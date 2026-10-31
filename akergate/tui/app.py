"""
AkerGate - Interactive Terminal User Interface (TUI)
Full keyboard-driven management console for PAM, TOTP, Telegram Bot, Services, and Sentry.
Supports seamless navigation via Arrow Keys (UP / DOWN / LEFT / RIGHT), ENTER, SPACE, and ESC.
Zero emojis, clean symbols only.
"""

import os
import sys
import time
import socket
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.text import Text

from akergate.config import (
    APP_NAME,
    APP_VERSION,
    AUTHOR,
    load_config,
    save_config,
    is_root,
    get_totp_secret_file,
    get_telegram_secret_file,
    get_events_log_file,
    get_offline_queue_file
)
from akergate.core.totp import generate_totp_secret, verify_totp, compute_totp, build_otpauth_uri
from akergate.core.windowed_otp import generate_telegram_secret, verify_windowed_otp, generate_windowed_otp
from akergate.core.storage import get_totp_secret, set_totp_secret, get_telegram_secret, set_telegram_secret
from akergate.core.lockdown import (
    is_lockdown_active,
    get_lockdown_state,
    trigger_lockdown,
    disarm_lockdown,
    parse_custom_policy,
    DEFAULT_POLICY
)
from akergate.pam.patcher import is_pam_patched, patch_pam, unpatch_pam
from akergate.pam.rollback import run_failsafe_test
from akergate.tui.qr_render import generate_terminal_qr
from akergate.tui.keyboard import get_key, select_menu, wait_for_key
from akergate.tui.ascii_banner import get_rich_banner
from akergate.sentry.notifier import send_telegram_alert, is_network_available
from akergate.i18n import t, get_current_language, set_language, list_available_languages

console = Console()

def clear_screen():
    console.clear()

def print_header(active_tab: str = "Dashboard", highlighted_tab_idx: Optional[int] = None):
    tabs = [
        ("1", t("tabs.dashboard")),
        ("2", t("tabs.services")),
        ("3", t("tabs.totp")),
        ("4", t("tabs.telegram")),
        ("5", t("tabs.sentry")),
        ("6", t("tabs.logs")),
        ("7", t("tabs.lockdown")),
        ("0", t("tabs.banner")),
        ("L", f"Lang: {get_current_language().upper()}"),
        ("Q", t("tabs.quit"))
    ]
    
    header_text = Text()
    header_text.append(f"{t('app.name').upper()} [v{APP_VERSION}] ", style="bold cyan")
    header_text.append(f"| {t('app.credits')}\n\n", style="dim")
    
    for idx, (key, name) in enumerate(tabs):
        is_highlighted = (highlighted_tab_idx is not None and idx == highlighted_tab_idx)
        is_active = (name.lower() == active_tab.lower() or (active_tab == "Dashboard" and key == "1"))
        
        if is_highlighted:
            header_text.append(f" > [{key}] {name} < ", style="bold #0B0E14 on #E5C07B")
        elif is_active:
            header_text.append(f" [{key}] {name} ", style="bold white on blue")
        else:
            header_text.append(f" [{key}] {name} ", style="dim")
        header_text.append(" ")
        
    instructions = "[dim]Navigate: [bold #56B6C2]UP / DOWN / LEFT / RIGHT Arrows[/bold #56B6C2]  |  Select: [bold #56B6C2]ENTER / SPACE[/bold #56B6C2][/dim]"
    console.print(Panel(header_text, subtitle=instructions, border_style="blue", padding=(0, 1)))

# ─────────────────────────────────────────────────────────────────────────────
# TAB 1: DASHBOARD
# ─────────────────────────────────────────────────────────────────────────────
def render_dashboard():
    config = load_config()
    pam_status = is_pam_patched()
    totp_configured = bool(get_totp_secret())
    tg_configured = bool(get_telegram_secret())
    
    # Status Overview Grid
    table = Table(show_header=True, header_style="bold magenta", expand=True)
    table.add_column("Component", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Details")
    
    table.add_row(
        t("dashboard.pam_integration"),
        f"[green]{t('dashboard.active')}[/green]" if pam_status else f"[yellow]{t('dashboard.not_configured')}[/yellow]",
        t("dashboard.pam_active_desc") if pam_status else t("dashboard.pam_inactive_desc")
    )
    table.add_row(
        t("dashboard.rtc_clock"),
        f"[green]{t('dashboard.clock_ok')}[/green]",
        t("dashboard.local_time", time=time.strftime('%Y-%m-%d %H:%M:%S'))
    )
    table.add_row(
        t("dashboard.offline_totp"),
        f"[green]{t('dashboard.configured')}[/green]" if totp_configured else f"[yellow]{t('dashboard.unset')}[/yellow]",
        t("dashboard.totp_desc") if totp_configured else t("dashboard.totp_unset_desc")
    )
    table.add_row(
        t("dashboard.telegram_otp"),
        f"[green]{t('dashboard.configured')}[/green]" if tg_configured else f"[yellow]{t('dashboard.unset')}[/yellow]",
        t("dashboard.telegram_desc", backend=config.get('telegram', {}).get('backend', 'cloudflare'))
    )
    table.add_row(
        t("dashboard.network_link"),
        f"[green]{t('dashboard.online')}[/green]" if is_network_available() else f"[yellow]{t('dashboard.offline')}[/yellow]",
        t("dashboard.network_desc")
    )
    
    console.print(Panel(table, title=f"[bold]{t('dashboard.title')}[/bold]", border_style="cyan"))
    
    # Protected Services Summary
    services = config.get("services", {})
    srv_text = Text()
    srv_text.append(f"{t('dashboard.protected_entries')}\n", style="bold")
    for srv, enabled in services.items():
        symbol = "[x]" if enabled else "[ ]"
        style = "green" if enabled else "dim red"
        srv_text.append(f"  {symbol} {srv:<14} ", style=style)
    console.print(Panel(srv_text, border_style="dim"))
    
    # Recent Log Entries
    log_file = get_events_log_file()
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8").strip().splitlines()[-4:]
            if lines:
                log_table = Table(title=t("dashboard.recent_events"), expand=True)
                log_table.add_column(t("dashboard.col_time"), style="dim")
                log_table.add_column(t("dashboard.col_user"))
                log_table.add_column(t("dashboard.col_service"))
                log_table.add_column(t("dashboard.col_method"))
                log_table.add_column(t("dashboard.col_result"))
                
                for line in reversed(lines):
                    import json
                    ev = json.loads(line)
                    res_str = f"[green]{t('dashboard.success')}[/green]" if ev.get("success") else f"[red]{t('dashboard.failed')}[/red]"
                    log_table.add_row(
                        ev.get("iso_time", ""),
                        ev.get("user", ""),
                        ev.get("service", ""),
                        ev.get("method", ""),
                        res_str
                    )
                console.print(log_table)
        except Exception:
            pass

# ─────────────────────────────────────────────────────────────────────────────
# TAB 2: SERVICES & PAM MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────
def render_services():
    config = load_config()
    services = config.get("services", {})
    
    while True:
        pam_status = is_pam_patched()
        status_msg = "[bold green][ACTIVE IN PAM][/bold green]" if pam_status else "[bold red][NOT APPLIED TO PAM][/bold red]"
        
        def draw_header():
            print_header("Services", highlighted_tab_idx=1)
            console.print(Panel(
                f"Current PAM Hook Status: {status_msg}\nLocation: /etc/pam.d/common-auth",
                title="PAM Integration Status",
                border_style="blue"
            ))

        options = [
            (f"sudo: {'[x] ENABLED' if services.get('sudo') else '[ ] DISABLED'}", "Root command elevation via terminal"),
            (f"screensaver: {'[x] ENABLED' if services.get('screensaver') else '[ ] DISABLED'}", "Lock screen session unlock (Cinnamon/i3/Sway)"),
            (f"login: {'[x] ENABLED' if services.get('login') else '[ ] DISABLED'}", "Display Manager login (LightDM/GDM)"),
            (f"sshd: {'[x] ENABLED' if services.get('sshd') else '[ ] DISABLED'}", "Remote SSH login authentication"),
            ("Apply Configuration to PAM", "Activate AkerGate in /etc/pam.d/common-auth (with 30s auto-rollback)"),
            ("Revert / Remove from PAM", "Restore original PAM configuration backup"),
            ("Return to Dashboard", "Go back to main status dashboard")
        ]

        choice_idx = select_menu(
            options,
            default_index=0,
            title="Service Protection Toggles (Use UP / DOWN Arrows + ENTER)",
            on_render_header=draw_header
        )

        if choice_idx in (0, 1, 2, 3):
            keys = ["sudo", "screensaver", "login", "sshd"]
            target = keys[choice_idx]
            services[target] = not services.get(target, False)
            config["services"] = services
            save_config(config)
            
        elif choice_idx == 4:
            if not is_root():
                console.print("\n[!] Root privileges required to modify PAM files. Please run with sudo.", style="bold red")
                time.sleep(2)
                continue
                
            console.print("\n[*] Starting 30-Second Failsafe PAM activation...", style="cyan")
            console.print("[*] Notice: If not confirmed within 30 seconds, configuration will automatically revert.")
            
            confirmed = Confirm.ask("Do you want to activate AkerGate in PAM now?")
            if confirmed:
                success, msg = patch_pam()
                if success:
                    console.print(f"\n[+] {msg}", style="bold green")
                else:
                    console.print(f"\n[!] Failed: {msg}", style="bold red")
                time.sleep(2)
                
        elif choice_idx == 5:
            if not is_root():
                console.print("\n[!] Root privileges required to modify PAM files. Please run with sudo.", style="bold red")
                time.sleep(2)
                continue
            success, msg = unpatch_pam()
            if success:
                console.print(f"\n[+] {msg}", style="bold green")
            else:
                console.print(f"\n[!] {msg}", style="bold red")
            time.sleep(2)
            
        elif choice_idx == 6 or choice_idx == len(options) - 1:
            break

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: TOTP SETUP & QR CODE
# ─────────────────────────────────────────────────────────────────────────────
def render_totp_setup():
    secret = get_totp_secret()
    
    while True:
        def draw_content():
            print_header("TOTP / QR", highlighted_tab_idx=2)
            nonlocal secret
            secret = get_totp_secret()
            if secret:
                username = os.environ.get("USER", "yuki")
                uri = build_otpauth_uri(secret, username)
                
                console.print(Panel(
                    f"Base32 Secret: [bold cyan]{secret}[/bold cyan]\n"
                    f"Key URI: [dim]{uri}[/dim]",
                    title="TOTP Key Credentials",
                    border_style="cyan"
                ))
                
                console.print("\n[bold]Scan this QR code with Google Authenticator, Aegis, or 2FAS:[/bold]\n")
                qr_output = generate_terminal_qr(uri)
                console.print(qr_output)
                
                current_code = compute_totp(secret)
                console.print(f"\nCurrent Host Calculated Code: [bold green]{current_code}[/bold green] (changes every 30s)")
            else:
                console.print(Panel("[yellow][!] No TOTP secret configured yet. Select Generate New Key below.[/yellow]", border_style="yellow"))

        options = [
            ("Test Verification Code", "Type 6-digit code shown on your phone to verify sync"),
            ("Generate New Secret Key", "Create new RFC 6238 key and generate new QR code"),
            ("Return to Dashboard", "Go back to main status dashboard")
        ]

        choice_idx = select_menu(
            options,
            default_index=0,
            title="TOTP Setup & Verification Options (Arrow Keys)",
            on_render_header=draw_content
        )

        if choice_idx == 0:
            if not secret:
                console.print("\n[!] Please generate a TOTP key first.", style="bold red")
                time.sleep(1.5)
                continue
            user_code = Prompt.ask("\nEnter 6-digit code shown on your phone")
            valid, step = verify_totp(secret, user_code)
            if valid:
                console.print("[+] CODE VERIFIED SUCCESSFULLY! Phone and Host are in sync.", style="bold green")
            else:
                console.print("[!] Verification failed. Check clock synchronization or re-scan QR code.", style="bold red")
            wait_for_key("Press any arrow key or Enter to return...")
            
        elif choice_idx == 1:
            if Confirm.ask("\nGenerate a new TOTP key? Old keys will stop working"):
                secret = generate_totp_secret()
                set_totp_secret(secret)
                console.print("[+] New key generated and saved.", style="green")
                time.sleep(1)
                
        elif choice_idx == 2 or choice_idx == len(options) - 1:
            break

# ─────────────────────────────────────────────────────────────────────────────
# TAB 4: TELEGRAM BOT SETUP
# ─────────────────────────────────────────────────────────────────────────────
def render_telegram_setup():
    config = load_config()
    tg_cfg = config.get("telegram", {})
    secret = get_telegram_secret()
    
    if not secret:
        secret = generate_telegram_secret()
        set_telegram_secret(secret)

    while True:
        def draw_content():
            print_header("Telegram", highlighted_tab_idx=3)
            bot_token = tg_cfg.get("bot_token", "")
            chat_id = tg_cfg.get("allowed_chat_id", 0)
            backend = tg_cfg.get("backend", "cloudflare")
            
            table = Table(title="Telegram Offline OTP Configuration", expand=True)
            table.add_column("Setting", style="bold cyan")
            table.add_column("Value")
            table.add_row("Backend Mode", f"[bold]{backend.upper()}[/bold] (cloudflare / standalone)")
            table.add_row("Bot Token", f"{bot_token[:8]}..." if bot_token else "[yellow]UNSET[/yellow]")
            table.add_row("Allowed Chat ID", str(chat_id) if chat_id else "[yellow]UNSET[/yellow]")
            table.add_row("Shared Secret", f"[cyan]{secret}[/cyan]")
            table.add_row("Epoch Interval", f"{tg_cfg.get('interval_seconds', 300)} seconds (5 minutes)")
            console.print(table)
            
            sample_otp = generate_windowed_otp(secret)
            console.print(f"Sample Valid 7-Digit OTP for Current Window: [bold green]{sample_otp}[/bold green]")

        options = [
            ("Configure Bot Token & Chat ID", "Set Telegram Bot credentials for offline OTP generation"),
            ("Switch Backend Mode", f"Toggle between Cloudflare Worker and Standalone Python Bot"),
            ("Test 7-Digit Offline OTP", "Verify a 7-digit OTP against the RTC epoch window"),
            ("Return to Dashboard", "Go back to main status dashboard")
        ]

        choice_idx = select_menu(
            options,
            default_index=0,
            title="Telegram Bot Options (Arrow Keys)",
            on_render_header=draw_content
        )

        if choice_idx == 0:
            bot_token = tg_cfg.get("bot_token", "")
            chat_id = tg_cfg.get("allowed_chat_id", 0)
            new_token = Prompt.ask("\nEnter Telegram Bot Token (from @BotFather)", default=bot_token)
            new_id_str = Prompt.ask("Enter your Telegram User ID (from @userinfobot)", default=str(chat_id))
            try:
                new_id = int(new_id_str)
            except ValueError:
                new_id = 0
                
            tg_cfg["bot_token"] = new_token
            tg_cfg["allowed_chat_id"] = new_id
            config["telegram"] = tg_cfg
            save_config(config)
            console.print("[+] Telegram credentials updated.", style="green")
            time.sleep(1)
            
        elif choice_idx == 1:
            backend = tg_cfg.get("backend", "cloudflare")
            new_backend = "standalone" if backend == "cloudflare" else "cloudflare"
            tg_cfg["backend"] = new_backend
            config["telegram"] = tg_cfg
            save_config(config)
            console.print(f"\n[+] Switched backend to {new_backend.upper()}", style="green")
            time.sleep(1)
            
        elif choice_idx == 2:
            test_code = Prompt.ask("\nEnter 7-digit Telegram OTP")
            valid, token_id = verify_windowed_otp(secret, test_code)
            if valid:
                console.print(f"[+] VALID OTP! Identified as: {token_id}", style="bold green")
            else:
                console.print("[!] Invalid OTP or expired epoch window.", style="bold red")
            wait_for_key("Press any arrow key or Enter to return...")
            
        elif choice_idx == 3 or choice_idx == len(options) - 1:
            break

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: SENTRY ALERTS & MONITORING
# ─────────────────────────────────────────────────────────────────────────────
def render_sentry_setup():
    config = load_config()
    sentry_cfg = config.get("sentry", {})
    queue_file = get_offline_queue_file()

    while True:
        queue_count = 0
        if queue_file.exists():
            try:
                queue_count = len(queue_file.read_text(encoding="utf-8").strip().splitlines())
            except Exception:
                queue_count = 0

        def draw_content():
            print_header("Sentry", highlighted_tab_idx=4)
            table = Table(title="AkerGate Sentry Monitoring Settings", expand=True)
            table.add_column("Setting", style="bold cyan")
            table.add_column("State", style="bold")
            table.add_row("Notify on Login Success", "[green]ON[/green]" if sentry_cfg.get("notify_on_login") else "[dim]OFF[/dim]")
            table.add_row("Notify on Failed Attempts", "[green]ON[/green]" if sentry_cfg.get("notify_on_failed") else "[dim]OFF[/dim]")
            table.add_row("Track Active Sessions", "[green]ON[/green]" if sentry_cfg.get("notify_on_session") else "[dim]OFF[/dim]")
            table.add_row("Pending Offline Alerts Queue", f"[yellow]{queue_count} events queued[/yellow]")
            console.print(table)

        options = [
            (f"Notify on Login: {'[x] ON' if sentry_cfg.get('notify_on_login', True) else '[ ] OFF'}", "Send Telegram alert on successful PAM login"),
            (f"Notify on Failed Attempts: {'[x] ON' if sentry_cfg.get('notify_on_failed', True) else '[ ] OFF'}", "Send Telegram alert on failed authentication attempt"),
            (f"Track Active Sessions: {'[x] ON' if sentry_cfg.get('notify_on_session', False) else '[ ] OFF'}", "Send Telegram alert when a session is opened or closed"),
            ("Send Test Notification to Telegram", "Dispatch immediate test notification"),
            ("Return to Dashboard", "Go back to main status dashboard")
        ]

        choice_idx = select_menu(
            options,
            default_index=0,
            title="Sentry Monitoring Options (Arrow Keys)",
            on_render_header=draw_content
        )

        if choice_idx == 0:
            sentry_cfg["notify_on_login"] = not sentry_cfg.get("notify_on_login", True)
            config["sentry"] = sentry_cfg
            save_config(config)
        elif choice_idx == 1:
            sentry_cfg["notify_on_failed"] = not sentry_cfg.get("notify_on_failed", True)
            config["sentry"] = sentry_cfg
            save_config(config)
        elif choice_idx == 2:
            sentry_cfg["notify_on_session"] = not sentry_cfg.get("notify_on_session", False)
            config["sentry"] = sentry_cfg
            save_config(config)
        elif choice_idx == 3:
            console.print("\n[*] Sending test alert to Telegram...", style="cyan")
            test_msg = (
                "*[+] AKERGATE TEST ALERT*\n"
                "────────────────────────\n"
                f"• Host: `{socket.gethostname()}`\n"
                f"• Time: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                "• Status: Communication channel active\n"
                "────────────────────────"
            )
            if send_telegram_alert(test_msg, config):
                console.print("[+] Test alert sent successfully!", style="bold green")
            else:
                console.print("[!] Failed to send alert. Check Bot Token, Chat ID, and internet link.", style="bold red")
            time.sleep(2)
        elif choice_idx == 4 or choice_idx == len(options) - 1:
            break

# ─────────────────────────────────────────────────────────────────────────────
# TAB 6: AUDIT LOGS
# ─────────────────────────────────────────────────────────────────────────────
def render_audit_logs():
    clear_screen()
    print_header("Audit Logs", highlighted_tab_idx=5)
    log_file = get_events_log_file()
    if not log_file.exists():
        console.print("[dim]No audit events recorded yet.[/dim]")
    else:
        try:
            import json
            lines = log_file.read_text(encoding="utf-8").strip().splitlines()
            table = Table(title="Authentication Audit Trail (Latest 20 Events)", expand=True)
            table.add_column("Time", style="dim")
            table.add_column("User")
            table.add_column("Service")
            table.add_column("Method")
            table.add_column("Result")
            
            for line in reversed(lines[-20:]):
                ev = json.loads(line)
                res_str = "[green]SUCCESS[/green]" if ev.get("success") else "[red]FAILED[/red]"
                table.add_row(
                    ev.get("iso_time", ""),
                    ev.get("user", ""),
                    ev.get("service", ""),
                    ev.get("method", ""),
                    res_str
                )
            console.print(table)
        except Exception as e:
            console.print(f"[!] Error reading logs: {e}", style="red")
            
    wait_for_key("Press any arrow key, Enter, or Space to return to Dashboard...")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 7: EMERGENCY LOCKDOWN & PANIC CONTROLS
# ─────────────────────────────────────────────────────────────────────────────
def render_lockdown():
    while True:
        active = is_lockdown_active()
        state = get_lockdown_state()
        policy = state.get("policy", DEFAULT_POLICY)

        def draw_content():
            print_header("Lockdown", highlighted_tab_idx=6)
            if active:
                status_banner = "[bold white on red] EMERGENCY LOCKDOWN ACTIVE [/bold white on red]"
                req_list = []
                if policy.get("totp_count", 0) > 0:
                    req_list.append(f"{policy['totp_count']} Consecutive TOTP code(s)")
                if policy.get("require_emergency_pin"):
                    req_list.append("Emergency Recovery PIN")
                if policy.get("require_telegram_otp"):
                    req_list.append("Telegram Windowed OTP")
                req_str = ", ".join(req_list) if req_list else "None (Manual Disarm Only)"
                
                details = (
                    f"• Status: {status_banner}\n"
                    f"• Policy Name: [bold cyan]{policy.get('name', 'custom').upper()}[/bold cyan]\n"
                    f"• Required for Disarm: [bold yellow]{req_str}[/bold yellow]\n"
                    f"• Trigger Source: `{state.get('trigger_source', 'unknown')}`\n"
                    f"• Forensic Report: `{state.get('report_path', 'None')}`\n\n"
                    "[bold yellow]Standard 1-token authentication is suspended.[/bold yellow]"
                )
            else:
                status_banner = "[bold green]NORMAL - SYSTEM SECURE[/bold green]"
                details = (
                    f"• Status: {status_banner}\n"
                    "• Mode: Flexible Multi-Auth (Password / TOTP / Telegram OTP)\n"
                    "• Automatic Brute-Force Trigger: Enabled (Breach at 5 consecutive failures)\n"
                    "• Disarm Policy: Fully Customizable on demand"
                )
            console.print(Panel(details, title="Host Quarantine Console", border_style="red" if active else "green"))

        if active:
            options = [
                ("Disarm Lockdown (Restore Flexible Multi-Auth)", "Remove quarantine and return to normal mode"),
                ("View Forensic Incident Report", "Inspect Markdown forensic snapshot of processes and sessions"),
                ("Return to Dashboard", "Go back to main status dashboard")
            ]
        else:
            options = [
                ("Trigger Lockdown: Dual Consecutive TOTP", "Require 2 consecutive TOTP codes to unlock (Offline safe)"),
                ("Trigger Lockdown: Emergency Recovery PIN", "Require emergency PIN/Passphrase to unlock"),
                ("Trigger Lockdown: Custom Rule Builder", "Customize TOTP count, PIN, and Telegram OTP requirements"),
                ("View Latest Forensic Report", "Inspect last captured forensic report"),
                ("Return to Dashboard", "Go back to main status dashboard")
            ]

        choice_idx = select_menu(
            options,
            default_index=0,
            title="Lockdown & Quarantine Controls (Arrow Keys)",
            on_render_header=draw_content
        )

        if active:
            if choice_idx == 0:
                if Confirm.ask("\nDisarm emergency lockdown now?"):
                    if disarm_lockdown():
                        console.print("[+] Lockdown disarmed. Flexible multi-auth restored.", style="bold green")
                    time.sleep(1)
            elif choice_idx == 1:
                rep_path = state.get("report_path")
                if rep_path and Path(rep_path).exists():
                    content = Path(rep_path).read_text(encoding="utf-8")
                    console.print(Panel(content[:3000], title="Forensic Incident Report", border_style="yellow"))
                else:
                    console.print("[dim]No incident report found.[/dim]")
                wait_for_key()
            elif choice_idx == 2 or choice_idx == len(options) - 1:
                break
        else:
            if choice_idx == 0:
                if Confirm.ask("\nConfirm emergency quarantine with policy 'dual_totp'?"):
                    ok, report = trigger_lockdown(policy_input="dual_totp", trigger_source="tui_manual")
                    if ok:
                        console.print(f"[+] Emergency lockdown activated. Forensic report: {report}", style="bold red")
                    time.sleep(2)
            elif choice_idx == 1:
                pin_input = Prompt.ask("\nEnter Emergency Recovery PIN to lock with", password=True)
                if pin_input:
                    ok, report = trigger_lockdown(policy_input="pin_only", trigger_source="tui_pin_only", emergency_pin=pin_input)
                    if ok:
                        console.print(f"[+] PIN-only lockdown activated! Report: {report}", style="bold red")
                    time.sleep(2)
            elif choice_idx == 2:
                console.print("\n[bold cyan]--- Custom Disarm Policy Builder ---[/bold cyan]")
                totp_count_str = Prompt.ask("Number of Consecutive TOTP codes required (0 for none)", default="2")
                try:
                    totp_cnt = int(totp_count_str)
                except ValueError:
                    totp_cnt = 2
                req_pin = Confirm.ask("Require custom Emergency Recovery PIN?", default=False)
                pin_val = ""
                if req_pin:
                    pin_val = Prompt.ask("Enter emergency PIN/Passphrase", password=True)
                req_tg = Confirm.ask("Require active Telegram OTP?", default=False)
                expire_str = Prompt.ask("Auto-expire after X minutes (0 for never)", default="0")
                try:
                    expire_mins = int(expire_str)
                except ValueError:
                    expire_mins = 0
                custom_rule = {
                    "name": "custom_builder",
                    "totp_count": totp_cnt,
                    "require_emergency_pin": req_pin,
                    "emergency_pin_hash": "",
                    "require_telegram_otp": req_tg,
                    "allow_remote_disarm": True,
                    "auto_expire_minutes": expire_mins
                }
                from akergate.core.lockdown import hash_pin
                if req_pin and pin_val:
                    custom_rule["emergency_pin_hash"] = hash_pin(pin_val)
                if Confirm.ask("Activate lockdown now with these custom rules?"):
                    ok, report = trigger_lockdown(policy_input=custom_rule, trigger_source="tui_custom_builder")
                    if ok:
                        console.print(f"[+] Custom lockdown activated! Report: {report}", style="bold red")
                    time.sleep(2)
            elif choice_idx == 3:
                rep_path = state.get("report_path")
                if rep_path and Path(rep_path).exists():
                    content = Path(rep_path).read_text(encoding="utf-8")
                    console.print(Panel(content[:3000], title="Forensic Incident Report", border_style="yellow"))
                else:
                    console.print("[dim]No incident report found.[/dim]")
                wait_for_key()
            elif choice_idx == 4 or choice_idx == len(options) - 1:
                break

# ─────────────────────────────────────────────────────────────────────────────
# TAB 0: BANNER VIEW
# ─────────────────────────────────────────────────────────────────────────────
def render_banner_screen():
    clear_screen()
    print_header("Banner", highlighted_tab_idx=7)
    banner = get_rich_banner()
    console.print(Panel(
        banner,
        title=f"[bold #E5C07B]{t('tabs.banner').upper()}[/bold #E5C07B] - {APP_NAME.upper()} [v{APP_VERSION}]",
        subtitle=f"[#56B6C2]Clean Modern Developer Typography | Author: {AUTHOR}[/#56B6C2]",
        border_style="#E5C07B",
        padding=(1, 2)
    ))
    wait_for_key("Press any arrow key, Enter, or Space to return to Dashboard...")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN TUI LOOP (Fully Keyboard-Driven with Arrow Keys)
# ─────────────────────────────────────────────────────────────────────────────
def main_tui():
    tabs_keys = ["1", "2", "3", "4", "5", "6", "7", "0", "L", "Q"]
    tab_names = ["Dashboard", "Services", "TOTP / QR", "Telegram", "Sentry", "Audit Logs", "Lockdown", "Banner", "Lang", "Quit"]
    
    current_tab_idx = 0
    
    while True:
        clear_screen()
        active_tab = tab_names[current_tab_idx]
        
        if active_tab == "Dashboard":
            def draw_dash():
                print_header(active_tab="Dashboard", highlighted_tab_idx=current_tab_idx)
                render_dashboard()

            dash_options = [
                ("Configure Protected Services", "Manage PAM rules for sudo, login, screensaver, sshd"),
                ("Manage TOTP & Scan QR Code", "View current credentials or re-scan terminal QR"),
                ("Telegram Bot Offline Settings", "Manage bot token, chat ID, and 7-digit OTP tests"),
                ("Sentry Event Monitor", "Configure brute-force lockdown and alert notifications"),
                ("View Authentication Audit Logs", "Read authentication history and timestamps"),
                ("Emergency Quarantine & Lockdown", "Trigger or disarm lockdown policies"),
                ("View AkerGate Logo Banner", "Display official two-tone typography banner"),
                (f"Switch Language ({'العربية' if get_current_language() == 'en' else 'English'})", "Toggle interface language instantly"),
                ("Quit AkerGate Console", "Close interactive terminal user interface")
            ]

            choice_idx = select_menu(
                dash_options,
                default_index=0,
                title="Dashboard Navigation & Actions (Use UP / DOWN Arrows + ENTER)",
                on_render_header=draw_dash,
                allow_cancel=False
            )

            if choice_idx == 0:
                current_tab_idx = 1
            elif choice_idx == 1:
                current_tab_idx = 2
            elif choice_idx == 2:
                current_tab_idx = 3
            elif choice_idx == 3:
                current_tab_idx = 4
            elif choice_idx == 4:
                current_tab_idx = 5
            elif choice_idx == 5:
                current_tab_idx = 6
            elif choice_idx == 6:
                current_tab_idx = 7
            elif choice_idx == 7:
                curr = get_current_language()
                set_language("ar" if curr == "en" else "en")
            elif choice_idx == 8 or choice_idx == len(dash_options) - 1:
                break
                
        elif active_tab == "Services":
            render_services()
            current_tab_idx = 0
            
        elif active_tab == "TOTP / QR":
            render_totp_setup()
            current_tab_idx = 0
            
        elif active_tab == "Telegram":
            render_telegram_setup()
            current_tab_idx = 0
            
        elif active_tab == "Sentry":
            render_sentry_setup()
            current_tab_idx = 0
            
        elif active_tab == "Audit Logs":
            render_audit_logs()
            current_tab_idx = 0
            
        elif active_tab == "Lockdown":
            render_lockdown()
            current_tab_idx = 0
            
        elif active_tab == "Banner":
            render_banner_screen()
            current_tab_idx = 0
            
        elif active_tab == "Lang":
            curr = get_current_language()
            set_language("ar" if curr == "en" else "en")
            current_tab_idx = 0
            
        elif active_tab == "Quit":
            break

if __name__ == "__main__":
    main_tui()

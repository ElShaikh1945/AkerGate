"""
AkerGate - Interactive Terminal User Interface (TUI)
Full management console for PAM, TOTP, Telegram Bot, Services, and Sentry.
Zero emojis, clean symbols only.
"""

import os
import sys
import time
import socket
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.prompt import Prompt, Confirm
from rich.layout import Layout
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
from akergate.sentry.notifier import send_telegram_alert, is_network_available

console = Console()

def clear_screen():
    console.clear()

def print_header(active_tab: str = "Dashboard"):
    tabs = [
        ("1", "Dashboard"),
        ("2", "Services"),
        ("3", "TOTP / QR"),
        ("4", "Telegram"),
        ("5", "Sentry"),
        ("6", "Audit Logs"),
        ("7", "Lockdown"),
        ("Q", "Quit")
    ]
    
    header_text = Text()
    header_text.append(f"{APP_NAME.upper()} [v{APP_VERSION}] ", style="bold cyan")
    header_text.append(f"| Developed by {AUTHOR} | Non-Commercial\n", style="dim")
    
    for key, name in tabs:
        if name == active_tab:
            header_text.append(f" [{key}] {name} ", style="bold white on blue")
        else:
            header_text.append(f" [{key}] {name} ", style="dim")
        header_text.append(" ")
        
    console.print(Panel(header_text, border_style="blue", padding=(0, 1)))

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
        "PAM Integration",
        "[green][ACTIVE][/green]" if pam_status else "[yellow][NOT CONFIGURED][/yellow]",
        "/etc/pam.d/common-auth" if pam_status else "Select [2] Services to configure"
    )
    table.add_row(
        "Hardware Clock (RTC)",
        "[green][OK][/green]",
        f"Local time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    table.add_row(
        "Offline TOTP",
        "[green][CONFIGURED][/green]" if totp_configured else "[yellow][UNSET][/yellow]",
        "RFC 6238 6-Digit Authenticator Key" if totp_configured else "Select [3] to set up"
    )
    table.add_row(
        "Telegram Offline OTP",
        "[green][CONFIGURED][/green]" if tg_configured else "[yellow][UNSET][/yellow]",
        f"Backend: {config.get('telegram', {}).get('backend', 'cloudflare')} (7-Digit)"
    )
    table.add_row(
        "Network Link",
        "[green][ONLINE][/green]" if is_network_available() else "[yellow][OFFLINE][/yellow]",
        "Sentry queue active for offline alerts"
    )
    
    console.print(Panel(table, title="[bold]System Status Overview[/bold]", border_style="cyan"))
    
    # Protected Services Summary
    services = config.get("services", {})
    srv_text = Text()
    srv_text.append("Protected Entry Points:\n", style="bold")
    for srv, enabled in services.items():
        symbol = "[x]" if enabled else "[ ]"
        style = "green" if enabled else "dim red"
        srv_text.append(f"  {symbol} {srv:<14} ", style=style)
    console.print(Panel(srv_text, border_style="dim"))
    
    # Recent Log Entries
    log_file = get_events_log_file()
    if log_file.exists():
        try:
            lines = log_file.read_text(encoding="utf-8").strip().splitlines()[-5:]
            if lines:
                log_table = Table(title="Recent Authentication Events", expand=True)
                log_table.add_column("Time", style="dim")
                log_table.add_column("User")
                log_table.add_column("Service")
                log_table.add_column("Method")
                log_table.add_column("Result")
                
                for line in reversed(lines):
                    import json
                    ev = json.loads(line)
                    res_str = "[green]SUCCESS[/green]" if ev.get("success") else "[red]FAILED[/red]"
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
    pam_status = is_pam_patched()
    
    table = Table(title="Service Protection Toggles", expand=True)
    table.add_column("Key", style="bold cyan", width=6)
    table.add_column("Service", style="bold")
    table.add_column("Scope")
    table.add_column("Status", style="bold")
    
    table.add_row("1", "sudo", "Root command line elevation", "[green]PROTECTED[/green]" if services.get("sudo") else "[dim]DISABLED[/dim]")
    table.add_row("2", "screensaver", "Lock screen (Cinnamon/i3/Sway)", "[green]PROTECTED[/green]" if services.get("screensaver") else "[dim]DISABLED[/dim]")
    table.add_row("3", "login", "Display Manager (LightDM/GDM)", "[green]PROTECTED[/green]" if services.get("login") else "[dim]DISABLED[/dim]")
    table.add_row("4", "sshd", "Remote SSH login", "[green]PROTECTED[/green]" if services.get("sshd") else "[dim]DISABLED[/dim]")
    
    console.print(table)
    
    status_msg = "[bold green][ACTIVE IN PAM][/bold green]" if pam_status else "[bold red][NOT APPLIED TO PAM][/bold red]"
    console.print(Panel(f"Current PAM Hook Status: {status_msg}\nLocation: /etc/pam.d/common-auth", border_style="blue"))
    
    console.print("[bold]Available Actions:[/bold]")
    console.print("  [1-4] Toggle corresponding service")
    console.print("  [A] Apply to PAM with [bold yellow]30-Second Failsafe Auto-Rollback[/bold yellow]")
    console.print("  [R] Remove / Revert AkerGate from PAM")
    console.print("  [B] Back to Dashboard")
    
    choice = Prompt.ask("\nSelect action", choices=["1", "2", "3", "4", "a", "A", "r", "R", "b", "B"], default="b")
    
    if choice in ("1", "2", "3", "4"):
        keys = {"1": "sudo", "2": "screensaver", "3": "login", "4": "sshd"}
        target = keys[choice]
        services[target] = not services.get(target, False)
        config["services"] = services
        save_config(config)
        console.print(f"[+] Toggled {target} -> {'ENABLED' if services[target] else 'DISABLED'}", style="green")
        time.sleep(1)
        
    elif choice in ("a", "A"):
        if not is_root():
            console.print("[!] Root privileges required to modify PAM files. Please run with sudo.", style="bold red")
            time.sleep(2)
            return
            
        console.print("\n[*] Starting 30-Second Failsafe PAM activation...", style="cyan")
        console.print("[*] Notice: If not confirmed within 30 seconds, configuration will automatically revert.")
        
        def on_tick(remaining):
            console.print(f"[*] Failsafe active: {remaining}s remaining before auto-rollback...", end="\r")
            
        def on_revert():
            console.print("\n[!] Timeout reached! Configuration safely reverted to original PAM settings.", style="bold yellow")
            
        # Run failsafe confirmation test
        confirmed = Confirm.ask("Do you want to activate AkerGate in PAM now?")
        if confirmed:
            success, msg = patch_pam()
            if success:
                console.print(f"\n[+] {msg}", style="bold green")
            else:
                console.print(f"\n[!] Failed: {msg}", style="bold red")
            time.sleep(2)
            
    elif choice in ("r", "R"):
        if not is_root():
            console.print("[!] Root privileges required to modify PAM files. Please run with sudo.", style="bold red")
            time.sleep(2)
            return
        success, msg = unpatch_pam()
        if success:
            console.print(f"[+] {msg}", style="bold green")
        else:
            console.print(f"[!] {msg}", style="bold red")
        time.sleep(2)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 3: TOTP SETUP & QR CODE
# ─────────────────────────────────────────────────────────────────────────────
def render_totp_setup():
    secret = get_totp_secret()
    
    if not secret:
        console.print("[yellow][!] No TOTP secret configured yet.[/yellow]")
        if Confirm.ask("Generate a new RFC 6238 TOTP Secret Key now?"):
            secret = generate_totp_secret()
            set_totp_secret(secret)
            console.print("[+] New TOTP Secret generated!", style="green")
            
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
        
        # Current live code for verification
        current_code = compute_totp(secret)
        console.print(f"\nCurrent Host Calculated Code: [bold green]{current_code}[/bold green] (changes every 30s)")
        
    console.print("\n[bold]Options:[/bold]")
    console.print("  [T] Test Verification (Type 6-digit code from phone)")
    console.print("  [G] Generate New Secret Key")
    console.print("  [B] Back to Dashboard")
    
    choice = Prompt.ask("\nSelect option", choices=["t", "T", "g", "G", "b", "B"], default="b")
    
    if choice in ("t", "T"):
        user_code = Prompt.ask("Enter 6-digit code shown on your phone")
        valid, step = verify_totp(secret, user_code)
        if valid:
            console.print("[+] CODE VERIFIED SUCCESSFULLY! Phone and Host are in sync.", style="bold green")
        else:
            console.print("[!] Verification failed. Check clock synchronization or re-scan QR code.", style="bold red")
        Prompt.ask("\nPress Enter to continue")
        
    elif choice in ("g", "G"):
        if Confirm.ask("Are you sure you want to regenerate the TOTP key? Old keys will stop working."):
            secret = generate_totp_secret()
            set_totp_secret(secret)
            console.print("[+] New key generated and saved.", style="green")
            time.sleep(1)

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
    
    # Generate current sample OTP for testing
    sample_otp = generate_windowed_otp(secret)
    console.print(f"Sample Valid 7-Digit OTP for Current Window: [bold green]{sample_otp}[/bold green]")
    
    console.print("\n[bold]Options:[/bold]")
    console.print("  [1] Configure Bot Token & Chat ID")
    console.print("  [2] Switch Backend (Cloudflare Worker <-> Standalone VPS)")
    console.print("  [3] Test OTP Verification (Enter 7-digit code)")
    console.print("  [B] Back to Dashboard")
    
    choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "b", "B"], default="b")
    
    if choice == "1":
        new_token = Prompt.ask("Enter Telegram Bot Token (from @BotFather)", default=bot_token)
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
        
    elif choice == "2":
        new_backend = "standalone" if backend == "cloudflare" else "cloudflare"
        tg_cfg["backend"] = new_backend
        config["telegram"] = tg_cfg
        save_config(config)
        console.print(f"[+] Switched backend to {new_backend.upper()}", style="green")
        time.sleep(1)
        
    elif choice == "3":
        test_code = Prompt.ask("Enter 7-digit Telegram OTP")
        valid, token_id = verify_windowed_otp(secret, test_code)
        if valid:
            console.print(f"[+] VALID OTP! Identified as: {token_id}", style="bold green")
        else:
            console.print("[!] Invalid OTP or expired epoch window.", style="bold red")
        Prompt.ask("\nPress Enter to continue")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 5: SENTRY ALERTS & MONITORING
# ─────────────────────────────────────────────────────────────────────────────
def render_sentry_setup():
    config = load_config()
    sentry_cfg = config.get("sentry", {})
    queue_file = get_offline_queue_file()
    queue_count = 0
    if queue_file.exists():
        try:
            queue_count = len(queue_file.read_text(encoding="utf-8").strip().splitlines())
        except Exception:
            queue_count = 0
            
    table = Table(title="AkerGate Sentry Monitoring Settings", expand=True)
    table.add_column("Setting", style="bold cyan")
    table.add_column("State", style="bold")
    
    table.add_row("Master Sentry Daemon", "[green]ENABLED[/green]" if sentry_cfg.get("enabled") else "[dim]DISABLED[/dim]")
    table.add_row("Notify on Login Success", "[green]ON[/green]" if sentry_cfg.get("notify_on_login") else "[dim]OFF[/dim]")
    table.add_row("Notify on Failed Attempts", "[green]ON[/green]" if sentry_cfg.get("notify_on_failed") else "[dim]OFF[/dim]")
    table.add_row("Track Active Sessions", "[green]ON[/green]" if sentry_cfg.get("notify_on_session") else "[dim]OFF[/dim]")
    table.add_row("Pending Offline Alerts Queue", f"[yellow]{queue_count} events queued[/yellow]")
    
    console.print(table)
    
    console.print("\n[bold]Options:[/bold]")
    console.print("  [1] Toggle Notify on Login")
    console.print("  [2] Toggle Notify on Failed Attempts")
    console.print("  [3] Toggle Track Active Sessions")
    console.print("  [T] Send Test Notification to Telegram")
    console.print("  [B] Back to Dashboard")
    
    choice = Prompt.ask("\nSelect option", choices=["1", "2", "3", "t", "T", "b", "B"], default="b")
    
    if choice == "1":
        sentry_cfg["notify_on_login"] = not sentry_cfg.get("notify_on_login", True)
    elif choice == "2":
        sentry_cfg["notify_on_failed"] = not sentry_cfg.get("notify_on_failed", True)
    elif choice == "3":
        sentry_cfg["notify_on_session"] = not sentry_cfg.get("notify_on_session", False)
    elif choice in ("t", "T"):
        console.print("[*] Sending test alert to Telegram...", style="cyan")
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
        return
        
    config["sentry"] = sentry_cfg
    save_config(config)

# ─────────────────────────────────────────────────────────────────────────────
# TAB 6: AUDIT LOGS
# ─────────────────────────────────────────────────────────────────────────────
def render_audit_logs():
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
            
    Prompt.ask("\nPress Enter to return to Dashboard")

# ─────────────────────────────────────────────────────────────────────────────
# TAB 7: EMERGENCY LOCKDOWN & PANIC CONTROLS
# ─────────────────────────────────────────────────────────────────────────────
def render_lockdown():
    active = is_lockdown_active()
    state = get_lockdown_state()
    policy = state.get("policy", DEFAULT_POLICY)
    
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
            f"• Incident Time: `{state.get('iso_time', 'unknown')}`\n"
            f"• Forensic Report: `{state.get('report_path', 'None')}`\n\n"
            "[bold yellow]Standard 1-token authentication is suspended.[/bold yellow]\n"
            "Disarm on host by entering the required credentials (e.g. `PIN+TOTP1+TOTP2`)."
        )
    else:
        status_banner = "[bold green]NORMAL - SYSTEM SECURE[/bold green]"
        details = (
            f"• Status: {status_banner}\n"
            "• Mode: Flexible Multi-Auth (Password / TOTP / Telegram OTP)\n"
            "• Automatic Brute-Force Trigger: Enabled (Breach at 5 consecutive failures)\n"
            "• Disarm Policy: Fully Customizable on demand"
        )
        
    console.print(Panel(details, title="[bold]Host Quarantine & Custom Defense Console[/bold]", border_style="red" if active else "green"))
    
    console.print("\n[bold]Actions:[/bold]")
    if active:
        console.print("  [D] Disarm Lockdown (Return to Normal)")
    else:
        console.print("  [1] Trigger Lockdown: Dual Consecutive TOTP (Offline Safe)")
        console.print("  [2] Trigger Lockdown: Custom Rule Builder (Customize factors freely)")
        console.print("  [3] Trigger Lockdown: Emergency PIN Only")
    console.print("  [V] View Latest Forensic Incident Report")
    console.print("  [B] Back to Dashboard")
    
    allowed = ["d", "D", "v", "V", "b", "B"] if active else ["1", "2", "3", "v", "V", "b", "B"]
    choice = Prompt.ask("\nSelect action", choices=allowed, default="b")
    
    if choice == "1":
        if Confirm.ask("Confirm emergency quarantine with policy 'dual_totp'?"):
            ok, report = trigger_lockdown(policy_input="dual_totp", trigger_source="tui_manual")
            if ok:
                console.print(f"[+] Emergency lockdown activated. Forensic report: {report}", style="bold red")
            time.sleep(2)
            
    elif choice == "2":
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
        expire_str = Prompt.ask("Auto-expire and unlock after X minutes (0 for never)", default="0")
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
            
    elif choice == "3":
        pin_input = Prompt.ask("Enter Emergency Recovery PIN to lock with", password=True)
        if pin_input:
            ok, report = trigger_lockdown(policy_input="pin_only", trigger_source="tui_pin_only", emergency_pin=pin_input)
            if ok:
                console.print(f"[+] PIN-only lockdown activated! Report: {report}", style="bold red")
            time.sleep(2)
            
    elif choice in ("d", "D"):
        if Confirm.ask("Disarm emergency lockdown now?"):
            if disarm_lockdown():
                console.print("[+] Lockdown disarmed. Flexible multi-auth restored.", style="bold green")
            time.sleep(1)
            
    elif choice in ("v", "V"):
        rep_path = state.get("report_path")
        if rep_path and Path(rep_path).exists():
            content = Path(rep_path).read_text(encoding="utf-8")
            console.print(Panel(content[:3000], title="Forensic Incident Report (Excerpt)", border_style="yellow"))
        else:
            console.print("[dim]No incident report found.[/dim]")
        Prompt.ask("\nPress Enter to return")

# ─────────────────────────────────────────────────────────────────────────────
# MAIN TUI LOOP
# ─────────────────────────────────────────────────────────────────────────────
def main_tui():
    active_tab = "Dashboard"
    
    while True:
        clear_screen()
        print_header(active_tab)
        
        if active_tab == "Dashboard":
            render_dashboard()
            console.print("\n[bold]Select view [1-7] or [Q] to quit:[/bold]")
            key = Prompt.ask("Action", choices=["1", "2", "3", "4", "5", "6", "7", "q", "Q"], default="1")
            
            if key == "1": active_tab = "Dashboard"
            elif key == "2": active_tab = "Services"
            elif key == "3": active_tab = "TOTP / QR"
            elif key == "4": active_tab = "Telegram"
            elif key == "5": active_tab = "Sentry"
            elif key == "6": active_tab = "Audit Logs"
            elif key == "7": active_tab = "Lockdown"
            elif key in ("q", "Q"): break
            
        elif active_tab == "Services":
            render_services()
            active_tab = "Dashboard"
            
        elif active_tab == "TOTP / QR":
            render_totp_setup()
            active_tab = "Dashboard"
            
        elif active_tab == "Telegram":
            render_telegram_setup()
            active_tab = "Dashboard"
            
        elif active_tab == "Sentry":
            render_sentry_setup()
            active_tab = "Dashboard"
            
        elif active_tab == "Audit Logs":
            render_audit_logs()
            active_tab = "Dashboard"
            
        elif active_tab == "Lockdown":
            render_lockdown()
            active_tab = "Dashboard"

if __name__ == "__main__":
    main_tui()

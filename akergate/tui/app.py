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
from akergate.tui.keyboard import get_key, select_menu, wait_for_key, console
from akergate.tui.ascii_banner import get_rich_banner
from akergate.sentry.notifier import (
    send_telegram_alert,
    is_network_available,
    set_telegram_webhook,
    get_telegram_webhook_info,
    delete_telegram_webhook
)
from akergate.core.serverless_deployer import (
    sync_telegram_serverless_config,
    sync_cloudflare_worker_bundle,
    run_tgcloud_push,
    run_wrangler_deploy,
    load_tgcloud_credentials,
    save_tgcloud_credentials,
    delete_tgcloud_credentials,
    run_tgcloud_interactive_login
)
from akergate.core.telegram_pair import (
    validate_bot_token,
    listen_for_incoming_user,
    dispatch_pairing_otp
)
from akergate.i18n import t, get_current_language, set_language, list_available_languages

_last_net_check_time = 0.0
_cached_net_state = False

def get_cached_network_status(ttl: float = 15.0) -> bool:
    """Return network availability with 15-second TTL cache to eliminate UI render stutter."""
    global _last_net_check_time, _cached_net_state
    now = time.time()
    if now - _last_net_check_time > ttl:
        _cached_net_state = is_network_available(timeout=1)
        _last_net_check_time = now
    return _cached_net_state

def clear_screen():
    """In-place clean reposition (cursor to top-left and clear to bottom) without wiping buffer."""
    sys.stdout.write("\033[H\033[J")
    sys.stdout.flush()

def print_header(title: str = "Dashboard", highlighted_tab_idx: Optional[int] = None):
    """
    Renders top visual presentation:
    - On Dashboard: Clean two-tone Slant typography banner
    - On Submenus: Clean, single-line breadcrumb navigation bar
    """
    if title == "Dashboard":
        console.print(get_rich_banner())
    else:
        nav_text = Text()
        nav_text.append(f"AKERGATE [v{APP_VERSION}]", style="bold #56B6C2")
        nav_text.append("  >  ", style="dim")
        nav_text.append(title.upper(), style="bold #E5C07B")
        console.print(Panel(nav_text, border_style="cyan", padding=(0, 1)))

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
        f"[green]{t('dashboard.online')}[/green]" if get_cached_network_status() else f"[yellow]{t('dashboard.offline')}[/yellow]",
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
# AUTOMATED SERVERLESS DEPLOYMENT WIZARD
# ─────────────────────────────────────────────────────────────────────────────
def render_serverless_wizard():
    """
    Automated Serverless Deployment Wizard.
    Guides the user through deploying to Telegram Serverless or Cloudflare with zero friction.
    """
    config = load_config()
    tg_cfg = config.get("telegram", {})
    bot_token = tg_cfg.get("bot_token", "")
    chat_id = tg_cfg.get("allowed_chat_id", 0)
    secret = get_telegram_secret()

    while True:
        def draw_wizard_header():
            print_header("Serverless Deployment Wizard")
            table = Table(box=None, expand=True, padding=(0, 1))
            table.add_column("Property", style="bold cyan", width=24)
            table.add_column("Status", style="bold")
            table.add_row("Bot Token", f"{bot_token[:8]}..." if bot_token else "[yellow]NOT CONFIGURED[/yellow]")
            table.add_row("Allowed Chat ID", str(chat_id) if chat_id else "[yellow]NOT CONFIGURED[/yellow]")
            table.add_row("Shared Secret", "[green]READY[/green]" if secret else "[yellow]NOT SET[/yellow]")
            saved_tg_tok = load_tgcloud_credentials()
            if saved_tg_tok:
                app_id = saved_tg_tok.split(":", 1)[0]
                table.add_row("tgcloud Session", f"[green]LINKED ({app_id})[/green]")
            else:
                table.add_row("tgcloud Session", "[yellow]NOT LINKED[/yellow]")
            console.print(Panel(table, title="[bold]Deployment Credentials Readiness[/bold]", border_style="cyan"))

        wizard_options = [
            ("Deploy to Telegram Serverless (Official tgcloud.ai)", "Auto-configures and pushes code directly to Telegram V8 cloud"),
            ("Login / Link Telegram Serverless Account (In-App)", "Connect via CLI Access Token or interactive tgcloud login"),
            ("Deploy to Cloudflare Workers (Auto Bundle & Webhook)", "Pre-bundles standalone worker.bundle.js & auto-registers webhook"),
            ("Auto-Sync Host Credentials to All Backend Templates", "Injects current Chat ID & Secret into all local template files"),
            ("Return to Telegram Menu", "Go back to previous menu")
        ]

        choice = select_menu(
            wizard_options,
            title="Choose Automated Deployment Target",
            on_render_header=draw_wizard_header
        )

        if choice == 0:
            if not chat_id:
                new_id_str = Prompt.ask("\nEnter your Telegram User ID (from @userinfobot)")
                try:
                    chat_id = int(new_id_str)
                    tg_cfg["allowed_chat_id"] = chat_id
                    config["telegram"] = tg_cfg
                    save_config(config)
                except ValueError:
                    console.print("[!] Invalid chat ID.", style="bold red")
                    time.sleep(1.5)
                    continue

            console.print("\n[bold cyan]Step 1: BotFather Serverless Activation[/bold cyan]")
            console.print("1. Open Telegram and message [bold]@BotFather[/bold]")
            console.print("2. Send /mybots -> choose your bot -> [bold]Serverless[/bold] -> [bold]Turn On[/bold]")
            confirmed = Confirm.ask("\nHave you enabled Serverless on @BotFather for your bot?")
            if not confirmed:
                console.print("[yellow]Please enable it first in @BotFather to authorize deployments.[/yellow]")
                time.sleep(2)
                continue

            # Check if session is already linked
            current_cli_tok = load_tgcloud_credentials()
            if not current_cli_tok:
                console.print("\n[bold yellow][!] No Telegram Serverless session linked yet.[/bold yellow]")
                auth_init_options = [
                    ("Paste CLI Access Token from @BotFather", "Instant connection with app<id>:<secret> token"),
                    ("Launch Official Interactive Login", "Runs official 'tgcloud login' in this terminal"),
                    ("Cancel & Return to Wizard", "Do not authenticate now")
                ]
                init_choice = select_menu(
                    auth_init_options,
                    title="Telegram Serverless Authentication Required",
                    border_style="yellow"
                )
                if init_choice == 0:
                    console.print("\n[dim]In @BotFather: /mybots -> your bot -> Serverless -> CLI Access -> Access token[/dim]")
                    token_in = Prompt.ask("Enter CLI Access Token (format: app<id>:<secret>)")
                    if token_in.strip():
                        ok_s, msg_s = save_tgcloud_credentials(token_in.strip())
                        if ok_s:
                            console.print(f"[+] {msg_s}", style="bold green")
                            current_cli_tok = token_in.strip()
                        else:
                            console.print(f"[!] {msg_s}", style="bold red")
                            time.sleep(2)
                            continue
                    else:
                        continue
                elif init_choice == 1:
                    console.print("\n[*] Starting official tgcloud login...", style="cyan")
                    time.sleep(1)
                    ok_l, msg_l = run_tgcloud_interactive_login()
                    if ok_l:
                        console.print(f"\n[+] {msg_l}", style="bold green")
                        current_cli_tok = load_tgcloud_credentials()
                    else:
                        console.print(f"\n[!] {msg_l}", style="yellow")
                        wait_for_key("Press any key to return...")
                        continue
                else:
                    continue

            console.print("\n[*] Auto-generating tgcloud configuration...", style="cyan")
            ok, msg = sync_telegram_serverless_config()
            if not ok:
                console.print(f"[!] {msg}", style="bold red")
                time.sleep(2)
                continue
            console.print(f"[+] {msg}", style="bold green")

            console.print("\n[*] Pushing to Telegram Serverless (npx @tgcloud/cli push)...", style="cyan")
            run_deploy = Confirm.ask("Execute automated deployment now?")
            if run_deploy:
                success, output = run_tgcloud_push(cli_token=current_cli_tok)
                if success:
                    tg_cfg["backend"] = "telegram_serverless"
                    config["telegram"] = tg_cfg
                    save_config(config)
                    console.print(f"\n[+] DEPLOYMENT SUCCEEDED!\n{output}", style="bold green")
                else:
                    console.print(f"\n[!] Deployment Output:\n{output}", style="yellow")
                    if "No CLI access token found" in output:
                        console.print("\n[bold red]Authentication Required:[/bold red]")
                        console.print("Please use '[2] Login / Link Telegram Serverless Account' to authenticate.")
                    else:
                        console.print("\n[dim]To run manually in terminal: cd telegram_backends/telegram_serverless && npx @tgcloud/cli push[/dim]")
                wait_for_key("Press any key to return...")

        elif choice == 1:
            while True:
                current_tok = load_tgcloud_credentials()
                app_info = current_tok.split(":", 1)[0] if current_tok else "NOT LINKED"

                def draw_auth_header():
                    print_header("Telegram Serverless Authentication Manager")
                    table = Table(box=None, expand=True, padding=(0, 1))
                    table.add_column("Property", style="bold cyan", width=24)
                    table.add_column("Status", style="bold")
                    if current_tok:
                        table.add_row("Connection Status", f"[green]LINKED ({app_info})[/green]")
                        table.add_row("CLI Token", f"[cyan]{current_tok[:10]}...[/cyan]")
                    else:
                        table.add_row("Connection Status", "[yellow]NOT LINKED[/yellow]")
                    console.print(Panel(table, title="[bold]Session Status[/bold]", border_style="cyan"))

                auth_menu_items = [
                    ("Paste CLI Access Token (Direct & Fast)", "Copy from @BotFather -> Serverless -> CLI Access -> Access token"),
                    ("Launch Official Interactive Login", "Runs official 'npx @tgcloud/cli login' in terminal")
                ]
                if current_tok:
                    auth_menu_items.append(("Disconnect / Clear Saved Credentials", "Remove stored session credentials"))
                auth_menu_items.append(("Return to Serverless Wizard", "Go back to previous menu"))

                sub_choice = select_menu(
                    auth_menu_items,
                    title="Choose Authentication Action",
                    on_render_header=draw_auth_header
                )

                if sub_choice == 0:
                    console.print("\n[bold]Instructions:[/bold]")
                    console.print("1. Open Telegram and message [bold]@BotFather[/bold]")
                    console.print("2. Send /mybots -> select your bot -> [bold]Serverless[/bold] -> [bold]CLI Access[/bold]")
                    console.print("3. Click [bold]Access token[/bold] and copy the value.\n")
                    token_input = Prompt.ask("Paste CLI Access Token (format: app<id>:<secret>)")
                    if token_input.strip():
                        ok_save, msg_save = save_tgcloud_credentials(token_input.strip())
                        if ok_save:
                            console.print(f"\n[+] {msg_save}", style="bold green")
                        else:
                            console.print(f"\n[!] {msg_save}", style="bold red")
                        time.sleep(2)
                elif sub_choice == 1:
                    console.print("\n[*] Launching official interactive login in terminal...", style="cyan")
                    console.print("[dim]AkerGate will temporarily yield terminal control to @tgcloud/cli.[/dim]\n")
                    time.sleep(1)
                    ok_log, msg_log = run_tgcloud_interactive_login()
                    if ok_log:
                        console.print(f"\n[+] {msg_log}", style="bold green")
                    else:
                        console.print(f"\n[!] {msg_log}", style="yellow")
                    wait_for_key("Press any key to return...")
                elif sub_choice == 2 and current_tok:
                    if Confirm.ask("\nAre you sure you want to remove tgcloud credentials?"):
                        delete_tgcloud_credentials()
                        console.print("[+] Telegram Serverless session removed.", style="bold green")
                        time.sleep(1.5)
                else:
                    # Return or cancel
                    break

        elif choice == 2:
            console.print("\n[*] Generating pre-bundled Cloudflare Worker...", style="cyan")
            ok, msg = sync_cloudflare_worker_bundle()
            if ok:
                console.print(f"[+] {msg}", style="bold green")
                console.print("\n[bold]Two Easy Options to Complete Cloudflare Deployment:[/bold]")
                console.print("  [bold cyan]Method A (Web Dashboard - 30 seconds):[/bold cyan]")
                console.print("  1. Open dash.cloudflare.com -> Workers & Pages -> Create Application.")
                console.print("  2. Click 'Quick edit', paste the full contents of:")
                console.print("     [bold yellow]telegram_backends/cloudflare_worker/worker.bundle.js[/bold yellow]")
                console.print("  3. Click 'Deploy'. Everything (secrets, token, chat ID) is already baked in!")
                console.print("\n  [bold cyan]Method B (Wrangler CLI):[/bold cyan]")
                console.print("  Run in terminal: [dim]cd telegram_backends/cloudflare_worker && npx wrangler deploy worker.bundle.js[/dim]")

                registered = Confirm.ask("\nDo you have the deployed Worker URL ready to link to Telegram now?")
                if registered:
                    worker_url = Prompt.ask("Enter Worker URL (e.g. https://my-bot.workers.dev)")
                    if worker_url:
                        if not bot_token:
                            bot_token = Prompt.ask("Enter Telegram Bot Token")
                            tg_cfg["bot_token"] = bot_token
                            config["telegram"] = tg_cfg
                            save_config(config)
                        ok_wh, msg_wh = set_telegram_webhook(bot_token, worker_url)
                        if ok_wh:
                            tg_cfg["webhook_url"] = worker_url
                            tg_cfg["backend"] = "serverless"
                            config["telegram"] = tg_cfg
                            save_config(config)
                            console.print(f"[+] Webhook registered successfully! {msg_wh}", style="bold green")
                        else:
                            console.print(f"[!] Failed to register webhook: {msg_wh}", style="bold red")
                wait_for_key("Press any key to return...")
            else:
                console.print(f"[!] {msg}", style="bold red")
                time.sleep(2)

        elif choice == 3:
            console.print("\n[*] Auto-syncing credentials to all backend templates...", style="cyan")
            ok1, m1 = sync_telegram_serverless_config()
            ok2, m2 = sync_cloudflare_worker_bundle()
            if ok1: console.print(f"[+] Telegram Serverless: {m1}", style="green")
            else: console.print(f"[!] Telegram Serverless: {m1}", style="yellow")
            if ok2: console.print(f"[+] Cloudflare Worker: {m2}", style="green")
            else: console.print(f"[!] Cloudflare Worker: {m2}", style="yellow")
            time.sleep(2)

        elif choice == 4 or choice == len(wizard_options) - 1:
            break

# ─────────────────────────────────────────────────────────────────────────────
# INTERACTIVE TELEGRAM AUTO-PAIRING WIZARD
# ─────────────────────────────────────────────────────────────────────────────
def render_telegram_pairing_wizard():
    """
    Interactive Auto-Pairing Wizard:
    1. Prompts for Bot Token & validates with Telegram Bot API.
    2. Listens for incoming message (/start) to auto-detect User ID.
    3. Confirms user identity or permits switching accounts.
    4. Dispatches a 6-digit confirmation OTP to Telegram to verify 2-way communication.
    5. Locks pairing upon code verification.
    """
    config = load_config()
    tg_cfg = config.get("telegram", {})
    current_token = tg_cfg.get("bot_token", "")

    print_header("Telegram Auto-Pairing Wizard")
    console.print(Panel(
        "This wizard automatically pairs your Linux Host with your Telegram account.\n"
        "You do NOT need to look up your numeric Chat ID manually!\n"
        "Just enter your Bot Token, send /start to your bot, and enter the verification code.",
        title="[bold]Zero-Manual Setup Experience[/bold]",
        border_style="cyan"
    ))

    # Step 1: Bot Token Entry & Verification
    console.print("\n[bold cyan]Step 1: Bot Token[/bold cyan]")
    bot_token = Prompt.ask("Enter Telegram Bot Token (from @BotFather)", default=current_token).strip()
    if not bot_token:
        console.print("[!] Bot Token cannot be empty.", style="bold red")
        time.sleep(1.5)
        return

    console.print("\n[*] Validating token with Telegram Bot API...", style="cyan")
    valid, bot_name, bot_info = validate_bot_token(bot_token)
    if not valid:
        console.print(f"[!] Token validation failed: {bot_name}", style="bold red")
        wait_for_key("Press any key to return...")
        return

    bot_username = bot_info.get("username", "")
    console.print(f"[+] Connected to Bot: [bold green]{bot_name}[/bold green]", style="bold green")

    # Step 2: Auto-Discovery Listener
    while True:
        console.print("\n" + "=" * 60)
        console.print(f"[bold cyan]Step 2: Auto-Discover Your Telegram Account[/bold cyan]")
        console.print("=" * 60)
        instructions = (
            f"1. Open your Telegram app on phone or desktop.\n"
            f"2. Search for: [bold green]@{bot_username}[/bold green] (or open t.me/{bot_username})\n"
            f"3. Click [bold]START[/bold] or send any text message (e.g. 'hello').\n\n"
            "[dim]AkerGate will automatically detect your incoming message...[/dim]"
        )
        console.print(Panel(instructions, title="[bold]Send Message to Your Bot[/bold]", border_style="green"))

        detected_user = None

        with console.status("[bold cyan]Listening for incoming message from your Telegram account (waiting up to 60s)...[/bold cyan]", spinner="dots"):
            ok, user_data, msg = listen_for_incoming_user(bot_token, timeout_seconds=60)
            if ok and user_data:
                detected_user = user_data

        if not detected_user:
            console.print(f"\n[yellow][!] {msg}[/yellow]")
            retry = Confirm.ask("Would you like to try listening again?")
            if retry:
                continue
            else:
                return

        # Step 3: Confirmation of Detected Account
        user_id = detected_user["user_id"]
        fname = detected_user["first_name"]
        uname = f"@{detected_user['username']}" if detected_user.get("username") else "No username"
        received_text = detected_user.get("text", "")

        user_table = Table(box=None, expand=True, padding=(0, 1))
        user_table.add_column("Property", style="bold cyan", width=18)
        user_table.add_column("Value", style="bold")
        user_table.add_row("Full Name", fname)
        user_table.add_row("Username", uname)
        user_table.add_row("Detected User ID", f"[bold green]{user_id}[/bold green]")
        user_table.add_row("Message Received", f"'{received_text}'")

        console.print(Panel(user_table, title="[bold]Incoming Sender Detected[/bold]", border_style="green"))

        pair_choices = [
            ("Confirm and Pair with this Account", f"Authorize User ID {user_id} ({fname})"),
            ("Wait for another message", "Send from a different Telegram account or number"),
            ("Cancel Pairing Wizard", "Exit to Telegram menu")
        ]
        choice = select_menu(pair_choices, title="Account Confirmation")
        if choice == 0:
            # Step 4: Two-Way OTP Verification Challenge
            console.print("\n" + "=" * 60)
            console.print(f"[bold cyan]Step 3: Two-Way Security Handshake[/bold cyan]")
            console.print("=" * 60)
            console.print(f"[*] Dispatching one-time pairing verification code to Telegram ({fname})...", style="cyan")

            otp_ok, sent_code, otp_msg = dispatch_pairing_otp(bot_token, user_id)
            if not otp_ok:
                console.print(f"[!] Failed to deliver OTP to Telegram: {otp_msg}", style="bold red")
                wait_for_key("Press any key to return...")
                return

            console.print(Panel(
                f"[bold green][+] VERIFICATION CODE DISPATCHED TO YOUR TELEGRAM![/bold green]\n"
                f"Check your Telegram app for a message from [bold]@{bot_username}[/bold].\n"
                "Enter the 6-digit confirmation code below to lock the pairing.",
                border_style="green"
            ))

            for attempt in range(3):
                input_code = Prompt.ask("\nEnter 6-digit Pairing Code received on Telegram").strip()
                if input_code == sent_code:
                    # Successfully verified!
                    tg_cfg["bot_token"] = bot_token
                    tg_cfg["allowed_chat_id"] = user_id
                    config["telegram"] = tg_cfg
                    save_config(config)

                    # Auto-sync credentials across all backend templates
                    sync_telegram_serverless_config()
                    sync_cloudflare_worker_bundle()

                    # Send final success confirmation to Telegram
                    success_notice = (
                        "*[+] AKERGATE PAIRING LOCKED SUCCESSFULLY*\n"
                        "────────────────────────\n"
                        f"• Host: `{socket.gethostname()}`\n"
                        f"• Paired ID: `{user_id}`\n"
                        f"• Time: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                        "• Status: Two-Way communication active and verified.\n"
                        "────────────────────────"
                    )
                    send_telegram_alert(success_notice, config)

                    console.print(Panel(
                        f"[bold green]PAIRING VERIFIED & LOCKED SUCCESSFULLY![/bold green]\n\n"
                        f"• Bot: [bold cyan]@{bot_username}[/bold cyan]\n"
                        f"• Authorized User: [bold cyan]{fname} ({uname})[/bold cyan]\n"
                        f"• Telegram User ID: [bold green]{user_id}[/bold green]\n\n"
                        "Two-way cryptographic communication is verified and active.",
                        title="[bold]Pairing Complete[/bold]",
                        border_style="green"
                    ))
                    wait_for_key("Press any key to continue...")
                    return
                else:
                    remaining_attempts = 2 - attempt
                    if remaining_attempts > 0:
                        console.print(f"[!] Incorrect code. {remaining_attempts} attempt(s) remaining.", style="bold red")
                    else:
                        console.print("[!] Verification failed. Pairing aborted.", style="bold red")
                        wait_for_key("Press any key to return...")
                        return

        elif choice == 1:
            console.print("\n[cyan]Listening for the next message... Send /start from the intended account.[/cyan]")
            time.sleep(1)
            continue
        else:
            return

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
        bot_token = tg_cfg.get("bot_token", "")
        chat_id = tg_cfg.get("allowed_chat_id", 0)
        backend = tg_cfg.get("backend", "serverless")
        webhook_url = tg_cfg.get("webhook_url", "")

        def draw_content():
            print_header("Telegram Offline OTP")
            
            table = Table(title="Telegram Offline OTP Configuration", expand=True)
            table.add_column("Setting", style="bold cyan", width=22)
            table.add_column("Value")
            
            if backend == "telegram_serverless":
                backend_label = "[bold green]TELEGRAM SERVERLESS (Official tgcloud.ai)[/bold green]"
                deploy_info = "telegram_backends/telegram_serverless  (npx tgcloud push)"
            elif backend in ("cloudflare", "serverless"):
                backend_label = "[bold green]EXTERNAL SERVERLESS (Cloudflare / Vercel)[/bold green]"
                deploy_info = "telegram_backends/cloudflare_worker or serverless_python"
            else:
                backend_label = "[bold blue]STANDALONE DAEMON (Local / VPS)[/bold blue]"
                deploy_info = "telegram_backends/standalone_bot/bot.py"

            table.add_row("Backend Architecture", backend_label)
            table.add_row("Deployment Target", deploy_info)
            if backend in ("cloudflare", "serverless"):
                table.add_row("Webhook URL", f"[dim]{webhook_url}[/dim]" if webhook_url else "[dim]Not registered (set via Option 4)[/dim]")
            elif backend == "telegram_serverless":
                table.add_row("Official Docs", "https://core.telegram.org/bots/serverless")
            table.add_row("Bot Token", f"{bot_token[:8]}..." if bot_token else "[yellow]UNSET[/yellow]")
            table.add_row("Allowed Chat ID", str(chat_id) if chat_id else "[yellow]UNSET[/yellow]")
            table.add_row("Shared Secret", f"[cyan]{secret}[/cyan]")
            table.add_row("Epoch Interval", f"{tg_cfg.get('interval_seconds', 300)} seconds (5 minutes)")
            console.print(table)
            
            sample_otp = generate_windowed_otp(secret)
            console.print(f"Sample Valid 7-Digit OTP for Current Window: [bold green]{sample_otp}[/bold green]")

        options = [
            ("Interactive Auto-Pairing Wizard (Zero Manual Chat ID)", "Automatically discovers your User ID & verifies with OTP challenge"),
            ("Automated Serverless Setup Wizard", "1-Click automated deployer for Telegram Serverless & Cloudflare"),
            ("Manual Bot Token & Chat ID Entry", "Manually type or update credentials without auto-pairing"),
            ("Select Backend Mode", "Choose between Telegram Serverless (tgcloud), Cloudflare, or Standalone"),
            ("Register / Update Serverless Webhook URL", "Link Telegram directly to your deployed Serverless function"),
            ("Test 7-Digit Offline OTP", "Verify a 7-digit OTP against the RTC epoch window"),
            ("Return to Previous Menu", "Go back to Multi-Factor Authentication menu")
        ]

        choice_idx = select_menu(
            options,
            default_index=0,
            title="Telegram Bot Options (Arrow Keys)",
            on_render_header=draw_content
        )

        if choice_idx == 0:
            render_telegram_pairing_wizard()
            config = load_config()
            tg_cfg = config.get("telegram", {})
            bot_token = tg_cfg.get("bot_token", "")
            chat_id = tg_cfg.get("allowed_chat_id", 0)
            backend = tg_cfg.get("backend", "serverless")
            webhook_url = tg_cfg.get("webhook_url", "")

        elif choice_idx == 1:
            render_serverless_wizard()
            config = load_config()
            tg_cfg = config.get("telegram", {})
            bot_token = tg_cfg.get("bot_token", "")
            chat_id = tg_cfg.get("allowed_chat_id", 0)
            backend = tg_cfg.get("backend", "serverless")
            webhook_url = tg_cfg.get("webhook_url", "")

        elif choice_idx == 2:
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
            sync_telegram_serverless_config()
            sync_cloudflare_worker_bundle()
            console.print("[+] Telegram credentials updated.", style="green")
            time.sleep(1)

        elif choice_idx == 3:
            def draw_backend_picker():
                print_header("Choose Backend Mode")

            picker_options = [
                ("Official Telegram Serverless (tgcloud.ai)", "Zero external accounts. Runs natively in Telegram V8 isolates via @BotFather"),
                ("External Serverless Webhook (Cloudflare / Vercel)", "Zero maintenance, free external edge functions"),
                ("Standalone Python Bot (Long-Polling Daemon)", "Runs continuously on private machine or VPS"),
                ("Cancel / Keep Current", "Return without changes")
            ]
            picked = select_menu(picker_options, title="Select Backend Architecture", on_render_header=draw_backend_picker)
            if picked == 0:
                tg_cfg["backend"] = "telegram_serverless"
                config["telegram"] = tg_cfg
                save_config(config)
                console.print("\n[+] Backend set to OFFICIAL TELEGRAM SERVERLESS (tgcloud.ai).", style="bold green")
                time.sleep(1)
            elif picked == 1:
                tg_cfg["backend"] = "serverless"
                config["telegram"] = tg_cfg
                save_config(config)
                console.print("\n[+] Backend set to EXTERNAL SERVERLESS (Cloudflare/Vercel).", style="bold green")
                time.sleep(1)
            elif picked == 2:
                tg_cfg["backend"] = "standalone"
                config["telegram"] = tg_cfg
                save_config(config)
                if bot_token and webhook_url:
                    delete_telegram_webhook(bot_token)
                console.print("\n[+] Backend set to STANDALONE DAEMON.", style="bold green")
                time.sleep(1)

        elif choice_idx == 4:
            bot_token = tg_cfg.get("bot_token", "")
            if not bot_token:
                console.print("\n[!] Please configure your Bot Token first.", style="bold red")
                time.sleep(1.5)
                continue

            current_url = tg_cfg.get("webhook_url", "")
            console.print("\nEnter your deployed Serverless Webhook URL:")
            console.print("[dim]Example: https://akergate-otp.workers.dev or https://your-app.vercel.app/api/webhook[/dim]")
            new_url = Prompt.ask("Webhook URL", default=current_url)

            if new_url:
                console.print("\n[*] Registering webhook with Telegram API...", style="cyan")
                ok, msg = set_telegram_webhook(bot_token, new_url)
                if ok:
                    tg_cfg["webhook_url"] = new_url
                    tg_cfg["backend"] = "serverless"
                    config["telegram"] = tg_cfg
                    save_config(config)
                    console.print(f"[+] Webhook registered successfully! {msg}", style="bold green")
                else:
                    console.print(f"[!] Failed to register webhook: {msg}", style="bold red")
                time.sleep(2)

        elif choice_idx == 5:
            test_code = Prompt.ask("\nEnter 7-digit Telegram OTP")
            valid, token_id = verify_windowed_otp(secret, test_code)
            if valid:
                console.print(f"[+] VALID OTP! Identified as: {token_id}", style="bold green")
            else:
                console.print("[!] Invalid OTP or expired epoch window.", style="bold red")
            wait_for_key("Press any key to return...")

        elif choice_idx == 6 or choice_idx == len(options) - 1:
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
# SUBMENU: MULTI-FACTOR AUTHENTICATION
# ─────────────────────────────────────────────────────────────────────────────
def render_mfa_menu():
    """Submenu for Multi-Factor Authentication: TOTP Credentials & Telegram OTP."""
    while True:
        def draw_mfa_header():
            print_header("Multi-Factor Authentication")
            secret = get_totp_secret()
            tg_configured = bool(get_telegram_secret())
            config = load_config()
            tg_cfg = config.get("telegram", {})

            table = Table(box=None, expand=True, padding=(0, 1))
            table.add_column("Factor", style="bold cyan", width=22)
            table.add_column("Status", style="bold", width=16)
            table.add_column("Details")

            totp_st = "[bold green]CONFIGURED[/bold green]" if secret else "[bold yellow]NOT CONFIGURED[/bold yellow]"
            totp_dt = f"Current Host TOTP: [bold green]{compute_totp(secret)}[/bold green]" if secret else "Scan QR code or generate secret"
            table.add_row("RFC 6238 TOTP", totp_st, totp_dt)

            tg_st = "[bold green]CONFIGURED[/bold green]" if tg_configured else "[bold yellow]NOT CONFIGURED[/bold yellow]"
            tg_dt = f"Chat ID: {tg_cfg.get('allowed_chat_id', 'unset')} | Backend: {tg_cfg.get('backend', 'cloudflare')}"
            table.add_row("Telegram Windowed OTP", tg_st, tg_dt)

            console.print(Panel(table, title="[bold]Authentication Factors[/bold]", border_style="cyan"))

        mfa_options = [
            ("Manage TOTP & Scan QR Code", "View phone QR code, Base32 secret, and test synchronization"),
            ("Telegram Bot & Offline OTP Settings", "Manage bot token, chat ID, backend, and verify 7-digit OTP"),
            ("Return to Dashboard", "Go back to main status dashboard")
        ]

        choice_idx = select_menu(
            mfa_options,
            default_index=0,
            title="Multi-Factor Authentication Options (Arrow Keys)",
            on_render_header=draw_mfa_header
        )

        if choice_idx == 0:
            render_totp_setup()
        elif choice_idx == 1:
            render_telegram_setup()
        elif choice_idx == 2 or choice_idx == len(mfa_options) - 1:
            break

# ─────────────────────────────────────────────────────────────────────────────
# SUBMENU: SECURITY CENTER & AUDITING
# ─────────────────────────────────────────────────────────────────────────────
def render_security_center_menu():
    """Submenu for Security Operations, Auditing, Lockdown, and System Info."""
    while True:
        def draw_sec_header():
            print_header("Security Center & Auditing")

        sec_options = [
            ("View Authentication Audit Logs", "Read authentication history, timestamps, and service results"),
            ("Sentry Alerts & Event Monitor", "Configure Telegram alerts for logins, failed attempts, and queue"),
            ("Emergency Quarantine & Lockdown", "Trigger, customize, or disarm host lockdown policies"),
            ("View Official Logo Banner", "Display two-tone typography banner and license details"),
            ("Return to Dashboard", "Go back to main status dashboard")
        ]

        choice_idx = select_menu(
            sec_options,
            default_index=0,
            title="Security Center & Monitoring Options (Arrow Keys)",
            on_render_header=draw_sec_header
        )

        if choice_idx == 0:
            render_audit_logs()
        elif choice_idx == 1:
            render_sentry_setup()
        elif choice_idx == 2:
            render_lockdown()
        elif choice_idx == 3:
            render_banner_screen()
        elif choice_idx == 4 or choice_idx == len(sec_options) - 1:
            break

# ─────────────────────────────────────────────────────────────────────────────
# MAIN TUI LOOP (Fully Keyboard-Driven with Arrow Keys)
# ─────────────────────────────────────────────────────────────────────────────
def main_tui():
    # Enter terminal alternate screen buffer (clean dedicated canvas)
    sys.stdout.write("\033[?1049h\033[H")
    sys.stdout.flush()
    try:
        while True:
            def draw_dash():
                print_header("Dashboard")
                render_dashboard()

            dash_options = [
                ("Multi-Factor Authentication", "Configure TOTP QR credentials, code verification, and Telegram OTP"),
                ("Protected Services & PAM", "Manage PAM rules for sudo, login, screensaver, sshd"),
                ("Security Center & Auditing", "View audit logs, sentry event monitor, emergency lockdown, and info"),
                ("Quit AkerGate Console", "Close interactive terminal user interface")
            ]

            choice_idx = select_menu(
                dash_options,
                default_index=0,
                title="AkerGate Main Navigation (Arrow Keys)",
                on_render_header=draw_dash,
                allow_cancel=False
            )

            if choice_idx == 0:
                render_mfa_menu()
            elif choice_idx == 1:
                render_services()
            elif choice_idx == 2:
                render_security_center_menu()
            elif choice_idx == 3 or choice_idx == len(dash_options) - 1:
                break
    finally:
        # Restore normal terminal screen buffer and ensure cursor is visible
        sys.stdout.write("\033[?1049l\033[?25h")
        sys.stdout.flush()

if __name__ == "__main__":
    main_tui()

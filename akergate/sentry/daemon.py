"""
AkerGate Sentry - Background Daemon
Continuously monitors system sessions, login attempts, and drains the offline queue.
Zero external dependencies.
"""

import time
import signal
import sys
import subprocess
import json
from akergate.config import load_config, get_events_log_file
from akergate.sentry.queue_manager import flush_offline_queue
from akergate.sentry.notifier import send_telegram_alert, is_network_available
from akergate.core.lockdown import trigger_lockdown, is_lockdown_active

running = True

def handle_signal(sig, frame):
    global running
    running = False

def check_brute_force_threshold(max_failures: int = 5, window_seconds: int = 120) -> bool:
    """
    Scans the events log for rapid consecutive authentication failures.
    Returns True if threshold is breached.
    """
    log_file = get_events_log_file()
    if not log_file.exists():
        return False
        
    now = time.time()
    recent_failures = 0
    try:
        lines = log_file.read_text(encoding="utf-8").strip().splitlines()[-20:]
        for line in reversed(lines):
            try:
                ev = json.loads(line)
                if ev.get("event_type") == "auth_failure":
                    if (now - ev.get("timestamp", 0)) <= window_seconds:
                        recent_failures += 1
                        if recent_failures >= max_failures:
                            return True
                    else:
                        break
                elif ev.get("event_type") == "auth_success":
                    break
            except Exception:
                continue
    except Exception:
        pass
    return False

def get_active_sessions() -> set:
    """Returns set of active user sessions via who/loginctl."""
    sessions = set()
    try:
        res = subprocess.run(["who"], capture_output=True, text=True, timeout=5)
        for line in res.stdout.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                sessions.add((parts[0], parts[1]))
    except Exception:
        pass
    return sessions

def run_sentry_daemon():
    """Main loop for AkerGate Sentry Daemon."""
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    
    known_sessions = get_active_sessions()
    
    print("[+] AkerGate Sentry Daemon initialized.")
    
    while running:
        config = load_config()
        sentry_cfg = config.get("sentry", {})
        
        # 1. Brute-force detection & Auto-lockdown
        if not is_lockdown_active():
            if check_brute_force_threshold(max_failures=5, window_seconds=120):
                print("[!] Brute-force threshold breached! Triggering emergency lockdown...")
                ok, report_path = trigger_lockdown(policy="dual_totp", trigger_source="brute_force")
                alert_text = (
                    "*[!] CRITICAL ALERT: AUTOMATIC LOCKDOWN TRIGGERED*\n"
                    "────────────────────────\n"
                    "• Trigger: Brute-Force threshold exceeded (5 failed logins)\n"
                    "• Policy: Dual Consecutive TOTP\n"
                    f"• Time: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                    "• Status: Host sessions locked & quarantined\n"
                    "────────────────────────\n"
                    "Forensic snapshot generated. Recovery requires 2 consecutive TOTP codes."
                )
                if is_network_available():
                    send_telegram_alert(alert_text, config)
                else:
                    # Queue for sending when online
                    from akergate.core.storage import log_event
                    log_event("emergency_lockdown", "system", "sentry", "brute_force", False, extra="auto_lockdown")

        if not sentry_cfg.get("enabled", True):
            time.sleep(10)
            continue
            
        check_interval = sentry_cfg.get("check_interval_seconds", 15)
        
        # 2. Flush any pending offline queue items
        flush_offline_queue()
        
        # 2. Check for newly opened sessions if enabled
        if sentry_cfg.get("notify_on_session", False):
            current_sessions = get_active_sessions()
            new_sessions = current_sessions - known_sessions
            if new_sessions and is_network_available():
                for user, tty in new_sessions:
                    msg = (
                        "*[+] NEW SESSION OPENED*\n"
                        "────────────────────────\n"
                        f"• User: `{user}`\n"
                        f"• TTY/Display: `{tty}`\n"
                        f"• Time: `{time.strftime('%Y-%m-%d %H:%M:%S')}`\n"
                        "────────────────────────"
                    )
                    send_telegram_alert(msg, config)
            known_sessions = current_sessions
            
        # Sleep in small increments to be responsive to termination
        for _ in range(check_interval):
            if not running:
                break
            time.sleep(1)
            
    print("[*] AkerGate Sentry Daemon terminated gracefully.")

if __name__ == "__main__":
    run_sentry_daemon()

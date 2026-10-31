"""
AkerGate Sentry - Background Daemon
Continuously monitors system sessions, login attempts, and drains the offline queue.
Zero external dependencies.
"""

import time
import signal
import sys
import subprocess
from akergate.config import load_config
from akergate.sentry.queue_manager import flush_offline_queue
from akergate.sentry.notifier import send_telegram_alert, is_network_available

running = True

def handle_signal(sig, frame):
    global running
    running = False

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
        
        if not sentry_cfg.get("enabled", True):
            time.sleep(10)
            continue
            
        check_interval = sentry_cfg.get("check_interval_seconds", 15)
        
        # 1. Flush any pending offline queue items
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

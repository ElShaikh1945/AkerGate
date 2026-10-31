"""
AkerGate Sentry - Offline Queue Manager
Safely stores authentication alerts while host is offline and flushes them when internet returns.
Zero external dependencies.
"""

import json
import fcntl
from akergate.config import get_offline_queue_file, load_config
from akergate.sentry.notifier import is_network_available, send_telegram_alert, format_event_message

def flush_offline_queue() -> int:
    """
    Checks for pending offline alerts.
    If network is reachable, sends them in sequence to Telegram and drains the queue.
    Returns number of flushed messages.
    """
    queue_file = get_offline_queue_file()
    if not queue_file.exists():
        return 0
        
    if not is_network_available():
        return 0
        
    config = load_config()
    sentry_cfg = config.get("sentry", {})
    if not sentry_cfg.get("enabled", True):
        return 0
        
    flushed_count = 0
    remaining_events = []
    
    try:
        with open(queue_file, "r+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                lines = f.readlines()
                for line in lines:
                    line_str = line.strip()
                    if not line_str:
                        continue
                    try:
                        event = json.loads(line_str)
                    except Exception:
                        continue
                        
                    event_type = event.get("event_type", "")
                    notify_on_login = sentry_cfg.get("notify_on_login", True)
                    notify_on_failed = sentry_cfg.get("notify_on_failed", True)
                    
                    should_send = False
                    if event_type == "auth_success" and notify_on_login:
                        should_send = True
                    elif event_type == "auth_failure" and notify_on_failed:
                        should_send = True
                        
                    if should_send:
                        msg = format_event_message(event)
                        sent = send_telegram_alert(msg, config)
                        if sent:
                            flushed_count += 1
                        else:
                            # Network dropped or Telegram API error, keep remaining
                            remaining_events.append(line_str)
                            
                f.seek(0)
                if remaining_events:
                    f.write("\n".join(remaining_events) + "\n")
                f.truncate()
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass
        
    return flushed_count

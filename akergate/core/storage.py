"""
AkerGate - Secure Storage & Token Burning Engine
Handles atomic file locking, anti-replay burned tokens, and event logging.
Zero external dependencies.
"""

import os
import json
import time
import fcntl
from pathlib import Path
from akergate.config import (
    get_burned_tokens_file,
    get_events_log_file,
    get_offline_queue_file,
    get_totp_secret_file,
    get_telegram_secret_file,
    is_root
)

def read_secret(file_path: Path) -> str:
    """Safely reads a secret key from disk."""
    if not file_path.exists():
        return ""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except Exception:
        return ""

def write_secret(file_path: Path, secret: str) -> bool:
    """Safely writes a secret key to disk with 0600 permissions."""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(secret.strip())
        if is_root():
            os.chmod(file_path, 0o600)
        return True
    except Exception:
        return False

def get_totp_secret() -> str:
    return read_secret(get_totp_secret_file())

def set_totp_secret(secret: str) -> bool:
    return write_secret(get_totp_secret_file(), secret)

def get_telegram_secret() -> str:
    return read_secret(get_telegram_secret_file())

def set_telegram_secret(secret: str) -> bool:
    return write_secret(get_telegram_secret_file(), secret)

def is_token_burned(token_id: str) -> bool:
    """Checks if a token identifier has already been consumed/burned."""
    burned_file = get_burned_tokens_file()
    if not burned_file.exists():
        return False
        
    try:
        with open(burned_file, "r", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_SH)
            try:
                data = json.load(f)
                return token_id in data
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        return False

def burn_token(token_id: str, retention_seconds: int = 86400) -> bool:
    """
    Atomically records a token as burned.
    Also purges entries older than retention_seconds (default 24h).
    """
    burned_file = get_burned_tokens_file()
    burned_file.parent.mkdir(parents=True, exist_ok=True)
    
    now = time.time()
    try:
        mode = "r+" if burned_file.exists() else "w+"
        with open(burned_file, mode, encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            try:
                if mode == "r+":
                    try:
                        data = json.load(f)
                    except Exception:
                        data = {}
                else:
                    data = {}
                    
                # Clean up expired entries
                cleaned = {k: v for k, v in data.items() if (now - v) < retention_seconds}
                
                # Mark current token as burned
                cleaned[token_id] = now
                
                f.seek(0)
                json.dump(cleaned, f)
                f.truncate()
                return True
            finally:
                fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        return False

def log_event(event_type: str, user: str, service: str, method: str, success: bool, extra: str = ""):
    """
    Appends an authentication event to local log and the offline sentry queue.
    """
    log_file = get_events_log_file()
    queue_file = get_offline_queue_file()
    
    log_file.parent.mkdir(parents=True, exist_ok=True)
    queue_file.parent.mkdir(parents=True, exist_ok=True)
    
    event = {
        "timestamp": int(time.time()),
        "iso_time": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
        "event_type": event_type,
        "user": user,
        "service": service,
        "method": method,
        "success": success,
        "extra": extra
    }
    
    entry_line = json.dumps(event) + "\n"
    
    # 1. Append to permanent log file
    try:
        with open(log_file, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(entry_line)
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass
        
    # 2. Append to offline sentry queue for Telegram notification
    try:
        with open(queue_file, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(entry_line)
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception:
        pass

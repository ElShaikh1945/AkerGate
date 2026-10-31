"""
AkerGate - Configuration and Environment Settings
Handles paths, constants, and system configurations.
"""

import os
import sys
import json
from pathlib import Path

# Application metadata
APP_NAME = "AkerGate"
APP_VERSION = "0.1.0"
AUTHOR = "Yuki"

# System Paths (Root mode)
SYSTEM_CONFIG_DIR = Path("/etc/akergate")
SYSTEM_DATA_DIR = Path("/var/lib/akergate")
SYSTEM_LOG_DIR = Path("/var/log/akergate")

# User Fallback Paths (Development or dry-run testing mode)
USER_CONFIG_DIR = Path.home() / ".config" / "akergate"
USER_DATA_DIR = Path.home() / ".local" / "share" / "akergate"
USER_LOG_DIR = Path.home() / ".local" / "state" / "akergate"

def is_root() -> bool:
    """Check if current process has root privileges."""
    return os.geteuid() == 0

def get_config_dir() -> Path:
    """Returns active config directory based on privileges."""
    if is_root():
        return SYSTEM_CONFIG_DIR
    return USER_CONFIG_DIR

def get_data_dir() -> Path:
    """Returns active data directory based on privileges."""
    if is_root():
        return SYSTEM_DATA_DIR
    return USER_DATA_DIR

def get_log_dir() -> Path:
    """Returns active log directory based on privileges."""
    if is_root():
        return SYSTEM_LOG_DIR
    return USER_LOG_DIR

def get_config_file() -> Path:
    return get_config_dir() / "config.json"

def get_totp_secret_file() -> Path:
    return get_config_dir() / "totp_secret.key"

def get_telegram_secret_file() -> Path:
    return get_config_dir() / "telegram_secret.key"

def get_burned_tokens_file() -> Path:
    return get_data_dir() / "burned_tokens.json"

def get_events_log_file() -> Path:
    return get_log_dir() / "events.jsonl"

def get_offline_queue_file() -> Path:
    return get_data_dir() / "offline_queue.jsonl"

# Default Configuration Dictionary
DEFAULT_CONFIG = {
    "version": APP_VERSION,
    "services": {
        "sudo": True,
        "screensaver": True,
        "login": True,
        "sshd": False
    },
    "totp": {
        "enabled": True,
        "interval_seconds": 30,
        "window": 1,
        "issuer": "AkerGate"
    },
    "telegram": {
        "enabled": True,
        "backend": "cloudflare",  # "cloudflare" or "standalone"
        "interval_seconds": 300,  # 5 minutes window for offline validation
        "window": 1,              # +/- 1 window (allows current and previous)
        "bot_token": "",
        "allowed_chat_id": 0,
        "worker_url": ""
    },
    "sentry": {
        "enabled": True,
        "notify_on_login": True,
        "notify_on_failed": True,
        "notify_on_session": False,
        "check_interval_seconds": 15
    },
    "failsafe": {
        "rollback_timeout_seconds": 30,
        "backup_dir": "/etc/akergate/pam_backups"
    }
}

def load_config() -> dict:
    """Loads configuration safely with fallback defaults."""
    cfg_file = get_config_file()
    if cfg_file.exists():
        try:
            with open(cfg_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                config = DEFAULT_CONFIG.copy()
                config.update(loaded)
                return config
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()

def save_config(config: dict) -> bool:
    """Saves configuration to disk with secure permissions."""
    cfg_dir = get_config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = get_config_file()
    
    try:
        with open(cfg_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        if is_root():
            os.chmod(cfg_file, 0o600)
        return True
    except Exception:
        return False

def ensure_directories():
    """Ensure required directories exist with secure permissions."""
    c_dir = get_config_dir()
    d_dir = get_data_dir()
    l_dir = get_log_dir()
    
    for d in (c_dir, d_dir, l_dir):
        d.mkdir(parents=True, exist_ok=True)
        if is_root():
            os.chmod(d, 0o700)

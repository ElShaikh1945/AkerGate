"""
AkerGate Sentry - Telegram Notifier
Sends structured security alerts and notifications to the owner on Telegram.
Zero emojis, clean symbols only.
"""

import json
import socket
import urllib.request
import urllib.error
from akergate.config import load_config

def is_network_available(timeout: int = 3) -> bool:
    """Checks if external internet is reachable."""
    try:
        # Check connection to Cloudflare or Google DNS
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.connect(("1.1.1.1", 53))
        return True
    except Exception:
        return False

def send_telegram_alert(text: str, config: dict = None) -> bool:
    """Sends a raw Markdown message to the configured Telegram chat."""
    if config is None:
        config = load_config()
        
    tg_cfg = config.get("telegram", {})
    bot_token = tg_cfg.get("bot_token", "")
    chat_id = tg_cfg.get("allowed_chat_id", 0)
    
    if not bot_token or not chat_id:
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except Exception:
        return False

def format_event_message(event: dict) -> str:
    """Formats an event dictionary into a clean Markdown notification."""
    hostname = socket.gethostname()
    event_type = event.get("event_type", "unknown")
    user = event.get("user", "unknown")
    service = event.get("service", "unknown")
    method = event.get("method", "unknown")
    iso_time = event.get("iso_time", "unknown")
    success = event.get("success", False)
    
    if success:
        status_tag = "[+] AUTHENTICATION SUCCESS"
        method_desc = {
            "totp": "Offline TOTP Code",
            "telegram_otp": "One-Time Telegram OTP",
            "password": "Master Password",
            "unknown": "System Verified"
        }.get(method, method)
    else:
        status_tag = "[!] AUTHENTICATION FAILED"
        method_desc = "Invalid Credential / Replay Attempt"

    lines = [
        f"*{status_tag}*",
        f"────────────────────────",
        f"• Host: `{hostname}`",
        f"• User: `{user}`",
        f"• Service: `{service}`",
        f"• Method: `{method_desc}`",
        f"• Time: `{iso_time}`",
        f"────────────────────────"
    ]
    
    return "\n".join(lines)

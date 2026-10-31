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

def set_telegram_webhook(bot_token: str, webhook_url: str) -> tuple[bool, str]:
    """Registers a serverless webhook URL with Telegram Bot API."""
    if not bot_token or not webhook_url:
        return False, "Missing bot token or webhook URL."
    url = f"https://api.telegram.org/bot{bot_token}/setWebhook"
    payload = {"url": webhook_url}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if res_data.get("ok"):
                return True, res_data.get("description", "Webhook registered successfully.")
            return False, res_data.get("description", "Failed to register webhook.")
    except Exception as e:
        return False, str(e)

def get_telegram_webhook_info(bot_token: str) -> dict:
    """Fetches the current webhook registration status from Telegram."""
    if not bot_token:
        return {}
    url = f"https://api.telegram.org/bot{bot_token}/getWebhookInfo"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return data.get("result", {})
    except Exception:
        pass
    return {}

def delete_telegram_webhook(bot_token: str) -> tuple[bool, str]:
    """Deletes the registered webhook to enable standalone long-polling mode."""
    if not bot_token:
        return False, "Missing bot token."
    url = f"https://api.telegram.org/bot{bot_token}/deleteWebhook"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                return True, data.get("description", "Webhook removed.")
            return False, data.get("description", "Failed to delete webhook.")
    except Exception as e:
        return False, str(e)

def set_telegram_bot_commands(bot_token: str) -> tuple[bool, str]:
    """
    Registers the command palette and menu button with Telegram Bot API.
    Enables instant interactive popup suggestions when user types '/'.
    """
    if not bot_token:
        return False, "Missing bot token."

    commands = [
        {"command": "otp", "description": "Generate 7-digit AkerGate OTP code"},
        {"command": "status", "description": "Check timing & window synchronization"},
        {"command": "help", "description": "Show commands list and info"},
        {"command": "start", "description": "Initialize AkerGate bot session"}
    ]

    try:
        # 1. Register commands list
        cmd_url = f"https://api.telegram.org/bot{bot_token}/setMyCommands"
        cmd_payload = {"commands": commands}
        cmd_data = json.dumps(cmd_payload).encode("utf-8")
        cmd_req = urllib.request.Request(cmd_url, data=cmd_data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(cmd_req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if not res_data.get("ok"):
                return False, res_data.get("description", "Failed to register commands.")

        # 2. Reset Chat Menu Button to default (clean '/' icon only, no 'Menu' text label)
        menu_url = f"https://api.telegram.org/bot{bot_token}/setChatMenuButton"
        menu_payload = {"menu_button": {"type": "default"}}
        menu_data = json.dumps(menu_payload).encode("utf-8")
        menu_req = urllib.request.Request(menu_url, data=menu_data, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(menu_req, timeout=10) as resp2:
                pass
        except Exception:
            pass

        return True, "Bot commands and menu button registered successfully."
    except Exception as e:
        return False, str(e)

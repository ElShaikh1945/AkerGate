"""
AkerGate - Interactive Telegram Auto-Pairing Engine
Automatically detects incoming user messages to discover Chat ID without manual input.
Dispatches a 2-way verification OTP code to confirm identity.
Zero external dependencies. Zero emojis.
"""

import time
import json
import secrets
import urllib.request
import urllib.error
from typing import Tuple, Dict, Any, Optional

def validate_bot_token(bot_token: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Validates bot token against Telegram Bot API getMe endpoint.
    Returns (is_valid, message, bot_info_dict).
    """
    token = bot_token.strip()
    if not token or ":" not in token:
        return False, "Invalid token format. Token must be in format <id>:<hash>.", {}

    url = f"https://api.telegram.org/bot{token}/getMe"
    req = urllib.request.Request(url, headers={"User-Agent": "AkerGate-Engine/0.1.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                result = data.get("result", {})
                username = result.get("username", "UnknownBot")
                first_name = result.get("first_name", "Bot")
                return True, f"@{username} ({first_name})", result
            return False, data.get("description", "Bot token rejected by Telegram."), {}
    except urllib.error.HTTPError as e:
        if e.code == 401 or e.code == 404:
            return False, "Unauthorized token. Please verify the token from @BotFather.", {}
        return False, f"Telegram API error (HTTP {e.code}).", {}
    except Exception as e:
        return False, f"Network connection failed: {e}", {}

def listen_for_incoming_user(
    bot_token: str,
    timeout_seconds: int = 60,
    poll_callback: Optional[callable] = None
) -> Tuple[bool, Optional[Dict[str, Any]], str]:
    """
    Listens for incoming messages via getUpdates to discover the sender's Chat ID.
    Temporarily clears any conflicting webhook so getUpdates works.
    Returns (success, user_details_dict, message).
    """
    token = bot_token.strip()

    # Clear webhook if any so getUpdates polling is permitted
    del_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
    try:
        req = urllib.request.Request(del_url, headers={"User-Agent": "AkerGate-Engine/0.1.0"})
        urllib.request.urlopen(req, timeout=5)
    except Exception:
        pass

    start_time = time.time()
    offset = 0

    # First fast drain to skip stale past messages
    try:
        drain_url = f"https://api.telegram.org/bot{token}/getUpdates?offset=-1&timeout=0"
        with urllib.request.urlopen(drain_url, timeout=5) as resp:
            d_data = json.loads(resp.read().decode("utf-8"))
            if d_data.get("ok") and d_data.get("result"):
                offset = d_data["result"][-1]["update_id"] + 1
    except Exception:
        pass

    while time.time() - start_time < timeout_seconds:
        elapsed = int(time.time() - start_time)
        remaining = timeout_seconds - elapsed

        if poll_callback:
            poll_callback(remaining)

        poll_url = f"https://api.telegram.org/bot{token}/getUpdates?offset={offset}&timeout=3"
        try:
            req = urllib.request.Request(poll_url, headers={"User-Agent": "AkerGate-Engine/0.1.0"})
            with urllib.request.urlopen(req, timeout=6) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if data.get("ok"):
                updates = data.get("result", [])
                for upd in updates:
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or upd.get("edited_message")
                    if msg:
                        sender = msg.get("from", {})
                        chat = msg.get("chat", {})
                        user_id = sender.get("id") or chat.get("id")
                        if user_id:
                            return True, {
                                "user_id": user_id,
                                "first_name": sender.get("first_name", "User"),
                                "last_name": sender.get("last_name", ""),
                                "username": sender.get("username", ""),
                                "text": msg.get("text", ""),
                                "update_id": upd["update_id"]
                            }, "Message received successfully."

        except Exception:
            time.sleep(1)

        time.sleep(1)

    return False, None, "Listening timed out with no incoming message detected."

def dispatch_pairing_otp(bot_token: str, chat_id: int) -> Tuple[bool, str, str]:
    """
    Generates a secure 6-digit confirmation OTP and sends it to the user's Telegram.
    Returns (success, otp_code, message).
    """
    token = bot_token.strip()
    otp_code = f"{secrets.randbelow(900000) + 100000}"

    text = (
        "*[+] AKERGATE HOST PAIRING VERIFICATION*\n"
        "────────────────────────\n"
        f"Your One-Time Pairing Code is: `{otp_code}`\n"
        "────────────────────────\n"
        "• Enter this code into your Linux terminal to complete setup\n"
        "• This confirms two-way communication between Host and Telegram"
    )

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})

    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if res.get("ok"):
                return True, otp_code, "Verification OTP dispatched to Telegram."
            return False, "", res.get("description", "Failed to send Telegram message.")
    except Exception as e:
        return False, "", str(e)

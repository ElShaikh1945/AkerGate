"""
AkerGate - Universal Serverless Python Telegram Webhook
Deployable on Vercel, AWS Lambda, Google Cloud Functions, or any HTTP serverless platform.
Responds instantly to Telegram webhooks with zero idle compute cost.
Zero emojis, clean symbols only.
"""

import os
import sys
import time
import json
import base64
import hmac
import hashlib
import struct
import urllib.request

BOT_TOKEN = os.environ.get("AKERGATE_BOT_TOKEN", "")
ALLOWED_CHAT_ID = int(os.environ.get("AKERGATE_ALLOWED_CHAT_ID", "0"))
SHARED_SECRET = os.environ.get("AKERGATE_SHARED_SECRET", "")
INTERVAL_SECONDS = int(os.environ.get("AKERGATE_INTERVAL", "300"))

def base32_decode(secret: str) -> bytes:
    """Decode standard Base32 secret with auto-padding."""
    s = secret.strip().upper().replace(" ", "")
    missing_padding = len(s) % 8
    if missing_padding:
        s += "=" * (8 - missing_padding)
    return base64.b32decode(s, casefold=True)

def generate_windowed_otp(secret: str, slot: int = 0, timestamp: float = None, interval: int = 300) -> str:
    """Calculates 7-digit windowed OTP matching AkerGate Core engine."""
    if timestamp is None:
        timestamp = time.time()
    counter = int(timestamp // interval)
    key_bytes = base32_decode(secret)
    msg = struct.pack(">QQ", counter, slot)
    digest = hmac.new(key_bytes, msg, hashlib.sha256).digest()
    offset = digest[19] & 0x0F
    code_bin = struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF
    code_6 = f"{code_bin % 1000000:06d}"
    return f"{slot}{code_6}"

def send_telegram_reply(chat_id: int, text: str):
    """Sends a Markdown-formatted reply to Telegram."""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[!] Error sending Telegram reply: {e}")

def handle_webhook_update(update: dict) -> dict:
    """Process incoming Telegram update dictionary and generate response."""
    msg = update.get("message", {})
    sender_id = msg.get("from", {}).get("id", 0)
    chat_id = msg.get("chat", {}).get("id", 0)
    text = (msg.get("text", "") or "").strip().lower()

    if not text:
        return {"status": "ok"}

    # Strict authorization check
    if sender_id != ALLOWED_CHAT_ID:
        send_telegram_reply(chat_id, "*[!] Access Denied*\nYou are not authorized to access this AkerGate node.")
        return {"status": "unauthorized"}

    now = time.time()
    seconds_left = INTERVAL_SECONDS - int(now % INTERVAL_SECONDS)

    if text in ("/start", "/help"):
        welcome = (
            "*[+] AKERGATE SERVERLESS OTP BOT*\n"
            "────────────────────────\n"
            "• `/otp` or `/code` : Generate your 7-digit offline OTP\n"
            "• `/status` : Check engine timing and epoch interval\n"
            "• `/help` : Show this commands list\n"
            "────────────────────────\n"
            f"Epoch Window: `{INTERVAL_SECONDS} seconds`\n"
            f"Next Rotation: `in {seconds_left}s`"
        )
        send_telegram_reply(chat_id, welcome)

    elif text in ("/otp", "/code", "otp", "code"):
        import random
        slot = random.randint(0, 9)
        code = generate_windowed_otp(SHARED_SECRET, slot=slot, timestamp=now, interval=INTERVAL_SECONDS)
        reply = (
            "*[+] AKERGATE AUTHENTICATION OTP*\n"
            "────────────────────────\n"
            f"Your 7-Digit Code: `{code}`\n"
            "────────────────────────\n"
            f"• Window Slot: `[{slot}]`\n"
            f"• Expires in: `{seconds_left} seconds`\n"
            "• Valid for PAM authentication elevation"
        )
        send_telegram_reply(chat_id, reply)

    elif text == "/status":
        status_msg = (
            "*[+] AKERGATE SERVERLESS STATUS*\n"
            "────────────────────────\n"
            f"• Host Epoch Interval: `{INTERVAL_SECONDS}s`\n"
            f"• Time to Window Change: `{seconds_left}s`\n"
            "• Backend: Universal Serverless Python\n"
            "• State: Active & Synchronized\n"
            "────────────────────────"
        )
        send_telegram_reply(chat_id, status_msg)

    return {"status": "ok"}

# AWS Lambda / Vercel entrypoint
def lambda_handler(event, context):
    try:
        body = event.get("body", "{}")
        if isinstance(body, str):
            update = json.loads(body)
        else:
            update = body
        handle_webhook_update(update)
        return {"statusCode": 200, "body": json.dumps({"ok": True})}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"error": str(e)})}

#!/usr/bin/env python3
"""
AkerGate - Standalone Telegram Bot Daemon
Can be hosted on any remote VPS, server, or container.
Generates offline-compatible 7-digit OTPs synchronized with host RTC.
Zero emojis, clean symbols only.
"""

import os
import sys
import time
import json
import urllib.request
import urllib.parse
from akergate.core.windowed_otp import generate_windowed_otp

BOT_TOKEN = os.environ.get("AKERGATE_BOT_TOKEN", "")
ALLOWED_CHAT_ID = int(os.environ.get("AKERGATE_ALLOWED_CHAT_ID", "0"))
SHARED_SECRET = os.environ.get("AKERGATE_SHARED_SECRET", "")
INTERVAL_SECONDS = int(os.environ.get("AKERGATE_INTERVAL", "300"))

def send_message(chat_id: int, text: str):
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
        print(f"[!] Error sending message: {e}")

def main():
    if not BOT_TOKEN or not ALLOWED_CHAT_ID or not SHARED_SECRET:
        print("[!] Missing required environment variables:")
        print("    - AKERGATE_BOT_TOKEN")
        print("    - AKERGATE_ALLOWED_CHAT_ID")
        print("    - AKERGATE_SHARED_SECRET")
        sys.exit(1)

    print("[+] AkerGate Standalone Bot listening...")
    offset = 0

    while True:
        try:
            url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates?offset={offset}&timeout=30"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=40) as resp:
                data = json.loads(resp.read().decode("utf-8"))

            if not data.get("ok"):
                time.sleep(2)
                continue

            for update in data.get("result", []):
                offset = update["update_id"] + 1
                msg = update.get("message", {})
                sender = msg.get("from", {})
                user_id = sender.get("id")
                chat_id = msg.get("chat", {}).get("id")
                text = msg.get("text", "").strip()

                if user_id != ALLOWED_CHAT_ID:
                    continue

                if text in ("/start", "/help"):
                    welcome = (
                        "*AkerGate - Remote Authentication Bot*\n"
                        "────────────────────────\n"
                        "Commands:\n"
                        "• `/otp` : Generate a 7-digit temporary access code\n"
                        "• `/status` : Check backend status and timing\n"
                        "────────────────────────\n"
                        "AkerGate protects your Linux host even when offline."
                    )
                    send_message(chat_id, welcome)

                elif text.startswith("/otp") or text in ("otp", "code"):
                    otp = generate_windowed_otp(SHARED_SECRET, interval=INTERVAL_SECONDS)
                    minutes = INTERVAL_SECONDS // 60
                    reply = (
                        "*[+] AkerGate One-Time Passcode*\n"
                        "────────────────────────\n"
                        f"• Passcode: `{otp}`\n"
                        f"• Epoch Validity: ~{minutes} Minutes\n"
                        "• Single-use: Burns immediately upon entry\n"
                        "────────────────────────\n"
                        "Type this code into the password prompt on your PC."
                    )
                    send_message(chat_id, reply)

                elif text == "/status":
                    now = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
                    status = (
                        "*[i] AkerGate Backend Status*\n"
                        "────────────────────────\n"
                        "• Status: Operational (Standalone VPS)\n"
                        f"• Time: `{now}`\n"
                        f"• Interval: {INTERVAL_SECONDS}s\n"
                        "────────────────────────"
                    )
                    send_message(chat_id, status)

        except Exception as e:
            time.sleep(3)

if __name__ == "__main__":
    main()

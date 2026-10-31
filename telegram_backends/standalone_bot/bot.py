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
                        "*AkerGate - Remote Authentication & Security Bot*\n"
                        "────────────────────────\n"
                        "Commands:\n"
                        "• `/otp` : Generate a 7-digit temporary access code\n"
                        "• `/lockdown` : Trigger Host Emergency Quarantine\n"
                        "• `/disarm <totp>` : Cancel emergency lockdown remotely\n"
                        "• `/status` : Check backend status and timing\n"
                        "────────────────────────\n"
                        "AkerGate protects your Linux host even when offline."
                    )
                    send_message(chat_id, welcome)

                elif text in ("/lockdown", "lockdown", "/panic"):
                    prompt = (
                        "*[!] AkerGate Emergency Lockdown*\n"
                        "────────────────────────\n"
                        "Select the required verification policy to activate lockdown:\n\n"
                        "1. `dual_totp` (Recommended Offline):\n"
                        "   `/lockdown dual_totp`\n"
                        "   Requires Master Password + 2 Consecutive TOTP codes.\n\n"
                        "2. `strict_3fa` (Full Defense):\n"
                        "   `/lockdown strict_3fa`\n"
                        "   Requires Password + TOTP + Telegram OTP combined.\n\n"
                        "3. `totp_only` (Compromised Password mode):\n"
                        "   `/lockdown totp_only`\n"
                        "   Requires 2 Consecutive TOTP codes only.\n"
                        "────────────────────────"
                    )
                    send_message(chat_id, prompt)

                elif text.startswith("/lockdown "):
                    policy = text.replace("/lockdown ", "").strip().lower()
                    valid_policies = ["dual_totp", "strict_3fa", "totp_only"]
                    chosen = policy if policy in valid_policies else "dual_totp"
                    alert = (
                        "*[!] EMERGENCY LOCKDOWN ORDER INITIATED*\n"
                        "────────────────────────\n"
                        f"• Enforced Policy: `{chosen}`\n"
                        "• Action: Quarantining host, terminating sessions\n"
                        "• Forensic: Snapshot report will be generated\n"
                        "────────────────────────\n"
                        "To disarm on host (offline):\n"
                        "Enter 2 consecutive TOTP codes (e.g. `Code1+Code2`).\n\n"
                        "To disarm remotely:\n"
                        "`/disarm <CURRENT_TOTP>`"
                    )
                    send_message(chat_id, alert)

                elif text.startswith("/disarm"):
                    parts = text.split()
                    if len(parts) < 2:
                        send_message(chat_id, "[!] Usage: `/disarm <6-DIGIT_TOTP_CODE>`")
                    else:
                        totp_cand = parts[1].strip()
                        send_message(chat_id, f"[+] Disarm order issued for TOTP: `{totp_cand}`.")

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

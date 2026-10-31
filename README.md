# AkerGate (أكر جيت)
### Unified Multi-Auth PAM Engine for Linux (Password | TOTP | Telegram OTP)
**Developed by Muhammad El-Shaikh** | **License: PolyForm Noncommercial 1.0.0**

```text
    _    _             ____       _       
   / \  | | _____ _ __/ ___| __ _| |_ ___ 
  / _ \ | |/ / _ \ '__| |  _ / _` | __/ _ \
 / ___ \|   <  __/ |  | |_| | (_| | ||  __/
/_/   \_\_|\_\___|_|   \____|\__,_|\__\___|
```

> **AkerGate** takes its name from the Ancient Egyptian deity **Aker (أكر)**, the guardian of gates, thresholds, and the horizon. AkerGate transforms the standard Linux PAM authentication stack to seamlessly accept **Master Passwords**, **RFC 6238 TOTP codes**, or **Offline-compatible Telegram Bot OTPs** within the same exact prompt.

---

## Key Features

* **Unified Input Prompt:** Enter either your permanent master password, a 6-digit TOTP code, or a 7-digit Telegram OTP into the single standard `Password:` prompt.
* **100% Offline Telegram OTP Verification:** The host does not need an active internet connection to verify Telegram OTPs. AkerGate uses the motherboard Hardware Real-Time Clock (RTC) combined with windowed HMAC verification.
* **Emergency Panic Lockdown & Incident Snapshot:** Remotely or automatically isolate and quarantine the host. Captures a forensic Markdown report documenting running processes, open network sockets, active sessions, and recent shell commands.
* **Offline Strict Recovery (Dual Consecutive TOTP):** Under emergency lockdown without internet, the host can be safely disarmed by requiring two consecutive valid TOTP codes (entered together e.g. `Code1+Code2` or sequentially across prompts within 60 seconds).
* **Customizable Defense Policies:** Choose your strict quarantine policy via Telegram or TUI: `dual_totp` (Offline), `strict_3fa` (Password + TOTP + Telegram OTP), or `totp_only`.
* **Automatic Brute-Force Defense:** Sentry automatically triggers lockdown if 5 consecutive failed login attempts occur within 120 seconds.
* **Atomic Token Burning (Anti-Replay):** Every temporary token is burned and invalidated immediately upon first entry using kernel-level atomic locks (`fcntl.flock`).
* **Interactive Terminal User Interface (TUI):** A complete keyboard-driven terminal console with real-time status dashboards, service toggles, log streams, incident reports, and **phone-scannable Unicode QR codes rendered directly in your terminal**.
* **30-Second Failsafe Auto-Rollback:** When applying PAM changes, a failsafe countdown prevents lockouts. If not confirmed, AkerGate automatically reverts to original PAM configuration.
* **Sentry Event Monitor & Offline Queue:** Continuous tracking of logins, sessions, and failed attempts. If an authentication event occurs while offline, Sentry queues the alert and sends it to Telegram the moment an internet connection is re-established.
* **Multi-Language Support (i18n):** All strings and prompts are stored in external JSON files (`akergate/i18n/locales/`). Shipped out-of-the-box with English (`en.json`) and Arabic (`ar.json`), with instant language switching in TUI or via CLI.
* **Zero External Dependencies for Core PAM:** The PAM authentication hook runs on pure standard library Python, eliminating runtime breakage risks from package managers or virtual environments.

---

## Architecture Overview

```text
+-----------------------------------------------------------+
|              Single Unified Password Prompt               |
|            (sudo, LightDM, lockscreen, etc.)              |
+-----------------------------------------------------------+
                             |
                             v
               +---------------------------+
               |  Step 1: pam_unix.so      |
               |  Checks Master Password   |
               +---------------------------+
                    |                 |
             (Match |                 | (Mismatch)
                    v                 v
             [Access Granted]  +----------------------------------+
                               |  Step 2: pam_exec -> AkerGate    |
                               |  Reads token from stdin          |
                               +----------------------------------+
                                         |              |
                           (TOTP / OTP)  |              | (Invalid)
                                         v              v
                                  [Burn & Grant] [pam_deny -> Reject]
```

---

## Installation

### Prerequisites (Ubuntu / Linux Mint / Debian):
```bash
sudo apt update
sudo apt install -y python3 python3-rich python3-qrcode
```

### Install AkerGate:
```bash
git clone https://github.com/Yuki/AkerGate.git
cd AkerGate
sudo ./install.sh
```

---

## Quick Start & Usage

Launch the interactive management console:
```bash
sudo akergate
```

### CLI Shortcut Commands:
* `akergate status`   : Display active PAM status, keys, and clock health.
* `akergate qr`       : Display the TOTP QR code directly in the terminal for phone scanning.
* `akergate lang [ar|en]` : Switch interface language or display current locale.
* `akergate patch`    : Safely apply AkerGate multi-auth rules to `/etc/pam.d/common-auth`.
* `akergate unpatch`  : Safely remove AkerGate and restore original system PAM settings.
* `akergate lockdown` : Trigger emergency quarantine (customizable disarm policy).
* `akergate disarm`   : Disarm emergency lockdown and restore flexible multi-auth.
* `akergate report`   : Display latest forensic incident report.
* `akergate sentry`   : Run the background event and session monitor.

---

## Telegram Bot Integration

AkerGate supports two deployment models for the Telegram OTP generator:

### Option A: Serverless Cloudflare Worker (Recommended - 100% Free)
A ready-to-deploy Cloudflare Worker script is included under `telegram_backends/cloudflare_worker/worker.js`.
Deployment takes under 2 minutes and requires zero servers:

1. **Get Bot Credentials:**
   * Create a bot using `@BotFather` on Telegram to get your `BOT_TOKEN`.
   * Get your numeric user ID from `@userinfobot` on Telegram (`ALLOWED_CHAT_ID`).
   * Get your Base32 shared secret key from AkerGate (`akergate` -> Tab 4, or `cat /etc/akergate/telegram_secret.key`).

2. **Deploy via Cloudflare Web Dashboard (No CLI required):**
   * Log into [Cloudflare Dashboard](https://dash.cloudflare.com/) -> **Compute (Workers & Pages)** -> **Create Application** -> **Create Worker**.
   * Give it a name (e.g. `akergate-bot`) and click **Deploy**.
   * Click **Edit code**, replace everything in the editor with the contents of `telegram_backends/cloudflare_worker/worker.js`, and click **Deploy**.
   * Go to **Settings** -> **Variables and Secrets** and add these 3 Secrets:
     * `BOT_TOKEN`: Your Telegram bot token.
     * `ALLOWED_CHAT_ID`: Your Telegram numeric user ID.
     * `SHARED_SECRET`: Your Base32 shared secret.

3. **Link Telegram to your Worker (One-Time Webhook Activation):**
   Open your browser or terminal and visit this URL (replace with your values):
   ```text
   https://api.telegram.org/bot<BOT_TOKEN>/setWebhook?url=https://<YOUR_WORKER_NAME>.<YOUR_SUBDOMAIN>.workers.dev
   ```
   Telegram will respond with `{"ok":true,"result":true,"description":"Webhook was set"}`.

4. **Done!** Open your bot on Telegram and type `/otp` anytime from your phone!

### Option B: Standalone VPS / Docker Daemon
For users running their own VPS, server, or Raspberry Pi:
```bash
cd telegram_backends/standalone_bot
export AKERGATE_BOT_TOKEN="your_token"
export AKERGATE_ALLOWED_CHAT_ID=123456789
export AKERGATE_SHARED_SECRET="your_base32_secret"
python3 bot.py
```

---

## Protected Services Matrix

AkerGate allows granular toggles for specific system services via the TUI:
* `sudo` : Command-line root privilege elevation.
* `screensaver` : Screen lock (Cinnamon Screensaver, Swaylock, i3lock, etc.).
* `login` : Display managers (LightDM, GDM, SDDM).
* `sshd` : Remote SSH access (disabled by default for security).

---

## License & Attribution

This project is licensed under the **PolyForm Noncommercial License 1.0.0**.

* **Author:** Muhammad El-Shaikh
* **Commercial Use:** Strictly prohibited without explicit written permission.
* **Redistribution & Modification:** Permitted for personal, educational, and open-source non-commercial use, provided that original author credits, notices, and links to this repository are prominently preserved.

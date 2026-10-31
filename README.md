# AkerGate (أكر جيت)
### Unified Multi-Auth PAM Engine for Linux (Password | TOTP | Telegram OTP)
**Developed by Yuki** | **License: PolyForm Noncommercial 1.0.0**

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
* **Atomic Token Burning (Anti-Replay):** Every temporary token is burned and invalidated immediately upon first entry using kernel-level atomic locks (`fcntl.flock`).
* **Interactive Terminal User Interface (TUI):** A complete keyboard-driven terminal console with real-time status dashboards, service toggles, log streams, and **phone-scannable Unicode QR codes rendered directly in your terminal**.
* **30-Second Failsafe Auto-Rollback:** When applying PAM changes, a failsafe countdown prevents lockouts. If not confirmed, AkerGate automatically reverts to original PAM configuration.
* **Sentry Event Monitor & Offline Queue:** Continuous tracking of logins, sessions, and failed attempts. If an authentication event occurs while offline, Sentry queues the alert and sends it to Telegram the moment an internet connection is re-established.
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
* `akergate status` : Display active PAM status, keys, and clock health.
* `akergate qr`     : Display the TOTP QR code directly in the terminal for phone scanning.
* `akergate patch`  : Safely apply AkerGate multi-auth rules to `/etc/pam.d/common-auth`.
* `akergate unpatch`: Safely remove AkerGate and restore original system PAM settings.
* `akergate sentry` : Run the background event and session monitor.

---

## Telegram Bot Integration

AkerGate supports two deployment models for the Telegram OTP generator:

### Option A: Serverless Cloudflare Worker (Recommended - 100% Free)
A ready-to-deploy Cloudflare Worker script is included under `telegram_backends/cloudflare_worker/worker.js`.
1. Create a bot using `@BotFather` on Telegram to get your `BOT_TOKEN`.
2. Get your numeric ID using `@userinfobot` to set `ALLOWED_CHAT_ID`.
3. In Cloudflare Workers, create a worker and paste `worker.js`.
4. Add Secrets: `BOT_TOKEN`, `ALLOWED_CHAT_ID`, and `SHARED_SECRET` (generated in `akergate`).
5. Send `/otp` to your bot anytime from your phone!

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

* **Author:** Yuki
* **Commercial Use:** Strictly prohibited without explicit written permission.
* **Redistribution & Modification:** Permitted for personal, educational, and open-source non-commercial use, provided that original author credits, notices, and links to this repository are prominently preserved.

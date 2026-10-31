#!/usr/bin/env python3
"""
AkerGate - PAM Execution Hook
Invoked by Linux PAM (pam_exec.so expose_authtok) to authenticate TOTP or Telegram OTP.
Exits 0 on success, exits 1 on failure.
Zero external dependencies.
"""

import sys
import os
from akergate.config import load_config
from akergate.core.totp import verify_totp
from akergate.core.windowed_otp import verify_windowed_otp
from akergate.core.storage import (
    get_totp_secret,
    get_telegram_secret,
    is_token_burned,
    burn_token,
    log_event
)
from akergate.core.lockdown import (
    is_lockdown_active,
    get_lockdown_state,
    disarm_lockdown,
    verify_consecutive_totp
)

def main():
    # Retrieve environment variables set by pam_exec
    pam_user = os.environ.get("PAM_USER", "unknown")
    pam_service = os.environ.get("PAM_SERVICE", "unknown")
    
    # Read the token/password entered by the user via stdin
    try:
        raw_input = sys.stdin.read()
    except Exception:
        raw_input = ""
        
    token = raw_input.rstrip("\x00\r\n ")
    if not token:
        log_event("auth_failure", pam_user, pam_service, "empty", False)
        sys.exit(1)
        
    config = load_config()
    
    # Check if Host is currently under EMERGENCY LOCKDOWN
    if is_lockdown_active():
        state = get_lockdown_state()
        policy = state.get("policy", "dual_totp")
        totp_secret = get_totp_secret()
        
        # Under lockdown, standard single-token entry is suspended!
        # Offline recovery requires two consecutive TOTP codes
        if totp_secret and verify_consecutive_totp(totp_secret, token):
            disarm_lockdown()
            log_event("auth_success", pam_user, pam_service, "lockdown_disarmed_dual_totp", True)
            sys.exit(0)
            
        # Also check if user entered Telegram OTP + TOTP combined (strict_3fa)
        tg_secret = get_telegram_secret()
        if policy == "strict_3fa" and totp_secret and tg_secret:
            # Token format: 7 digits Telegram OTP + 6 digits TOTP (13 digits total)
            cleaned = token.replace(" ", "").replace("+", "")
            if len(cleaned) == 13 and cleaned.isdigit():
                tg_part = cleaned[:7]
                totp_part = cleaned[7:]
                valid_tg, tg_id = verify_windowed_otp(tg_secret, tg_part)
                valid_totp, _ = verify_totp(totp_secret, totp_part)
                if valid_tg and valid_totp and not is_token_burned(tg_id):
                    burn_token(tg_id)
                    disarm_lockdown()
                    log_event("auth_success", pam_user, pam_service, "lockdown_disarmed_3fa", True)
                    sys.exit(0)
                    
        # Any other credential rejected under lockdown
        log_event("auth_failure", pam_user, pam_service, "lockdown_rejected", False)
        sys.exit(1)
    
    # Check if Multi-Auth is enabled for this service
    services_cfg = config.get("services", {})
    service_enabled = True
    
    # Match service categories
    if pam_service in ("sudo", "sudo-i"):
        service_enabled = services_cfg.get("sudo", True)
    elif "screensaver" in pam_service or pam_service in ("cinnamon-screensaver", "swaylock", "i3lock"):
        service_enabled = services_cfg.get("screensaver", True)
    elif pam_service in ("lightdm", "lightdm-greeter", "gdm", "gdm3", "sddm", "login"):
        service_enabled = services_cfg.get("login", True)
    elif pam_service in ("sshd", "ssh"):
        service_enabled = services_cfg.get("sshd", False)
        
    if not service_enabled:
        # Service disabled in AkerGate, reject multi-auth
        sys.exit(1)

    # 1. Check TOTP (Standard 6-digit code)
    totp_cfg = config.get("totp", {})
    if totp_cfg.get("enabled", True):
        totp_secret = get_totp_secret()
        if totp_secret:
            interval = totp_cfg.get("interval_seconds", 30)
            window = totp_cfg.get("window", 1)
            valid, step = verify_totp(totp_secret, token, interval=interval, window=window)
            if valid:
                totp_id = f"totp:{step}:{token}"
                if not is_token_burned(totp_id):
                    burn_token(totp_id, retention_seconds=interval * (window * 2 + 1))
                    log_event("auth_success", pam_user, pam_service, "totp", True)
                    sys.exit(0)

    # 2. Check Telegram Windowed OTP (7-digit code)
    tg_cfg = config.get("telegram", {})
    if tg_cfg.get("enabled", True):
        tg_secret = get_telegram_secret()
        if tg_secret:
            interval = tg_cfg.get("interval_seconds", 300)
            window = tg_cfg.get("window", 1)
            valid, token_id = verify_windowed_otp(tg_secret, token, interval=interval, window=window)
            if valid and token_id:
                if not is_token_burned(token_id):
                    # Burn the token immediately (One-Time Use)
                    burn_token(token_id, retention_seconds=interval * (window * 2 + 1))
                    log_event("auth_success", pam_user, pam_service, "telegram_otp", True)
                    sys.exit(0)

    # If neither matches
    log_event("auth_failure", pam_user, pam_service, "invalid_token", False)
    sys.exit(1)

if __name__ == "__main__":
    main()

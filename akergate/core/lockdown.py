"""
AkerGate - Fully Customizable Emergency Lockdown & Forensic Engine
Allows users to define arbitrary disarm rule combinations:
- Consecutive TOTP (count 1..N)
- Custom Emergency Recovery PIN / Passphrase
- Telegram Windowed OTP
- Remote Telegram Disarm
- Auto-expiration timers
Zero emojis, clean symbols only.
"""

import os
import sys
import time
import json
import hashlib
import subprocess
import socket
from pathlib import Path

from akergate.config import (
    get_data_dir,
    get_log_dir,
    load_config,
    save_config,
    is_root
)
from akergate.core.totp import verify_totp
from akergate.core.windowed_otp import verify_windowed_otp

LOCKDOWN_STATE_FILE = get_data_dir() / "lockdown.json"

DEFAULT_POLICY = {
    "name": "custom",
    "totp_count": 2,                  # Number of consecutive TOTP codes required (0 to disable)
    "require_emergency_pin": False,   # Require emergency recovery PIN
    "emergency_pin_hash": "",         # SHA-256 hash of emergency recovery PIN
    "require_telegram_otp": False,    # Require 7-digit Telegram OTP
    "allow_remote_disarm": True,      # Can be disarmed via Telegram /disarm
    "auto_expire_minutes": 0          # 0 = infinite until disarmed
}

def is_lockdown_active() -> bool:
    """Checks whether the host is currently in emergency lockdown mode."""
    if not LOCKDOWN_STATE_FILE.exists():
        return False
    try:
        data = json.loads(LOCKDOWN_STATE_FILE.read_text(encoding="utf-8"))
        if not data.get("active", False):
            return False
            
        # Check auto-expiration if set
        auto_expire = data.get("policy", {}).get("auto_expire_minutes", 0)
        if auto_expire > 0:
            elapsed_minutes = (time.time() - data.get("triggered_at", 0)) / 60
            if elapsed_minutes >= auto_expire:
                disarm_lockdown()
                return False
                
        return True
    except Exception:
        return False

def get_lockdown_state() -> dict:
    """Returns current lockdown state dictionary."""
    if not LOCKDOWN_STATE_FILE.exists():
        return {"active": False, "policy": DEFAULT_POLICY.copy()}
    try:
        return json.loads(LOCKDOWN_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"active": False, "policy": DEFAULT_POLICY.copy()}

def hash_pin(pin: str) -> str:
    """Generates SHA-256 hash for emergency PIN/passphrase."""
    return hashlib.sha256(pin.strip().encode("utf-8")).hexdigest()

def parse_custom_policy(rule_str: str, emergency_pin: str = "") -> dict:
    """
    Parses a user-defined policy string into a structured policy dictionary.
    Examples:
      'totp=2'
      'totp=2,pin'
      'totp=1,tg'
      'totp=2,tg,pin'
      'pin_only'
      'strict_3fa'
      'dual_totp'
    """
    policy = DEFAULT_POLICY.copy()
    rule_lower = rule_str.strip().lower()
    
    if rule_lower in ("dual_totp", "default"):
        policy["totp_count"] = 2
        policy["require_emergency_pin"] = False
        policy["require_telegram_otp"] = False
        policy["name"] = "dual_totp"
        return policy
        
    if rule_lower in ("strict_3fa", "3fa"):
        policy["totp_count"] = 1
        policy["require_emergency_pin"] = False
        policy["require_telegram_otp"] = True
        policy["name"] = "strict_3fa"
        return policy
        
    if rule_lower in ("pin_only", "pin"):
        policy["totp_count"] = 0
        policy["require_emergency_pin"] = True
        policy["require_telegram_otp"] = False
        policy["name"] = "pin_only"
        if emergency_pin:
            policy["emergency_pin_hash"] = hash_pin(emergency_pin)
        return policy

    # Comma-separated or plus-separated tokens: e.g. "totp=2, pin=1234, tg"
    tokens = [t.strip() for t in rule_lower.replace("+", ",").split(",") if t.strip()]
    policy["totp_count"] = 0
    policy["require_emergency_pin"] = False
    policy["require_telegram_otp"] = False
    policy["name"] = "custom"
    
    for token in tokens:
        if token.startswith("totp"):
            if "=" in token:
                try:
                    count = int(token.split("=")[1])
                    policy["totp_count"] = max(1, count)
                except ValueError:
                    policy["totp_count"] = 1
            else:
                policy["totp_count"] = 1
        elif token.startswith("pin"):
            policy["require_emergency_pin"] = True
            if "=" in token:
                custom_pin = token.split("=")[1].strip()
                policy["emergency_pin_hash"] = hash_pin(custom_pin)
            elif emergency_pin:
                policy["emergency_pin_hash"] = hash_pin(emergency_pin)
        elif token in ("tg", "telegram", "otp"):
            policy["require_telegram_otp"] = True
        elif token.startswith("expire="):
            try:
                policy["auto_expire_minutes"] = int(token.split("=")[1])
            except ValueError:
                pass
                
    if emergency_pin and not policy.get("emergency_pin_hash"):
        policy["emergency_pin_hash"] = hash_pin(emergency_pin)
        
    return policy

def capture_forensic_snapshot(trigger_source: str = "manual") -> Path:
    """Captures a comprehensive, lightweight incident report in Markdown."""
    log_dir = get_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp_str = time.strftime("%Y%m%d_%H%M%S")
    report_file = log_dir / f"incident_report_{timestamp_str}.md"
    
    hostname = socket.gethostname()
    current_time = time.strftime("%Y-%m-%d %H:%M:%S %Z")
    
    # 1. Gather active sessions
    try:
        who_output = subprocess.run(["who", "-u"], capture_output=True, text=True, timeout=3).stdout.strip()
    except Exception:
        who_output = "Unavailable"
        
    # 2. Gather top running processes
    try:
        ps_output = subprocess.run(
            ["ps", "-eo", "user,pid,%cpu,%mem,stat,start,time,comm", "--sort=-%cpu"],
            capture_output=True, text=True, timeout=3
        ).stdout.splitlines()[:25]
        ps_str = "\n".join(ps_output)
    except Exception:
        ps_str = "Unavailable"
        
    # 3. Gather open network listening ports
    try:
        net_output = subprocess.run(
            ["ss", "-tulpn"],
            capture_output=True, text=True, timeout=3
        ).stdout.strip()
    except Exception:
        net_output = "Unavailable"
        
    # 4. Gather recent logins
    try:
        last_output = subprocess.run(
            ["last", "-n", "10"],
            capture_output=True, text=True, timeout=3
        ).stdout.strip()
    except Exception:
        last_output = "Unavailable"
        
    # 5. Gather last shell history
    history_lines = []
    user_home = Path.home()
    bash_hist = user_home / ".bash_history"
    if bash_hist.exists():
        try:
            lines = bash_hist.read_text(encoding="utf-8", errors="ignore").splitlines()[-15:]
            history_lines = lines
        except Exception:
            pass
    history_str = "\n".join(history_lines) if history_lines else "No recent history found."

    report_content = f"""# AkerGate Incident & Forensic Snapshot Report

## Metadata
* Hostname: `{hostname}`
* Incident Time: `{current_time}`
* Trigger Source: `{trigger_source}`
* Status: `HOST QUARANTINED / EMERGENCY LOCKDOWN`

---

## 1. Active Logged-in Sessions
```text
{who_output}
```

---

## 2. Top Running Processes (High CPU / Memory)
```text
{ps_str}
```

---

## 3. Network Listeners & Sockets
```text
{net_output}
```

---

## 4. Recent Authentication History
```text
{last_output}
```

---

## 5. Recent Command Shell History
```text
{history_str}
```

---
*Report automatically generated by AkerGate Forensic Engine.*
"""
    try:
        report_file.write_text(report_content, encoding="utf-8")
        if is_root():
            os.chmod(report_file, 0o600)
    except Exception:
        pass
        
    return report_file

def trigger_lockdown(policy_input: dict | str = "dual_totp", trigger_source: str = "manual", emergency_pin: str = "") -> tuple[bool, str]:
    """
    Activates emergency lockdown with arbitrary customizable policy.
    """
    if isinstance(policy_input, str):
        policy = parse_custom_policy(policy_input, emergency_pin=emergency_pin)
    else:
        policy = policy_input
        
    report_path = capture_forensic_snapshot(trigger_source=trigger_source)
    
    state_data = {
        "active": True,
        "policy": policy,
        "triggered_at": int(time.time()),
        "iso_time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "trigger_source": trigger_source,
        "report_path": str(report_path),
        # Session verification state for multi-step prompts
        "verified_factors": {
            "pin": False,
            "telegram_otp": False,
            "totp_steps": []
        },
        "session_window_start": int(time.time())
    }
    
    LOCKDOWN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        LOCKDOWN_STATE_FILE.write_text(json.dumps(state_data, indent=4), encoding="utf-8")
        if is_root():
            os.chmod(LOCKDOWN_STATE_FILE, 0o600)
    except Exception as e:
        return False, f"Failed to persist lockdown state: {e}"
        
    # Lock desktop screensaver if active
    try:
        subprocess.run(["loginctl", "lock-sessions"], capture_output=True, timeout=2)
    except Exception:
        pass
        
    return True, str(report_path)

def disarm_lockdown() -> bool:
    """Disarms emergency lockdown and restores standard flexible multi-auth."""
    if not LOCKDOWN_STATE_FILE.exists():
        return True
    try:
        state = get_lockdown_state()
        state["active"] = False
        state["disarmed_at"] = int(time.time())
        LOCKDOWN_STATE_FILE.write_text(json.dumps(state, indent=4), encoding="utf-8")
        return True
    except Exception:
        return False

def evaluate_custom_disarm(input_token: str, totp_secret: str, tg_secret: str) -> tuple[bool, str]:
    """
    Evaluates an input string against the active custom disarm policy.
    Supports:
    1. Combined inputs in a single string (separated by '+', space, or concatenated)
    2. Sequential inputs accumulated across multiple prompt attempts within 90 seconds
    Returns (is_fully_satisfied, status_message)
    """
    if not is_lockdown_active():
        return True, "Lockdown is not active."
        
    state = get_lockdown_state()
    policy = state.get("policy", DEFAULT_POLICY)
    now = time.time()
    
    # Check 90s session window for accumulated factors
    window_start = state.get("session_window_start", 0)
    if (now - window_start) > 90:
        # Reset session verification progress
        state["verified_factors"] = {"pin": False, "telegram_otp": False, "totp_steps": []}
        state["session_window_start"] = int(now)
        
    verified = state.setdefault("verified_factors", {"pin": False, "telegram_otp": False, "totp_steps": []})
    
    # Split input token by common separators or process whole
    raw = input_token.strip()
    subtokens = [s.strip() for s in raw.replace("+", " ").replace(":", " ").replace("-", " ").split() if s.strip()]
    if not subtokens:
        subtokens = [raw]
        
    # Check each subtoken against missing requirements
    for piece in subtokens:
        # A. Check Emergency PIN
        if policy.get("require_emergency_pin") and not verified.get("pin"):
            pin_hash = policy.get("emergency_pin_hash", "")
            if pin_hash and hash_pin(piece) == pin_hash:
                verified["pin"] = True
                continue
                
        # B. Check Telegram OTP (7 digits)
        if policy.get("require_telegram_otp") and not verified.get("telegram_otp"):
            if len(piece) == 7 and piece.isdigit() and tg_secret:
                valid_tg, _ = verify_windowed_otp(tg_secret, piece)
                if valid_tg:
                    verified["telegram_otp"] = True
                    continue
                    
        # C. Check TOTP Code (6 digits or multiple 6 digits)
        req_totp_count = policy.get("totp_count", 0)
        current_totp_steps = verified.setdefault("totp_steps", [])
        
        if req_totp_count > 0 and len(current_totp_steps) < req_totp_count:
            if totp_secret and piece.isdigit():
                # Check if piece contains multiple concatenated 6-digit codes (e.g. 12 or 18 digits)
                if len(piece) >= 12 and len(piece) % 6 == 0:
                    chunks = [piece[i:i+6] for i in range(0, len(piece), 6)]
                    for chunk in chunks:
                        v, step = verify_totp(totp_secret, chunk, timestamp=now, window=1)
                        if v and step not in current_totp_steps:
                            current_totp_steps.append(step)
                elif len(piece) == 6:
                    v, step = verify_totp(totp_secret, piece, timestamp=now, window=1)
                    if v and step not in current_totp_steps:
                        # Verify consecutive ordering if multiple codes required
                        if not current_totp_steps or (step == current_totp_steps[-1] + 1 or step == current_totp_steps[-1]):
                            current_totp_steps.append(step)

    # Save verification progress back to state file
    try:
        LOCKDOWN_STATE_FILE.write_text(json.dumps(state, indent=4), encoding="utf-8")
    except Exception:
        pass

    # Check if ALL required conditions of the policy are satisfied
    pin_ok = (not policy.get("require_emergency_pin")) or verified.get("pin", False)
    tg_ok = (not policy.get("require_telegram_otp")) or verified.get("telegram_otp", False)
    totp_ok = (policy.get("totp_count", 0) <= len(verified.get("totp_steps", [])))
    
    if pin_ok and tg_ok and totp_ok:
        # Full satisfaction: Disarm lockdown!
        disarm_lockdown()
        return True, "All custom policy requirements satisfied. Host unlocked."
        
    missing = []
    if not pin_ok: missing.append("Emergency PIN")
    if not tg_ok: missing.append("Telegram OTP")
    if not totp_ok:
        remaining_totp = policy.get("totp_count", 0) - len(verified.get("totp_steps", []))
        missing.append(f"{remaining_totp} TOTP code(s)")
        
    return False, f"Missing requirements: {', '.join(missing)}"

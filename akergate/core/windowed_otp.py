"""
AkerGate - Offline Windowed OTP Engine for Telegram Bot
Cryptographic verification between Cloud/Remote Telegram Bot and an Offline Linux PC.
Zero network access required on the local machine during verification.
"""

import hmac
import hashlib
import struct
import time
import secrets
import base64

DEFAULT_INTERVAL = 300  # 5 minutes per epoch

def generate_telegram_secret(num_bytes: int = 32) -> str:
    """Generates a secure Base32 shared secret for Telegram Bot and Host."""
    return base64.b32encode(secrets.token_bytes(num_bytes)).decode("ascii").rstrip("=")

def generate_windowed_otp(secret_b32: str, slot: int = None, interval: int = DEFAULT_INTERVAL, timestamp: float = None) -> str:
    """
    Generates a 7-digit OTP:
    [slot: 1 digit (0-9)] + [6 digits HMAC-SHA256]
    Used by the Telegram Bot (Cloudflare Worker or Standalone Daemon).
    """
    if timestamp is None:
        timestamp = time.time()
    
    if slot is None:
        slot = secrets.randbelow(10)  # Random slot 0..9
        
    secret_cleaned = secret_b32.strip().replace(" ", "").upper()
    padding = (8 - len(secret_cleaned) % 8) % 8
    key = base64.b32decode(secret_cleaned + "=" * padding, True)
    
    counter = int(timestamp // interval)
    msg = struct.pack(">QQ", counter, slot)
    digest = hmac.new(key, msg, hashlib.sha256).digest()
    
    offset = digest[19] & 0x0F
    binary_num = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
    
    return f"{slot}{binary_num:06d}"

def verify_windowed_otp(secret_b32: str, code: str, interval: int = DEFAULT_INTERVAL, window: int = 1, timestamp: float = None) -> tuple[bool, str]:
    """
    Verifies a 7-digit OTP on the offline host machine.
    Returns (is_valid, token_identifier_for_burning)
    """
    if not secret_b32 or not code:
        return False, ""
        
    code_cleaned = code.strip()
    if len(code_cleaned) != 7 or not code_cleaned.isdigit():
        return False, ""
        
    slot = int(code_cleaned[0])
    num_str = code_cleaned[1:]
    
    secret_cleaned = secret_b32.strip().replace(" ", "").upper()
    padding = (8 - len(secret_cleaned) % 8) % 8
    try:
        key = base64.b32decode(secret_cleaned + "=" * padding, True)
    except Exception:
        return False, ""
        
    if timestamp is None:
        timestamp = time.time()
        
    current_counter = int(timestamp // interval)
    
    for step in range(-window, window + 1):
        counter = current_counter + step
        msg = struct.pack(">QQ", counter, slot)
        digest = hmac.new(key, msg, hashlib.sha256).digest()
        offset = digest[19] & 0x0F
        binary_num = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000
        candidate = f"{binary_num:06d}"
        
        if hmac.compare_digest(candidate, num_str):
            token_id = f"tg:{counter}:{slot}:{candidate}"
            return True, token_id
            
    return False, ""

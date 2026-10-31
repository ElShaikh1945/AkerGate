"""
AkerGate - RFC 6238 TOTP Engine
Pure Python standard library implementation with zero external dependencies.
"""

import hmac
import hashlib
import time
import struct
import base64
import secrets

def generate_totp_secret(num_bytes: int = 20) -> str:
    """
    Generates a secure cryptographically random Base32 secret key.
    Default 20 bytes (160 bits) as recommended by RFC 6238.
    """
    random_bytes = secrets.token_bytes(num_bytes)
    return base64.b32encode(random_bytes).decode("ascii").rstrip("=")

def compute_totp(secret: str, timestamp: float = None, interval: int = 30, digits: int = 6) -> str:
    """
    Computes standard RFC 6238 TOTP code for a given timestamp.
    """
    if timestamp is None:
        timestamp = time.time()
    
    # Pad base32 string if needed
    secret_cleaned = secret.strip().replace(" ", "").upper()
    padding = (8 - len(secret_cleaned) % 8) % 8
    key = base64.b32decode(secret_cleaned + "=" * padding, True)
    
    counter = int(timestamp // interval)
    msg = struct.pack(">Q", counter)
    
    digest = hmac.new(key, msg, hashlib.sha1).digest()
    offset = digest[19] & 0x0F
    binary_code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    
    return f"{binary_code:0{digits}d}"

def verify_totp(secret: str, code: str, timestamp: float = None, interval: int = 30, window: int = 1, digits: int = 6) -> tuple[bool, int]:
    """
    Verifies a TOTP code within a drift window (-window to +window).
    Returns (is_valid, matched_step_counter)
    """
    if not secret or not code:
        return False, 0
    
    code_cleaned = code.strip()
    if len(code_cleaned) != digits or not code_cleaned.isdigit():
        return False, 0

    if timestamp is None:
        timestamp = time.time()

    secret_cleaned = secret.strip().replace(" ", "").upper()
    padding = (8 - len(secret_cleaned) % 8) % 8
    try:
        key = base64.b32decode(secret_cleaned + "=" * padding, True)
    except Exception:
        return False, 0

    current_counter = int(timestamp // interval)
    
    for step in range(-window, window + 1):
        counter = current_counter + step
        msg = struct.pack(">Q", counter)
        digest = hmac.new(key, msg, hashlib.sha1).digest()
        offset = digest[19] & 0x0F
        binary_code = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
        generated_str = f"{binary_code:0{digits}d}"
        
        # Constant-time comparison to prevent timing attacks
        if hmac.compare_digest(generated_str, code_cleaned):
            return True, counter

    return False, 0

def build_otpauth_uri(secret: str, username: str, issuer: str = "AkerGate") -> str:
    """Builds standard otpauth URI compatible with authenticator apps."""
    return f"otpauth://totp/{issuer}:{username}?secret={secret}&issuer={issuer}&algorithm=SHA1&digits=6&period=30"

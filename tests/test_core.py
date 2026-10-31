"""
AkerGate - Unit Test Suite for Cryptographic and PAM Logic
Zero external test dependencies (uses standard unittest).
Zero emojis.
"""

import unittest
import time
from pathlib import Path
import tempfile
import shutil

from akergate.core.totp import (
    generate_totp_secret,
    compute_totp,
    verify_totp,
    build_otpauth_uri
)
from akergate.core.windowed_otp import (
    generate_telegram_secret,
    generate_windowed_otp,
    verify_windowed_otp
)
from akergate.core.storage import burn_token, is_token_burned
from akergate.pam.patcher import patch_pam, unpatch_pam, is_pam_patched
from akergate.core.lockdown import (
    capture_forensic_snapshot,
    trigger_lockdown,
    disarm_lockdown,
    is_lockdown_active,
    verify_consecutive_totp
)

class TestAkerGateCore(unittest.TestCase):

    def test_totp_generation_and_verification(self):
        secret = generate_totp_secret()
        self.assertGreaterEqual(len(secret), 26)
        
        # Test current code
        now = time.time()
        code = compute_totp(secret, timestamp=now)
        self.assertEqual(len(code), 6)
        self.assertTrue(code.isdigit())
        
        # Verify match
        valid, step = verify_totp(secret, code, timestamp=now)
        self.assertTrue(valid)
        self.assertGreater(step, 0)
        
        # Test drift window (+1 step)
        valid_drift, _ = verify_totp(secret, code, timestamp=now + 25)
        self.assertTrue(valid_drift)
        
        # Test invalid code
        invalid, _ = verify_totp(secret, "000000", timestamp=now)
        self.assertFalse(invalid)

    def test_windowed_telegram_otp(self):
        secret = generate_telegram_secret()
        now = time.time()
        
        # Generate 7-digit OTP
        code1 = generate_windowed_otp(secret, slot=3, timestamp=now)
        self.assertEqual(len(code1), 7)
        self.assertEqual(code1[0], "3")
        
        # Verify valid OTP
        valid, token_id = verify_windowed_otp(secret, code1, timestamp=now)
        self.assertTrue(valid)
        self.assertIn("tg:", token_id)
        
        # Verify fake OTP fails
        invalid, _ = verify_windowed_otp(secret, "3999999", timestamp=now)
        self.assertFalse(invalid)

    def test_token_burning(self):
        token_id = f"test_token_{int(time.time() * 1000)}"
        self.assertFalse(is_token_burned(token_id))
        
        # Burn token
        burned = burn_token(token_id, retention_seconds=60)
        self.assertTrue(burned)
        
        # Check that it is now burned
        self.assertTrue(is_token_burned(token_id))

    def test_pam_patcher_mock(self):
        # Create a mock common-auth file
        with tempfile.TemporaryDirectory() as tmpdir:
            mock_pam = Path(tmpdir) / "common-auth"
            mock_backup = Path(tmpdir) / "backups"
            mock_pam.write_text(
                "# Mock common-auth\n"
                "auth\t[success=1 default=ignore]\tpam_unix.so nullok\n"
                "auth\trequisite\t\tpam_deny.so\n"
                "auth\trequired\t\tpam_permit.so\n",
                encoding="utf-8"
            )
            
            self.assertFalse(is_pam_patched(mock_pam))
            
            # Apply patch
            ok, msg = patch_pam(mock_pam, backup_dir=mock_backup)
            self.assertTrue(ok, msg)
            self.assertTrue(is_pam_patched(mock_pam))
            
            content = mock_pam.read_text(encoding="utf-8")
            self.assertIn("akergate-pam", content)
            self.assertIn("success=2", content)
            
            # Unpatch
            un_ok, un_msg = unpatch_pam(mock_pam, backup_dir=mock_backup)
            self.assertTrue(un_ok, un_msg)
            self.assertFalse(is_pam_patched(mock_pam))

    def test_forensic_snapshot_and_lockdown(self):
        # 1. Test capturing snapshot
        report_path = capture_forensic_snapshot(trigger_source="test_suite")
        self.assertTrue(report_path.exists())
        content = report_path.read_text(encoding="utf-8")
        self.assertIn("AkerGate Incident & Forensic Snapshot Report", content)
        self.assertIn("Metadata", content)
        
        # 2. Test lockdown trigger
        ok, r_path = trigger_lockdown(policy="dual_totp", trigger_source="test_panic")
        self.assertTrue(ok)
        self.assertTrue(is_lockdown_active())
        
        # 3. Test consecutive TOTP verification
        secret = generate_totp_secret()
        now = time.time()
        c1 = compute_totp(secret, timestamp=now)
        c2 = compute_totp(secret, timestamp=now + 30) # Next 30s step
        
        # Combined 12 digits
        combined = f"{c1}{c2}"
        self.assertTrue(verify_consecutive_totp(secret, combined))
        
        # Invalid combined
        self.assertFalse(verify_consecutive_totp(secret, "000000111111"))
        
        # 4. Test disarming
        disarmed = disarm_lockdown()
        self.assertTrue(disarmed)
        self.assertFalse(is_lockdown_active())

if __name__ == "__main__":
    unittest.main()

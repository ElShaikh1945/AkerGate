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
    parse_custom_policy,
    evaluate_custom_disarm
)
from akergate.i18n import t, set_language, get_current_language, list_available_languages

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
        
        # 2. Test policy parser
        custom_p = parse_custom_policy("totp=3,pin=1234,tg")
        self.assertEqual(custom_p["totp_count"], 3)
        self.assertTrue(custom_p["require_emergency_pin"])
        self.assertTrue(custom_p["require_telegram_otp"])
        self.assertTrue(bool(custom_p["emergency_pin_hash"]))
        
        # 3. Test triggering lockdown with custom PIN + TOTP
        secret = generate_totp_secret()
        now = time.time()
        c1 = compute_totp(secret, timestamp=now)
        
        ok, r_path = trigger_lockdown(policy_input="totp=1,pin=7788", trigger_source="test_panic")
        self.assertTrue(ok)
        self.assertTrue(is_lockdown_active())
        
        # Test wrong token fails
        sat_bad, _ = evaluate_custom_disarm("wrong_token", secret, "")
        self.assertFalse(sat_bad)
        self.assertTrue(is_lockdown_active())
        
        # Test combined PIN + TOTP disarms successfully
        sat_good, msg = evaluate_custom_disarm(f"7788+{c1}", secret, "")
        self.assertTrue(sat_good, msg)
        self.assertFalse(is_lockdown_active())
        
        # 4. Test 2-Consecutive TOTP disarm
        c2 = compute_totp(secret, timestamp=now + 30)
        ok2, _ = trigger_lockdown(policy_input="totp=2", trigger_source="test_panic_2")
        self.assertTrue(ok2)
        
        sat_consec, msg2 = evaluate_custom_disarm(f"{c1}{c2}", secret, "")
        self.assertTrue(sat_consec, msg2)
        self.assertFalse(is_lockdown_active())

    def test_i18n_engine(self):
        langs = list_available_languages()
        self.assertIn("en", langs)
        self.assertIn("ar", langs)
        
        # English translation test
        set_language("en")
        self.assertEqual(get_current_language(), "en")
        en_title = t("dashboard.title")
        self.assertEqual(en_title, "System Status Overview")
        
        # Arabic translation test
        set_language("ar")
        self.assertEqual(get_current_language(), "ar")
        ar_title = t("dashboard.title")
        self.assertEqual(ar_title, "نظرة عامة على حالة النظام")
        
        # Parameter interpolation test
        interpolated = t("dashboard.local_time", time="12:00:00")
        self.assertIn("12:00:00", interpolated)
        
        # Fallback test for non-existent key
        fallback = t("non_existent_key_xyz")
        self.assertEqual(fallback, "non_existent_key_xyz")
        
        # Reset back to English
        set_language("en")

if __name__ == "__main__":
    unittest.main()

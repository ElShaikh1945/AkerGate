"""
AkerGate - Failsafe Rollback Engine
Ensures the user can never be locked out of their system due to PAM misconfiguration.
Zero external dependencies.
"""

import time
import threading
from akergate.pam.patcher import patch_pam, unpatch_pam

_failsafe_active = False
_failsafe_confirmed = False

def run_failsafe_test(timeout_seconds: int = 30, on_tick=None, on_revert=None) -> bool:
    """
    Applies the patch temporarily and waits for user confirmation.
    If not confirmed within timeout_seconds, automatically reverts PAM.
    Returns True if confirmed by user, False if reverted.
    """
    global _failsafe_active, _failsafe_confirmed
    _failsafe_active = True
    _failsafe_confirmed = False
    
    # 1. Apply patch
    success, msg = patch_pam()
    if not success:
        return False
        
    start_time = time.time()
    
    while time.time() - start_time < timeout_seconds:
        if _failsafe_confirmed:
            _failsafe_active = False
            return True
            
        remaining = int(timeout_seconds - (time.time() - start_time))
        if on_tick:
            on_tick(remaining)
        time.sleep(1)
        
    # Timeout reached without confirmation -> Revert!
    unpatch_pam()
    _failsafe_active = False
    if on_revert:
        on_revert()
    return False

def confirm_failsafe():
    """Confirms that the new PAM configuration works and cancels auto-revert."""
    global _failsafe_confirmed
    _failsafe_confirmed = True

def is_failsafe_active() -> bool:
    global _failsafe_active
    return _failsafe_active

"""
AkerGate - Safe PAM Patcher
Handles safe modification, backup, verification, and restoration of /etc/pam.d/ files.
Zero external dependencies.
"""

import shutil
import time
from pathlib import Path
from akergate.config import get_config_dir

COMMON_AUTH_PATH = Path("/etc/pam.d/common-auth")

def get_backup_dir() -> Path:
    return get_config_dir() / "pam_backups"

AKERGATE_MARKER_START = "# --- BEGIN AKERGATE MANAGED BLOCK ---"
AKERGATE_MARKER_END = "# --- END AKERGATE MANAGED BLOCK ---"

# Target binary called by pam_exec
PAM_EXEC_TARGET = "/usr/local/bin/akergate-pam"

def is_pam_patched(target_file: Path = COMMON_AUTH_PATH) -> bool:
    """Checks whether the PAM file contains the AkerGate block."""
    if not target_file.exists():
        return False
    try:
        content = target_file.read_text(encoding="utf-8")
        return AKERGATE_MARKER_START in content
    except Exception:
        return False

def backup_pam_file(target_file: Path = COMMON_AUTH_PATH, backup_dir: Path = None) -> Path:
    """Creates a timestamped backup of the PAM file before modification."""
    b_dir = backup_dir if backup_dir else get_backup_dir()
    b_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    backup_path = b_dir / f"{target_file.name}.bak_{timestamp}"
    shutil.copy2(target_file, backup_path)
    return backup_path

def get_latest_backup(target_file: Path = COMMON_AUTH_PATH, backup_dir: Path = None) -> Path:
    """Finds the most recent backup of the specified PAM file."""
    b_dir = backup_dir if backup_dir else get_backup_dir()
    if not b_dir.exists():
        return None
    backups = sorted(b_dir.glob(f"{target_file.name}.bak_*"), reverse=True)
    return backups[0] if backups else None

def patch_pam(target_file: Path = COMMON_AUTH_PATH, backup_dir: Path = None) -> tuple[bool, str]:
    """
    Safely injects AkerGate block into /etc/pam.d/common-auth.
    Preserves existing rules and maintains dual-hop jump structure.
    """
    if not target_file.exists():
        return False, f"File {target_file} not found."
        
    if is_pam_patched(target_file):
        return True, "PAM is already configured for AkerGate."
        
    # Create backup first
    try:
        backup_path = backup_pam_file(target_file, backup_dir=backup_dir)
    except Exception as e:
        return False, f"Failed to create backup: {e}"
        
    try:
        lines = target_file.read_text(encoding="utf-8").splitlines()
        new_lines = []
        replaced = False
        
        for line in lines:
            stripped = line.strip()
            # Match Debian/Ubuntu standard primary unix line
            if not replaced and stripped.startswith("auth") and "pam_unix.so" in stripped and "pam-auth-update" not in stripped:
                new_lines.append(AKERGATE_MARKER_START)
                new_lines.append("# Primary unix password check (skips 2 rules on success)")
                new_lines.append("auth\t[success=2 default=ignore]\tpam_unix.so nullok try_first_pass nodelay")
                new_lines.append(f"# AkerGate Multi-Auth fallback (TOTP / Telegram OTP)")
                new_lines.append(f"auth\t[success=1 default=ignore]\tpam_exec.so expose_authtok seteuid {PAM_EXEC_TARGET}")
                new_lines.append(AKERGATE_MARKER_END)
                replaced = True
            else:
                new_lines.append(line)
                
        if not replaced:
            return False, "Could not locate standard pam_unix.so line in PAM configuration."
            
        target_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True, f"Successfully patched {target_file}. Backup saved at {backup_path.name}"
    except Exception as e:
        # Revert on write error
        if backup_path.exists():
            shutil.copy2(backup_path, target_file)
        return False, f"Error patching PAM: {e}"

def unpatch_pam(target_file: Path = COMMON_AUTH_PATH, backup_dir: Path = None) -> tuple[bool, str]:
    """
    Removes AkerGate block and restores standard pam_unix configuration.
    """
    if not target_file.exists():
        return False, f"File {target_file} not found."
        
    if not is_pam_patched(target_file):
        return True, "AkerGate block is not present in PAM configuration."
        
    try:
        backup_pam_file(target_file, backup_dir=backup_dir)
    except Exception as e:
        return False, f"Failed to create backup: {e}"
        
    try:
        lines = target_file.read_text(encoding="utf-8").splitlines()
        new_lines = []
        in_block = False
        restored = False
        
        for line in lines:
            if AKERGATE_MARKER_START in line:
                in_block = True
                new_lines.append("auth\t[success=1 default=ignore]\tpam_unix.so nullok")
                restored = True
                continue
            if AKERGATE_MARKER_END in line:
                in_block = False
                continue
            if not in_block:
                new_lines.append(line)
                
        target_file.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
        return True, f"Successfully unpatched {target_file}."
    except Exception as e:
        return False, f"Error restoring PAM: {e}"

def restore_latest_backup(target_file: Path = COMMON_AUTH_PATH) -> tuple[bool, str]:
    """Restores the most recent backup file."""
    latest = get_latest_backup(target_file)
    if not latest or not latest.exists():
        return False, "No backup file available."
    try:
        shutil.copy2(latest, target_file)
        return True, f"Restored {target_file} from {latest.name}"
    except Exception as e:
        return False, f"Failed to restore: {e}"

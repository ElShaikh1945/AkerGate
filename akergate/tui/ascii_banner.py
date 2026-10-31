"""
AkerGate - Clean Modern ASCII Typography Banner Engine
Provides crisp, professional developer CLI typography for AkerGate.
Zero emojis, clean symbols only.
"""

import sys
from typing import Optional
from rich.text import Text

# Color definitions (100% Flat TrueColor matching AkerGate palette)
GOLD = "\033[38;2;229;192;123m"
CYAN = "\033[38;2;86;182;194m"
WHITE = "\033[38;2;240;246;252m"
DIM = "\033[38;2;139;148;158m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ─────────────────────────────────────────────────────────────────────────────
# CLEAN MODERN TYPOGRAPHY BANNER (Slant Two-Tone: AKER in Gold, GATE in Cyan)
# ─────────────────────────────────────────────────────────────────────────────
BANNER_LINES = [
    f"{GOLD}    ___    __         {CYAN}    ______      __     {RESET}",
    f"{GOLD}   /   |  / /_____  __{CYAN}___/ ____/___ _/ /____ {RESET}",
    f"{GOLD}  / /| | / //_/ _ \\/ _{CYAN}__/ / __/ __ `/ __/ _ \\{RESET}",
    f"{GOLD} / ___ |/ ,< /  __/ / {CYAN} / /_/ / /_/ / /_/  __/{RESET}",
    f"{GOLD}/_/  |_/_/|_|\\___/_/  {CYAN}  \\____/\\__,_/\\__/\\___/ {RESET}",
    f"",
    f"  {CYAN}Unified Multi-Auth Linux PAM Engine {DIM}|{WHITE} v0.1.0{RESET}",
    f"  {WHITE}Author: {GOLD}Muhammad El-Shaikh {DIM}| License: PolyForm Noncommercial 1.0.0{RESET}",
    f"  {DIM}Factors: Master Password {CYAN}+ {DIM}RFC 6238 TOTP {CYAN}+ {DIM}Offline Telegram OTP{RESET}"
]

BANNER_ANSI = "\n".join(BANNER_LINES)

def get_ansi_banner(full: bool = False, trim_margins: bool = True) -> str:
    """Return the clean modern typography ANSI banner string."""
    return BANNER_ANSI

def get_compact_banner() -> str:
    """Alias for get_ansi_banner."""
    return BANNER_ANSI

def get_rich_banner(full: bool = False) -> Text:
    """Return the typography banner as a Rich Text object for TUI panels."""
    rich_text = Text()

    # Line 1
    rich_text.append("    ___    __             ", style="#E5C07B")
    rich_text.append("______      __     \n", style="#56B6C2")

    # Line 2
    rich_text.append("   /   |  / /_____  _____/", style="#E5C07B")
    rich_text.append("____/___ _/ /____ \n", style="#56B6C2")

    # Line 3
    rich_text.append("  / /| | / //_/ _ \\/ ___/", style="#E5C07B")
    rich_text.append(" / __/ __ `/ __/ _ \\\n", style="#56B6C2")

    # Line 4
    rich_text.append(" / ___ |/ ,< /  __/ /   ", style="#E5C07B")
    rich_text.append("/ /_/ / /_/ / /_/  __/\n", style="#56B6C2")

    # Line 5
    rich_text.append("/_/  |_/_/|_|\\___/_/    ", style="#E5C07B")
    rich_text.append("\\____/\\__,_/\\__/\\___/ \n\n", style="#56B6C2")

    # Line 6 (Subtitles)
    rich_text.append("  Unified Multi-Auth Linux PAM Engine ", style="#56B6C2")
    rich_text.append("| ", style="#8B949E")
    rich_text.append("v0.1.0\n", style="#F0F6FC")

    # Line 7 (Credits)
    rich_text.append("  Author: ", style="#F0F6FC")
    rich_text.append("Muhammad El-Shaikh ", style="#E5C07B")
    rich_text.append("| License: PolyForm Noncommercial 1.0.0\n", style="#8B949E")

    # Line 8 (Factors)
    rich_text.append("  Factors: Master Password ", style="#8B949E")
    rich_text.append("+ ", style="#56B6C2")
    rich_text.append("RFC 6238 TOTP ", style="#8B949E")
    rich_text.append("+ ", style="#56B6C2")
    rich_text.append("Offline Telegram OTP", style="#8B949E")

    return rich_text

def get_compact_rich_banner() -> Text:
    """Alias for get_rich_banner."""
    return get_rich_banner()

def print_banner(full: bool = False) -> None:
    """Print the clean typography banner directly to stdout."""
    sys.stdout.write(BANNER_ANSI + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    print_banner()

"""
AkerGate - Compact ASCII Terminal Sentinel Banner Engine
Provides both a sleek 14-line modern CLI banner and full legacy artwork.
Zero emojis, clean symbols only.
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Tuple, List
from rich.text import Text

# Color definitions (100% Flat TrueColor matching AkerGate palette)
GOLD = "\033[38;2;229;192;123m"
CYAN = "\033[38;2;86;182;194m"
WHITE = "\033[38;2;240;246;252m"
DIM = "\033[38;2;139;148;158m"
BOLD = "\033[1m"
RESET = "\033[0m"

# ─────────────────────────────────────────────────────────────────────────────
# 14-LINE COMPACT AKER SENTINEL BANNER (Default modern CLI style)
# ─────────────────────────────────────────────────────────────────────────────
COMPACT_BANNER_LINES = [
    f"{GOLD}           /\\                                                  /\\{RESET}",
    f"{GOLD}          /  \\___                                          ___/  \\{RESET}",
    f"{GOLD}         (  <{CYAN}o{GOLD}>  \\                 {CYAN}.--[+]--.{GOLD}              /  <{CYAN}o{GOLD}>  ){RESET}",
    f"{GOLD}          \\   ___/                {CYAN}/   (o)   \\{GOLD}             \\___   /{RESET}",
    f"{GOLD}          /  /                   {CYAN}|     |     |{GOLD}                   \\  \\{RESET}",
    f"{GOLD}     ____/  /                     {CYAN}\\___/__\\___/{GOLD}                     \\  \\____{RESET}",
    f"{GOLD}    ( SEF  /    {GOLD}___   _  _______ ____   ____    _  _____ _____     {GOLD}\\  DUAU ){RESET}",
    f"{GOLD}     \\____/    {GOLD}/ _ \\ | |/ / ____|  _ \\ / ___|  / \\|_   _| ____|     {GOLD}\\____/{RESET}",
    f"{GOLD}              {GOLD}/ /_\\ \\| ' /|  _| | |_) | |  _  / _ \\ | | |  _|{RESET}",
    f"{GOLD}             {GOLD}/ ___ \\| . \\| |___|  _ <| |_| |/ ___ \\| | | |___ {RESET}",
    f"{GOLD}            {GOLD}/_/   \\_\\_|\\_\\_____|_| \\_\\\\____|/_/   \\_\\_| |_____|{RESET}",
    f"{CYAN}       ====[ Yesterday ]=======[ AKERGATE PAM Engine ]=======[ Tomorrow ]===={RESET}",
    f"{WHITE}             Unified Multi-Factor Engine {DIM}|{WHITE} Author: Muhammad El-Shaikh{RESET}",
    f"{DIM}             Master Password  {CYAN}+  {DIM}RFC 6238 TOTP  {CYAN}+  {DIM}Offline Telegram OTP{RESET}"
]

COMPACT_BANNER_ANSI = "\n".join(COMPACT_BANNER_LINES)

def get_compact_banner() -> str:
    """Return the sleek 14-line colored ASCII banner string."""
    return COMPACT_BANNER_ANSI

def get_compact_rich_banner() -> Text:
    """Return the 14-line banner as a Rich Text object."""
    rich_text = Text()
    lines_specs = [
        [("           /\\                                                  /\\", "#E5C07B")],
        [("          /  \\___                                          ___/  \\", "#E5C07B")],
        [("         (  <", "#E5C07B"), ("o", "#56B6C2"), (">  \\                 ", "#E5C07B"), (".--[+]--.", "#56B6C2"), ("              /  <", "#E5C07B"), ("o", "#56B6C2"), (">  )", "#E5C07B")],
        [("          \\   ___/                ", "#E5C07B"), ("/   (o)   \\", "#56B6C2"), ("             \\___   /", "#E5C07B")],
        [("          /  /                   ", "#E5C07B"), ("|     |     |", "#56B6C2"), ("                   \\  \\", "#E5C07B")],
        [("     ____/  /                     ", "#E5C07B"), ("\\___/__\\___/", "#56B6C2"), ("                     \\  \\____", "#E5C07B")],
        [("    ( SEF  /    ", "#E5C07B"), ("___   _  _______ ____   ____    _  _____ _____     ", "#E5C07B"), ("\\  DUAU )", "#E5C07B")],
        [("     \\____/    ", "#E5C07B"), ("/ _ \\ | |/ / ____|  _ \\ / ___|  / \\|_   _| ____|     ", "#E5C07B"), ("\\____/", "#E5C07B")],
        [("              / /_\\ \\| ' /|  _| | |_) | |  _  / _ \\ | | |  _|", "#E5C07B")],
        [("             / ___ \\| . \\| |___|  _ <| |_| |/ ___ \\| | | |___ ", "#E5C07B")],
        [("            /_/   \\_\\_|\\_\\_____|_| \\_\\\\____|/_/   \\_\\_| |_____|", "#E5C07B")],
        [("       ====[ Yesterday ]=======[ AKERGATE PAM Engine ]=======[ Tomorrow ]====", "#56B6C2")],
        [("             Unified Multi-Factor Engine ", "#F0F6FC"), ("|", "#8B949E"), (" Author: Muhammad El-Shaikh", "#F0F6FC")],
        [("             Master Password  ", "#8B949E"), ("+", "#56B6C2"), ("  RFC 6238 TOTP  ", "#8B949E"), ("+", "#56B6C2"), ("  Offline Telegram OTP", "#8B949E")]
    ]
    for row_idx, row in enumerate(lines_specs):
        for text_part, color in row:
            rich_text.append(text_part, style=color)
        if row_idx < len(lines_specs) - 1:
            rich_text.append("\n")
    return rich_text

# ─────────────────────────────────────────────────────────────────────────────
# FULL 61-LINE ARTWORK LOADER (Legacy / Detailed View)
# ─────────────────────────────────────────────────────────────────────────────
_CACHED_JSON_DATA = None
_CACHED_FULL_ANSI = None

def _get_json_paths() -> List[Path]:
    base_dir = Path(__file__).resolve().parent.parent
    return [
        base_dir / "data" / "banner.json",
        base_dir.parent / "assets" / "asciinator_31Oct_001.json",
        base_dir.parent / "assets" / "banner.json",
        Path("/usr/share/akergate/banner.json"),
        Path("/etc/akergate/banner.json")
    ]

def load_banner_data() -> Optional[dict]:
    global _CACHED_JSON_DATA
    if _CACHED_JSON_DATA is not None:
        return _CACHED_JSON_DATA
    for candidate in _get_json_paths():
        if candidate.is_file():
            try:
                with open(candidate, "r", encoding="utf-8") as fh:
                    _CACHED_JSON_DATA = json.load(fh)
                    return _CACHED_JSON_DATA
            except Exception:
                continue
    return None

def _hex_to_rgb(hex_code: Optional[str]) -> Optional[Tuple[int, int, int]]:
    if not hex_code:
        return None
    hex_code = hex_code.lstrip("#")
    if len(hex_code) != 6:
        return None
    try:
        return (
            int(hex_code[0:2], 16),
            int(hex_code[2:4], 16),
            int(hex_code[4:6], 16)
        )
    except ValueError:
        return None

def get_full_ansi_banner(trim_margins: bool = True) -> str:
    global _CACHED_FULL_ANSI
    if _CACHED_FULL_ANSI is not None:
        return _CACHED_FULL_ANSI

    data = load_banner_data()
    if not data or "rows" not in data:
        return get_compact_banner()

    col_start = 12 if trim_margins else 0
    col_end = 108 if trim_margins else 120

    lines = []
    for row in data["rows"]:
        text = row.get("text", "")
        colors = row.get("colors", [])
        row_text = text[col_start:col_end]
        row_colors = colors[col_start:col_end] if colors else []

        line_parts = []
        current_color = None
        for idx, char in enumerate(row_text):
            col_hex = row_colors[idx] if idx < len(row_colors) else None
            if col_hex != current_color:
                current_color = col_hex
                if col_hex:
                    rgb = _hex_to_rgb(col_hex)
                    if rgb:
                        line_parts.append(f"\033[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m")
                    else:
                        line_parts.append("\033[0m")
                else:
                    line_parts.append("\033[0m")
            line_parts.append(char)
        line_parts.append("\033[0m")
        lines.append("".join(line_parts))

    _CACHED_FULL_ANSI = "\n".join(lines)
    return _CACHED_FULL_ANSI

# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRYPOINTS
# ─────────────────────────────────────────────────────────────────────────────
def get_ansi_banner(full: bool = False, trim_margins: bool = True) -> str:
    """Return ANSI banner string. Defaults to sleek 14-line compact version."""
    if full:
        return get_full_ansi_banner(trim_margins=trim_margins)
    return get_compact_banner()

def get_rich_banner(full: bool = False) -> Text:
    """Return banner as Rich Text. Defaults to sleek 14-line compact version."""
    if full:
        from rich.text import Text as RText
        data = load_banner_data()
        if not data:
            return get_compact_rich_banner()
        t = RText()
        for r in data["rows"]:
            for ch, col in zip(r["text"][12:108], r["colors"][12:108]):
                t.append(ch, style=col if col else "")
            t.append("\n")
        return t
    return get_compact_rich_banner()

def print_banner(full: bool = False) -> None:
    """Print the banner directly to stdout."""
    banner = get_ansi_banner(full=full)
    sys.stdout.write(banner + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    is_full = "--full" in sys.argv
    print_banner(full=is_full)

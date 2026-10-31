"""
AkerGate - ASCII Terminal Sentinel Banner Engine
Renders high-fidelity TrueColor ANSI / Rich ASCII art from asciinator specification.
Zero emojis, clean symbols only.
"""

import os
import sys
import json
from pathlib import Path
from typing import Optional, Tuple, List

# In-memory caches for instant rendering (<1ms)
_CACHED_JSON_DATA = None
_CACHED_ANSI_FULL = None
_CACHED_ANSI_TRIMMED = None

def _get_json_paths() -> List[Path]:
    """Return ordered candidate paths for the asciinator JSON file."""
    base_dir = Path(__file__).resolve().parent.parent
    return [
        base_dir / "data" / "banner.json",
        base_dir.parent / "assets" / "asciinator_31Oct_001.json",
        base_dir.parent / "assets" / "banner.json",
        Path("/usr/share/akergate/banner.json"),
        Path("/etc/akergate/banner.json")
    ]

def load_banner_data() -> Optional[dict]:
    """Load banner JSON from the first available location."""
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
    """Convert hex color string (#rrggbb) to (R, G, B) tuple."""
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

def get_ansi_banner(trim_margins: bool = False) -> str:
    """
    Generate and return the 24-bit TrueColor ANSI formatted ASCII banner.
    If trim_margins is True, crops left/right empty columns (from 120 down to 96 columns)
    to fit comfortably on standard terminal widths.
    """
    global _CACHED_ANSI_FULL, _CACHED_ANSI_TRIMMED

    if trim_margins and _CACHED_ANSI_TRIMMED is not None:
        return _CACHED_ANSI_TRIMMED
    if not trim_margins and _CACHED_ANSI_FULL is not None:
        return _CACHED_ANSI_FULL

    data = load_banner_data()
    if not data or "rows" not in data:
        fallback = "[ AKERGATE - TEMPORAL DUAL SENTINEL PAM ENGINE ]\n"
        return fallback

    # Bounds for trimming: columns 12 through 108
    col_start = 12 if trim_margins else 0
    col_end = 108 if trim_margins else 120

    lines = []
    for row in data["rows"]:
        text = row.get("text", "")
        colors = row.get("colors", [])

        # Substring / sublist for this row
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

    rendered = "\n".join(lines)
    if trim_margins:
        _CACHED_ANSI_TRIMMED = rendered
    else:
        _CACHED_ANSI_FULL = rendered

    return rendered

def get_rich_banner(trim_margins: bool = False):
    """
    Return the banner as a rich.text.Text object for display in Rich panels and TUI screens.
    """
    from rich.text import Text

    data = load_banner_data()
    if not data or "rows" not in data:
        fallback_text = Text("[ AKERGATE - TEMPORAL DUAL SENTINEL PAM ENGINE ]", style="bold cyan")
        return fallback_text

    col_start = 12 if trim_margins else 0
    col_end = 108 if trim_margins else 120

    rich_text = Text()
    for row_idx, row in enumerate(data["rows"]):
        text = row.get("text", "")
        colors = row.get("colors", [])

        row_text = text[col_start:col_end]
        row_colors = colors[col_start:col_end] if colors else []

        for idx, char in enumerate(row_text):
            col_hex = row_colors[idx] if idx < len(row_colors) else None
            style = f"{col_hex}" if col_hex else ""
            rich_text.append(char, style=style)
        
        if row_idx < len(data["rows"]) - 1:
            rich_text.append("\n")

    return rich_text

def print_banner(trim_margins: Optional[bool] = None) -> None:
    """
    Print the colored ASCII banner directly to stdout.
    Automatically detects terminal width if trim_margins is None.
    """
    if trim_margins is None:
        try:
            terminal_cols = os.get_terminal_size().columns
            trim_margins = terminal_cols < 120
        except OSError:
            trim_margins = False

    banner = get_ansi_banner(trim_margins=trim_margins)
    sys.stdout.write(banner + "\n")
    sys.stdout.flush()

if __name__ == "__main__":
    print_banner()

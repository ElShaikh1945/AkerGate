"""
AkerGate - Reliable Keyboard Navigation and Interactive Menu Engine
Direct OS-level raw descriptor reader (eliminating Python TextIOWrapper buffering conflicts).
Handles ANSI Arrow Keys (UP, DOWN, LEFT, RIGHT), ENTER, SPACE, ESC, and shortcuts seamlessly.
Zero emojis, clean symbols only.
"""

import sys
import os
import select
import termios
import tty
from typing import Optional, List, Tuple, Callable
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

def _parse_raw_bytes(b: bytes) -> str:
    """Parse raw bytes from terminal into logical key strings."""
    if not b:
        return ""
    # Standard and application keypad cursor keys
    if b in (b"\x1b[A", b"\x1bOA"):
        return "UP"
    elif b in (b"\x1b[B", b"\x1bOB"):
        return "DOWN"
    elif b in (b"\x1b[C", b"\x1bOC"):
        return "RIGHT"
    elif b in (b"\x1b[D", b"\x1bOD"):
        return "LEFT"
    elif b in (b"\x1b[H", b"\x1b[1~"):
        return "HOME"
    elif b in (b"\x1b[F", b"\x1b[4~"):
        return "END"
    elif b in (b"\r", b"\n"):
        return "ENTER"
    elif b == b" ":
        return "SPACE"
    elif b == b"\t":
        return "TAB"
    elif b in (b"\x7f", b"\x08"):
        return "BACKSPACE"
    elif b == b"\x1b":
        return "ESC"
    
    # Check if multiple escape sequences got batched
    if b.startswith(b"\x1b[") and len(b) >= 3:
        code = b[2:3]
        if code == b"A": return "UP"
        elif code == b"B": return "DOWN"
        elif code == b"C": return "RIGHT"
        elif code == b"D": return "LEFT"

    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return ""

def get_key(timeout: Optional[float] = None) -> str:
    """
    Read a single keypress directly from OS file descriptor without user-space buffering.
    Guarantees arrow key escape sequences (e.g. \\x1b[A) are read as atomic units.
    """
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        # Non-interactive / pipe fallback
        rlist, _, _ = select.select([fd], [], [], 0)
        if rlist:
            raw = os.read(fd, 32)
            if not raw:
                return "ENTER"
            return _parse_raw_bytes(raw)
        return "ENTER"

    old_settings = termios.tcgetattr(fd)
    try:
        # Use setraw for unbuffered atomic escape sequences
        tty.setraw(fd)
        if timeout is not None:
            rlist, _, _ = select.select([fd], [], [], timeout)
            if not rlist:
                return ""

        raw = os.read(fd, 32)
        if not raw:
            return ""

        # If a lone ESC byte was read, give a tiny 50ms window to catch trailing sequence
        if raw == b"\x1b":
            rlist, _, _ = select.select([fd], [], [], 0.05)
            if rlist:
                raw += os.read(fd, 31)

        return _parse_raw_bytes(raw)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def wait_for_key(prompt_text: str = "Press any key to return...") -> str:
    """Display a return prompt and wait for a single keypress."""
    console.print(f"\n[dim]{prompt_text}[/dim]")
    return get_key()

def select_menu(
    options: List[Tuple[str, str]],
    default_index: int = 0,
    title: str = "Select Action",
    border_style: str = "cyan",
    on_render_header: Optional[Callable[[], None]] = None,
    allow_cancel: bool = True
) -> int:
    """
    Render an interactive menu navigable via UP / DOWN arrow keys.
    Pressing ENTER or SPACE selects the highlighted option.
    Pressing ESC returns the last option (if allow_cancel is True).
    Direct digit keys (1-9) or shortcut letters will also jump/select.

    Each option is a tuple: (Label, Description)
    Returns: Index of the selected option (0 to len(options)-1).
    """
    if not options:
        return 0

    current_idx = max(0, min(default_index, len(options) - 1))
    fd = sys.stdin.fileno()

    # If non-interactive, return default
    if not os.isatty(fd):
        return current_idx

    while True:
        console.clear()
        if on_render_header:
            on_render_header()

        # Build menu table
        table = Table(show_header=False, expand=True, box=None, padding=(0, 1))
        table.add_column("Pointer", width=3, style="bold")
        table.add_column("Number", width=4, style="dim")
        table.add_column("Action", style="bold")
        table.add_column("Details")

        for idx, (label, desc) in enumerate(options):
            is_selected = (idx == current_idx)
            if is_selected:
                pointer = "[bold #E5C07B] > [/bold #E5C07B]"
                num_str = f"[bold #E5C07B][{idx + 1}][/bold #E5C07B]"
                label_str = f"[bold #0B0E14 on #E5C07B] {label} [/bold #0B0E14 on #E5C07B]"
                desc_str = f"[bold #E5C07B]{desc}[/bold #E5C07B]"
            else:
                pointer = "   "
                num_str = f"[dim][{idx + 1}][/dim]"
                label_str = f"[white]{label}[/white]"
                desc_str = f"[dim]{desc}[/dim]"

            table.add_row(pointer, num_str, label_str, desc_str)

        instructions = "[dim]Navigate: [bold #56B6C2]UP / DOWN Arrows[/bold #56B6C2]  |  Select: [bold #56B6C2]ENTER / SPACE[/bold #56B6C2]"
        if allow_cancel:
            instructions += "  |  Back: [bold #56B6C2]ESC / B[/bold #56B6C2][/dim]"
        else:
            instructions += "  |  Quit: [bold #56B6C2]Q[/bold #56B6C2][/dim]"

        panel = Panel(
            table,
            title=f"[bold]{title}[/bold]",
            subtitle=instructions,
            border_style=border_style,
            padding=(0, 1)
        )

        console.print(panel)

        key = get_key()

        if key == "UP":
            current_idx = (current_idx - 1) % len(options)
        elif key == "DOWN":
            current_idx = (current_idx + 1) % len(options)
        elif key in ("ENTER", "SPACE"):
            return current_idx
        elif key in ("ESC", "b", "B"):
            if allow_cancel:
                return len(options) - 1
            # If cancel is not allowed (e.g. Dashboard), do not exit!
        elif key in ("q", "Q"):
            if not allow_cancel:
                # In Dashboard, pressing Q selects Quit
                return len(options) - 1
            else:
                return len(options) - 1
        elif key.isdigit():
            # Check 1-based digit shortcut
            digit_val = int(key) - 1
            if 0 <= digit_val < len(options):
                return digit_val

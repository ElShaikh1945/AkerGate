"""
AkerGate - Keyboard Navigation and Interactive Menu Engine
Zero external dependencies (uses standard termios, tty, select).
Supports arrow keys (UP, DOWN, LEFT, RIGHT), ENTER, ESC, TAB, and direct keys.
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

def get_key(timeout: Optional[float] = None) -> str:
    """
    Read a single keypress from standard input without requiring Enter.
    Returns: 'UP', 'DOWN', 'LEFT', 'RIGHT', 'ENTER', 'ESC', 'TAB', 'BACKSPACE', 'SPACE',
    or the single character string (e.g. '1', 'q', 'l', 'y', 'n').
    """
    fd = sys.stdin.fileno()
    if not os.isatty(fd):
        # Fallback for pipes, tests, or non-interactive environments
        rlist, _, _ = select.select([sys.stdin], [], [], 0)
        if rlist:
            ch = sys.stdin.read(1)
            return ch if ch else "ENTER"
        return "ENTER"

    old_settings = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        if timeout is not None:
            rlist, _, _ = select.select([sys.stdin], [], [], timeout)
            if not rlist:
                return ""
        ch = sys.stdin.read(1)
        if ch == "\x1b":
            # Potential ANSI escape sequence
            rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
            if rlist:
                ch2 = sys.stdin.read(1)
                if ch2 in ("[", "O"):
                    rlist, _, _ = select.select([sys.stdin], [], [], 0.05)
                    if rlist:
                        ch3 = sys.stdin.read(1)
                        if ch3 == "A":
                            return "UP"
                        elif ch3 == "B":
                            return "DOWN"
                        elif ch3 == "C":
                            return "RIGHT"
                        elif ch3 == "D":
                            return "LEFT"
                        elif ch3 == "H":
                            return "HOME"
                        elif ch3 == "F":
                            return "END"
                        return f"ESC_{ch2}_{ch3}"
                return "ESC"
            return "ESC"
        elif ch in ("\r", "\n"):
            return "ENTER"
        elif ch == "\t":
            return "TAB"
        elif ch in ("\x7f", "\x08"):
            return "BACKSPACE"
        elif ch == " ":
            return "SPACE"
        return ch
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

def wait_for_key(prompt_text: str = "Press any arrow key, Enter, or Space to return...") -> str:
    """Display a return prompt and wait for a single keypress."""
    console.print(f"\n[dim]{prompt_text}[/dim]")
    return get_key()

def select_menu(
    options: List[Tuple[str, str]],
    default_index: int = 0,
    title: str = "Select Action",
    border_style: str = "cyan",
    on_render_header: Optional[Callable[[], None]] = None
) -> int:
    """
    Render an interactive menu navigable via UP / DOWN arrow keys.
    Pressing ENTER or SPACE selects the highlighted option.
    Pressing ESC returns the last option (typically 'Back').
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

        instructions = "[dim]Navigate: [bold #56B6C2]UP / DOWN Arrows[/bold #56B6C2]  |  Select: [bold #56B6C2]ENTER / SPACE[/bold #56B6C2]  |  Back: [bold #56B6C2]ESC / B[/bold #56B6C2][/dim]"
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
        elif key in ("ESC", "b", "B", "q", "Q"):
            # Return last option (assumed to be Back/Cancel)
            return len(options) - 1
        elif key.isdigit():
            # Check 1-based digit shortcut
            digit_val = int(key) - 1
            if 0 <= digit_val < len(options):
                return digit_val

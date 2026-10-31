"""
AkerGate - Terminal Unicode QR Code Renderer
Renders high-density, phone-scannable QR codes using Unicode half-block characters.
Zero external heavy dependencies (uses standard python-qrcode or fallback).
Zero emojis.
"""

import functools

@functools.lru_cache(maxsize=16)
def generate_terminal_qr(data: str) -> str:
    """
    Renders an ASCII/Unicode QR Code directly for terminal display.
    Uses half-block characters (▀, ▄, █, ' ') to fit 2 module rows per terminal row.
    """
    try:
        import qrcode
        qr = qrcode.QRCode(border=1)
        qr.add_data(data)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        
        lines = []
        for r in range(0, len(matrix), 2):
            row1 = matrix[r]
            row2 = matrix[r + 1] if r + 1 < len(matrix) else [False] * len(row1)
            line = []
            for c1, c2 in zip(row1, row2):
                if c1 and c2:
                    line.append(" ")
                elif c1 and not c2:
                    line.append("▄")
                elif not c1 and c2:
                    line.append("▀")
                else:
                    line.append("█")
            lines.append("".join(line))
        return "\n".join(lines)
    except ImportError:
        return "[!] python3-qrcode not installed. Unable to render graphical QR code in terminal."

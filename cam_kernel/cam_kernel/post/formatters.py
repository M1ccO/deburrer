"""NC formatters — generic G-code utilities.

Formatting helpers shared across post-processor backends:
- Number formatting (trailing-zero stripping, decimal places)
- Modal output (suppress repeated values)
- Block formatting (word order, comments)
- Program structure (header, footer, segment markers)

These are pure text functions with no knowledge of machine kinematics.

TODO:
 - Heidenhain conversational (.H) format
 - Siemens ShopMill format
 - ISO 6983 standard block format
"""

from __future__ import annotations

from typing import Optional


def format_number(value: float, decimals: int = 3) -> str:
    """Format a float, stripping trailing zeros and decimal point."""
    text = ("%.*f" % (decimals, value)).rstrip("0").rstrip(".")
    if text in ("-0", ""):
        return "0"
    return text


def format_xyz(x: float, y: float, z: float, decimals: int = 3) -> str:
    """Format an XYZ coordinate block."""
    return " ".join([
        f"X{format_number(x, decimals)}",
        f"Y{format_number(y, decimals)}",
        f"Z{format_number(z, decimals)}",
    ])


def format_bc(b: Optional[float], c: Optional[float], last_b: Optional[float], last_c: Optional[float], decimals: int = 3) -> str:
    """Format B/C words, suppressing repeated values."""
    words = []
    if b is not None and (last_b is None or abs(b - last_b) > 0.0005):
        words.append(f"B{format_number(b, decimals)}")
    if c is not None and (last_c is None or abs(c - last_c) > 0.0005):
        words.append(f"C{format_number(c, decimals)}")
    return " ".join(words)


def program_header(program_number: int, comment: str = "") -> str:
    """Render a standard program header."""
    comment_text = f" ({comment})" if comment else ""
    return f"O{program_number:04d}{comment_text}"


def program_footer() -> str:
    """Render a standard program footer."""
    return "M30\n"

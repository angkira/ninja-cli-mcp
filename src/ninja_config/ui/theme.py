"""Nord theme tokens shared by the Textual TUIs and InquirerPy flows.

Single source of truth for the Nord palette used across
``ninja_config.modern_tui`` and ``ninja_config.menuconfig_tui``
(the ``theme.tcss`` stylesheet in this package uses the same hex values).

Only stdlib + Rich imports here, so this module never pulls heavy
dependencies into importers.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from rich.text import Text


if TYPE_CHECKING:
    from collections.abc import Sequence

# ── Polar Night ──────────────────────────────────────────────────────
NORD0 = "#2E3440"
NORD1 = "#3B4252"
NORD2 = "#434C5E"
NORD3 = "#4C566A"

# ── Snow Storm ───────────────────────────────────────────────────────
NORD4 = "#D8DEE9"
NORD5 = "#E5E9F0"
NORD6 = "#ECEFF4"

# ── Frost ────────────────────────────────────────────────────────────
FROST7 = "#8FBCBB"
FROST8 = "#88C0D0"
FROST9 = "#81A1C1"
FROST10 = "#5E81AC"

# ── Aurora ───────────────────────────────────────────────────────────
AURORA_RED = "#BF616A"
AURORA_ORANGE = "#D08770"
AURORA_YELLOW = "#EBCB8B"
AURORA_GREEN = "#A3BE8C"
AURORA_PURPLE = "#B48EAD"

#: Full palette for programmatic use.
NORD: dict[str, str] = {
    "nord0": NORD0,
    "nord1": NORD1,
    "nord2": NORD2,
    "nord3": NORD3,
    "nord4": NORD4,
    "nord5": NORD5,
    "nord6": NORD6,
    "frost7": FROST7,
    "frost8": FROST8,
    "frost9": FROST9,
    "frost10": FROST10,
    "aurora_red": AURORA_RED,
    "aurora_orange": AURORA_ORANGE,
    "aurora_yellow": AURORA_YELLOW,
    "aurora_green": AURORA_GREEN,
    "aurora_purple": AURORA_PURPLE,
}

#: Horizontal gradient used for logos and section headers.
GRADIENT_FROST: tuple[str, ...] = (FROST8, FROST9, FROST7, FROST10)


def gradient_text(text: str, colors: Sequence[str] = GRADIENT_FROST) -> Text:
    """Render text with a horizontal frost gradient (newline-safe).

    Args:
        text: Text to colorize (may contain newlines).
        colors: Gradient stops, cycled left-to-right per line.

    Returns:
        Rich ``Text`` with per-character colors.
    """
    out = Text()
    lines = text.split("\n")
    for row_idx, line in enumerate(lines):
        width = max(len(line), 1)
        for col, ch in enumerate(line):
            if ch.strip():
                stop = min(col * len(colors) // width, len(colors) - 1)
                out.append(ch, style=colors[stop])
            else:
                out.append(ch)
        if row_idx < len(lines) - 1:
            out.append("\n")
    return out


#: Nord styling for InquirerPy prompts (pass via ``style=``).
NORD_INQUIRER_STYLE: dict[str, str] = {
    "questionmark": FROST8,
    "answer": AURORA_GREEN,
    "input": NORD6,
    "pointer": FROST8,
    "highlighted": FROST8,
    "separator": NORD3,
    "instruction": NORD3,
    "text": NORD4,
    "disabled": NORD3,
}


def get_nord_inquirer_style() -> object:
    """Build an InquirerPy style object from the Nord palette.

    Imported lazily so this module stays dependency-free besides Rich.
    """
    from InquirerPy.utils import get_style

    return get_style(NORD_INQUIRER_STYLE)

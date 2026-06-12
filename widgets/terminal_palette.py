from PyQt6.QtGui import QColor


ANSI_COLORS = {
    "black": "#000000",
    "red": "#cc0000",
    "green": "#4e9a06",
    "brown": "#c4a000",
    "yellow": "#c4a000",
    "blue": "#3465a4",
    "magenta": "#75507b",
    "cyan": "#06989a",
    "white": "#d3d7cf",
    "brightblack": "#555753",
    "brightred": "#ef2929",
    "brightgreen": "#8ae234",
    "brightbrown": "#fce94f",
    "brightyellow": "#fce94f",
    "brightblue": "#729fcf",
    "brightmagenta": "#ad7fa8",
    "brightcyan": "#34e2e2",
    "brightwhite": "#eeeeec",
}

DEFAULT_FG = "#d3d7cf"
DEFAULT_BG = "#000000"
BRACKETED_PASTE_ENABLE = b"\x1b[?2004h"
BRACKETED_PASTE_DISABLE = b"\x1b[?2004l"


def resolve_color(value: str, default: str, bold: bool = False) -> QColor:
    if not value or value == "default":
        return QColor(default)
    if bold and value in ANSI_COLORS and not value.startswith("bright"):
        bright = "bright" + value
        if bright in ANSI_COLORS:
            return QColor(ANSI_COLORS[bright])
    if value in ANSI_COLORS:
        return QColor(ANSI_COLORS[value])
    if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
        return QColor("#" + value)
    return QColor(default)

"""Persistent app settings.

QFont is not JSON-serializable, so we round-trip the font as a "Family,Pt"
string and rebuild a QFont on load. Other values are plain types.
"""

import logging

from PyQt6.QtGui import QFont

from core.platform_utils import atomic_write_json, config_path, default_monospace_font, load_json

log = logging.getLogger(__name__)


SETTINGS_FILE = "settings.json"


def _font_to_str(font: QFont) -> str:
    return f"{font.family()},{font.pointSize()}"


def _font_from_str(value: str) -> QFont:
    try:
        family, size = value.rsplit(",", 1)
        return QFont(family.strip(), int(size))
    except (ValueError, TypeError):
        return default_monospace_font(10)


def default_settings() -> dict:
    return {
        # General
        "show_dashboard": True,
        "auto_sftp": True,
        "confirm_close_tab": True,
        "confirm_quit_with_sessions": True,

        # Terminal appearance
        "font": default_monospace_font(10),
        "term_bg": "#000000",
        "term_fg": "#d3d7cf",
        "color_scheme": "Default",
        "cursor_blink": True,
        "cursor_shape": "block",        # block | underline | bar
        "cursor_color": "#d3d7cf",      # cursor block/underline/bar color
        "selection_bg": "#3465a4",      # selection highlight bg
        "selection_fg": "#ffffff",      # selection highlight fg
        "bold_is_bright": True,         # bold cells use the bright ANSI palette

        # Terminal behavior
        "right_click_paste": True,
        "copy_on_select": False,        # auto-copy when a drag ends (off by default)
        "scrollback": 5000,
        "wheel_lines": 3,
        "bell_mode": "beep",            # off | beep | visual
        "encoding": "UTF-8",
        "auto_log": False,
        "log_directory": "logs",
        "strip_newlines_on_paste": False,  # convert CRLF/CR to a single newline before writing to PTY
        "default_editor_command": "",   # optional external editor for SFTP-opened files (empty = built-in)

        # Window / chrome
        "theme": "Dark (MobaXterm style)",
        "opacity": 100,
        "tab_position": "Top",          # Top | Bottom | Left | Right
        "restore_window_geometry": True,
        "window_geometry": "",          # opaque hex blob from QMainWindow.saveGeometry()

        # SSH defaults
        "ssh_default_user": "",
        "ssh_default_port": 22,
        "ssh_connect_timeout": 15,
        "ssh_agent_forwarding": False,
        "ssh_keepalive_interval": 30,   # seconds; 0 disables
        "known_hosts_file": "~/.ssh/known_hosts",
    }


def load_settings() -> dict:
    """Load settings, merging with defaults so new keys appear without manual upgrade."""
    raw = load_json(config_path(SETTINGS_FILE), {})
    merged = default_settings()
    for key, value in raw.items():
        if key == "font":
            merged[key] = _font_from_str(value) if isinstance(value, str) else merged[key]
        else:
            merged[key] = value
    return merged


def save_settings(settings: dict) -> None:
    serializable = {}
    for key, value in settings.items():
        if isinstance(value, QFont):
            serializable[key] = _font_to_str(value)
        else:
            serializable[key] = value
    try:
        atomic_write_json(config_path(SETTINGS_FILE), serializable)
    except OSError:
        log.exception("Failed to save settings")

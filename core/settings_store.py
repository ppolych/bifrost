"""Persistent app settings.

QFont is not JSON-serializable, so we round-trip the font as a "Family,Pt"
string and rebuild a QFont on load. Other values are plain types.
"""

import logging

from PyQt6.QtGui import QFont

from core.platform_utils import atomic_write_json, config_path, default_monospace_font, load_json
from core.styles import DEFAULT_THEME, THEME_NAMES

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


def _coerce_int(value, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        result = int(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and result < min_value:
        return default
    if max_value is not None and result > max_value:
        return default
    return result


def _coerce_float(value, default: float, *, min_value: float | None = None, max_value: float | None = None) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    if min_value is not None and result < min_value:
        return default
    if max_value is not None and result > max_value:
        return default
    return result


def _coerce_bool(value, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _coerce_int_list(value, default: list[int]) -> list[int]:
    if not isinstance(value, list):
        return list(default)
    out = []
    for item in value:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            return list(default)
    return out


def default_settings() -> dict:
    return {
        # General
        "show_dashboard": True,
        "auto_sftp": True,
        "sftp_show_hidden": False,      # show dotfiles in the SFTP browser
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
        "confirm_multiline_paste": True,
        "confirm_large_paste": True,
        "large_paste_threshold": 2000,
        "auto_log": False,
        "log_directory": "logs",
        "strip_newlines_on_paste": False,  # convert CRLF/CR to a single newline before writing to PTY
        "default_editor_command": "",   # optional external editor for SFTP-opened files (empty = built-in)
        "default_text_editor_command": "",  # optional text editor for explicit SFTP "open in text editor"

        # Window / chrome
        "theme": "Dark (MobaXterm style)",
        "opacity": 100,
        "tab_position": "Top",          # Top | Bottom | Left | Right
        "restore_window_geometry": True,
        "window_geometry": "",          # opaque hex blob from QMainWindow.saveGeometry()
        "main_splitter_sizes": [],       # sidebar / terminal split
        "sidebar_splitter_sizes": [],    # sidebar tabs / SFTP split
        "last_sidebar_tab": 0,

        # SSH defaults
        "ssh_default_user": "",
        "ssh_default_port": 22,
        "ssh_default_auth": "agent",     # agent | key | password
        "ssh_default_key_path": "",
        "ssh_startup_command": "",       # sent after SSH shell opens
        "ssh_connect_timeout": 15,
        "ssh_agent_forwarding": False,
        "ssh_keepalive_interval": 30,   # seconds; 0 disables
        "ssh_tcp_keepalive": True,      # kernel-level SO_KEEPALIVE on the socket
        "known_hosts_file": "~/.ssh/known_hosts",

        # Security / credentials
        "credential_provider": "system",  # system | 1password | keepassxc
        "credential_save_policy": "ask",  # ask | never
    }


def load_settings() -> dict:
    """Load settings, merging with defaults so new keys appear without manual upgrade."""
    raw = load_json(config_path(SETTINGS_FILE), {})
    if not isinstance(raw, dict):
        raw = {}
    merged = default_settings()
    for key, value in raw.items():
        if key == "font":
            merged[key] = _font_from_str(value) if isinstance(value, str) else merged[key]
        else:
            merged[key] = value
    _sanitize_settings(merged, default_settings())
    return merged


def _sanitize_settings(settings: dict, defaults: dict) -> None:
    for key in (
        "show_dashboard", "auto_sftp", "sftp_show_hidden", "confirm_close_tab",
        "confirm_quit_with_sessions", "cursor_blink", "bold_is_bright",
        "right_click_paste", "copy_on_select", "confirm_multiline_paste",
        "confirm_large_paste", "auto_log", "strip_newlines_on_paste",
        "restore_window_geometry", "ssh_agent_forwarding", "ssh_tcp_keepalive",
    ):
        settings[key] = _coerce_bool(settings.get(key), defaults[key])
    for key, low, high in (
        ("scrollback", 100, 200000),
        ("wheel_lines", 1, 100),
        ("large_paste_threshold", 1, 10000000),
        ("opacity", 20, 100),
        ("ssh_default_port", 1, 65535),
        ("ssh_keepalive_interval", 0, 600),
        ("last_sidebar_tab", 0, 99),
    ):
        settings[key] = _coerce_int(settings.get(key), defaults[key], min_value=low, max_value=high)
    settings["ssh_connect_timeout"] = _coerce_float(
        settings.get("ssh_connect_timeout"),
        defaults["ssh_connect_timeout"],
        min_value=1.0,
        max_value=120.0,
    )
    settings["main_splitter_sizes"] = _coerce_int_list(
        settings.get("main_splitter_sizes"),
        defaults["main_splitter_sizes"],
    )
    settings["sidebar_splitter_sizes"] = _coerce_int_list(
        settings.get("sidebar_splitter_sizes"),
        defaults["sidebar_splitter_sizes"],
    )
    if settings.get("theme") not in THEME_NAMES:
        settings["theme"] = DEFAULT_THEME


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

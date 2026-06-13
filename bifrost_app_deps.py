import configparser
import importlib.metadata
import json
import logging
import os
import platform
import posixpath
import re
import shlex
import shutil
import socket
import subprocess
import sys

import psutil
import paramiko
import pyte
from PyQt6.QtCore import QT_VERSION_STR, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog, QHBoxLayout,
    QInputDialog, QLabel, QLineEdit, QMainWindow, QMenu, QMessageBox, QSplitter,
    QStatusBar, QTabBar, QTabWidget, QVBoxLayout, QWidget,
)

log = logging.getLogger(__name__)
from widgets.sidebar import Sidebar
from widgets.terminal import TerminalWidget
from widgets.terminal_container import TerminalContainer
from widgets.toolbar import MainToolBar
from widgets.session_dialog import SessionDialog
from widgets.settings_dialog import SettingsDialog
from widgets.command_palette import CommandPalette, PaletteEntry
from widgets.credential_manager import CredentialManager
from widgets.editor import MobaEditor
from widgets.dashboard import Dashboard
from widgets.remote_monitor import RemoteMonitorWidget
from core.styles import get_theme_stylesheet
from core.color_schemes import DEFAULT_NAME, SCHEMES, apply_scheme
from core import credentials, session_crypto, wake_on_lan, wsl
from core.host_key_prompt import HostKeyPrompter, QtHostKeyPolicy
from core.icons import app_icon
from core.logging_setup import _log_path, configure_logging
from core.mobaxterm_import import parse_mobaxterm_file
from core.rdp import RdpLaunchError, launch_rdp_session, rdp_client_status
from core.ssh_config_import import parse_ssh_config_file
from core.persistence import SessionManager
from core.macro_engine import MacroEngine
from core.snippets import SnippetManager
from core.platform_utils import config_dir, default_monospace_font, migrate_legacy_config
from core.settings_store import load_settings, save_settings
from core.serial_backend import SerialBackend
from core.ssh_backend import ParamikoBackend, SshCredentials
from core.telnet_backend import TelnetBackend
from core.workspaces import WorkspaceManager
from widgets.app_menus import setup_app_menus
from widgets.credential_prompt import CredentialPrompt
from widgets.tool_dialogs import run_tool
from widgets.vnc_viewer import VncViewer


_LOCAL_FILENAME_UNSAFE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _remote_display_name(remote_path: str, default: str = "file") -> str:
    """Return the leaf name of a remote POSIX path on every local OS."""
    name = posixpath.basename((remote_path or "").rstrip("/"))
    return name or default


def parse_quick_connect_command(method: str, text: str) -> tuple[str, str]:
    raw = (text or "").strip()
    if not raw:
        return method, raw
    try:
        parts = shlex.split(raw)
    except ValueError:
        return method, raw
    if not parts:
        return method, raw
    command = parts[0].lower()
    if command not in {"ssh", "telnet", "rdp", "vnc", "wsl", "local"}:
        return method, raw
    args = parts[1:]
    if command == "ssh":
        host = ""
        port = ""
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in {"-p", "-P"} and i + 1 < len(args):
                port = args[i + 1]
                i += 2
                continue
            if arg.startswith("-p") and arg[2:].isdigit():
                port = arg[2:]
                i += 1
                continue
            if not arg.startswith("-") and not host:
                host = arg
            i += 1
        if host and port and ":" not in host:
            host = f"{host}:{port}"
        return "SSH", host
    if command in {"telnet", "rdp"}:
        target = args[0] if args else ""
        if len(args) > 1 and args[1].isdigit() and ":" not in target:
            target = f"{target}:{args[1]}"
        return command.upper() if command == "rdp" else "Telnet", target
    if command == "vnc":
        return "VNC", args[0] if args else ""
    if command == "wsl":
        return "WSL", args[0] if args else ""
    return "Local", " ".join(args)


def _safe_temp_suffix(remote_path: str) -> str:
    """Build a suffix safe for tempfile paths on Linux, Windows, and macOS."""
    name = _remote_display_name(remote_path)
    return "-" + (_LOCAL_FILENAME_UNSAFE.sub("_", name).strip(" .") or "file")


def _iter_sessions(node, prefix: str = ""):
    if isinstance(node, list):
        for session in node:
            if isinstance(session, dict):
                name = session.get("name") or "session"
                yield f"{prefix}/{name}".strip("/"), session
        return
    if not isinstance(node, dict):
        return
    for name, child in node.items():
        child_prefix = f"{prefix}/{name}".strip("/")
        yield from _iter_sessions(child, child_prefix)


def _split_user_command(command: str) -> list[str]:
    """Split a user-entered command using the local platform's quoting rules."""
    if os.name == "nt":
        return [_strip_outer_quotes(part) for part in shlex.split(command, posix=False)]
    return shlex.split(command)


def _strip_outer_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _font_from_override(value: str, fallback: QFont) -> QFont:
    try:
        family, size = value.rsplit(",", 1)
        font = QFont(family.strip(), int(size))
    except (AttributeError, TypeError, ValueError):
        return QFont(fallback)
    return font if font.family() else QFont(fallback)


__all__ = [name for name in globals() if not name.startswith("__")]

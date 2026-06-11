"""Centralized icon lookup.

`session_icon(session_dict)` returns a QIcon appropriate for a session's
`type`. `folder_icon(open=True|False)` returns the folder icon.
`favorite_icon(on=...)` returns the star icon for a session-favorite toggle.

Icons are Material Symbols (Apache-2.0) bundled under `res/icons/material/`.
PyQt6 renders SVG via QIcon natively — no QtSvg dependency required.

Legacy `named_icon(...)` accepts the old asbru-* filenames as aliases so
existing UI call sites keep working through the rename.
"""

from __future__ import annotations

import os
from functools import lru_cache

from PyQt6.QtGui import QIcon

# Material Symbols set lives under res/icons/material; the parent res/icons
# also still contains the old asbru-cm SVGs for now (the rename PR will
# remove them). Resolve relative to this file so the import path is robust.
ICON_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "res", "icons")
MATERIAL_DIR = os.path.join(ICON_DIR, "material")


# Session-method → Material Symbols filename. Mapped to keep visual distinction:
# Local is a clean terminal; SSH/Telnet are network-shaped; RDP/VNC are
# display-shaped; SFTP/FTP are folder-shaped; Mosh is a signal-bars icon.
METHOD_ICON_MAP = {
    "SSH":    "dns.svg",
    "Telnet": "cable.svg",
    "Serial": "cable.svg",
    "RDP":    "desktop_windows.svg",
    "VNC":    "screen_share.svg",
    "SFTP":   "folder_shared.svg",
    "FTP":    "cloud_upload.svg",
    "Mosh":   "signal_cellular_4_bar.svg",
    "Local":  "terminal.svg",
    "WSL":    "terminal.svg",
}

# Old asbru-cm filenames (still referenced by some call sites) → new names.
_LEGACY_ALIASES = {
    "asbru-preferences.svg": "settings.svg",
    "asbru-wol.svg":         "power_settings_new.svg",
    "asbru-edit.svg":        "edit.svg",
    "asbru_quick_connect.svg": "bolt.svg",
    "asbru-logo.svg":        "hub.svg",
}


@lru_cache(maxsize=64)
def _icon(name: str) -> QIcon:
    """Load a material icon by filename. Empty QIcon if missing."""
    # Resolve legacy filenames transparently.
    name = _LEGACY_ALIASES.get(name, name)
    path = os.path.join(MATERIAL_DIR, name)
    if not os.path.exists(path):
        return QIcon()
    return QIcon(path)


def session_icon(session: dict | None) -> QIcon:
    if not session:
        return _icon("link.svg")
    method = session.get("type", "")
    return _icon(METHOD_ICON_MAP.get(method, "link.svg"))


def folder_icon(*, is_open: bool) -> QIcon:
    return _icon("folder_open.svg" if is_open else "folder.svg")


def favorite_icon(*, on: bool) -> QIcon:
    return _icon("star-fill.svg" if on else "star.svg")


def app_icon() -> QIcon:
    return _icon("hub.svg")


def named_icon(name: str) -> QIcon:
    """Direct accessor by filename. Legacy `asbru-*.svg` names are aliased."""
    return _icon(name)

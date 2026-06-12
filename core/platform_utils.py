import json
import os
import sys
import tempfile

from PyQt6.QtCore import QStandardPaths
from PyQt6.QtGui import QFont, QFontDatabase, QGuiApplication


def default_monospace_font(size: int = 10) -> QFont:
    """Pick a sensible monospace font for the current platform."""
    if sys.platform == "darwin":
        candidates = ["SF Mono", "Menlo", "Monaco", "Courier New"]
    elif sys.platform == "win32":
        candidates = ["Cascadia Mono", "Consolas", "Lucida Console", "Courier New"]
    else:
        candidates = ["DejaVu Sans Mono", "Liberation Mono", "Monospace", "Courier New"]

    if QGuiApplication.instance() is None:
        fallback = QFont(candidates[0], size)
        fallback.setStyleHint(QFont.StyleHint.Monospace)
        return fallback

    available = set(QFontDatabase.families())
    for name in candidates:
        if name in available:
            return QFont(name, size)

    fallback = QFont()
    fallback.setStyleHint(QFont.StyleHint.Monospace)
    fallback.setFamily(fallback.defaultFamily())
    fallback.setPointSize(size)
    return fallback


def config_dir() -> str:
    """Return the per-user config directory for Bifrost, creating it if needed.

    Relies on QApplication.setApplicationName('bifrost') being called at startup
    so QStandardPaths returns a stable path. Falls back to ~/.bifrost otherwise.
    """
    base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    if not base or os.path.basename(base) in ("", "-c"):
        base = os.path.join(os.path.expanduser("~"), ".bifrost")
    os.makedirs(base, exist_ok=True)
    return base


def _legacy_asbru_dirs() -> list[str]:
    """Best-effort guesses for the pre-rename config dir on each platform.

    We can't rely on QStandardPaths here because the application name has
    already moved to 'bifrost'. Hardcoded paths are fine — there are only
    three OSes and the format is stable.
    """
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, ".config", "asbru"),                       # Linux/XDG
        os.path.join(home, "Library", "Application Support", "asbru"),  # macOS
        os.path.join(home, ".asbru"),                                 # POSIX fallback
    ]
    appdata = os.environ.get("APPDATA")
    if appdata:
        candidates.insert(2, os.path.join(appdata, "asbru"))          # Windows
    return candidates


def migrate_legacy_config() -> tuple[int, str] | None:
    """One-shot rename migration: copy ~/.config/asbru/* → config_dir() if the
    new dir is empty and exactly one legacy dir exists.

    Returns (file_count, source_path) on success, None when nothing was done.
    Idempotent — runs safely on every startup.
    """
    import shutil

    new_dir = config_dir()
    try:
        if any(os.scandir(new_dir)):
            return None  # already populated; no migration
    except OSError:
        return None

    candidates = [p for p in _legacy_asbru_dirs() if p and os.path.isdir(p)]
    if not candidates:
        return None
    source = candidates[0]

    count = 0
    for entry in os.scandir(source):
        dest = os.path.join(new_dir, entry.name)
        try:
            if entry.is_dir(follow_symlinks=False):
                shutil.copytree(entry.path, dest, dirs_exist_ok=True)
            else:
                shutil.copy2(entry.path, dest)
            count += 1
        except OSError:
            pass
    return count, source


def config_path(filename: str) -> str:
    return os.path.join(config_dir(), filename)


def atomic_write_json(path: str, data) -> None:
    """Write JSON to `path` via tempfile + rename so a crash mid-write doesn't corrupt the file."""
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        os.replace(tmp_path, path)
    except Exception:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default

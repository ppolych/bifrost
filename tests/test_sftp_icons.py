"""SFTP browser icon selection."""

from __future__ import annotations

import stat
from types import SimpleNamespace

import pytest


def _fake_attr(name: str, mode: int, size: int = 0, mtime: int | None = None):
    return SimpleNamespace(filename=name, st_mode=mode, st_size=size, st_mtime=mtime)


@pytest.fixture
def browser(qapp):
    from widgets.sftp_browser import SftpBrowser
    return SftpBrowser()


def test_directory_uses_dir_icon(browser):
    icon = browser._icon_for("src", _fake_attr("src", stat.S_IFDIR | 0o755))
    # Comparing QIcon equality is fiddly across Qt versions; check cacheKey is
    # equal to the cached dir icon (different from the file icon).
    assert icon.cacheKey() == browser._dir_icon.cacheKey()
    assert icon.cacheKey() != browser._file_icon.cacheKey()


def test_symlink_uses_link_icon(browser):
    icon = browser._icon_for("ln", _fake_attr("ln", stat.S_IFLNK | 0o777))
    assert icon.cacheKey() == browser._link_icon.cacheKey()


def test_regular_file_without_known_extension_uses_generic_file_icon(browser):
    icon = browser._icon_for("README", _fake_attr("README", stat.S_IFREG | 0o644))
    # Either freedesktop theme picked it up (rare in headless) or we fall through.
    # In either case, it must not be the dir icon.
    assert icon.cacheKey() != browser._dir_icon.cacheKey()


def test_known_extensions_are_mapped(browser):
    """The extension map covers the obvious file types."""
    from widgets.sftp_browser import _EXT_THEME_ICONS

    for ext in (".py", ".sh", ".json", ".yaml", ".png", ".pdf", ".zip", ".mp4"):
        assert ext in _EXT_THEME_ICONS, ext

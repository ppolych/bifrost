"""Drag-and-drop upload tests.

We don't synthesize Qt drag events (they're flaky in offscreen mode). Instead
we verify the orchestration: target-dir resolution and queue handling, both
of which are unit-level.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def browser(qapp):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItem
    from widgets.sftp_browser import SftpBrowser

    b = SftpBrowser()
    b.cwd = "/home/user"
    # Seed two rows: one directory and one file with the right userData shape.
    dir_item = QTreeWidgetItem(b.tree, ["src", "<DIR>", "—"])
    dir_item.setData(0, Qt.ItemDataRole.UserRole, {"is_dir": True, "name": "src"})
    file_item = QTreeWidgetItem(b.tree, ["README", "1 KB", "—"])
    file_item.setData(0, Qt.ItemDataRole.UserRole, {"is_dir": False, "name": "README"})
    b._dir_item = dir_item
    b._file_item = file_item
    return b


def test_target_dir_uses_cwd_when_dropped_in_empty_area(browser):
    from PyQt6.QtCore import QPoint

    # Drop coords far outside the tree area.
    assert browser._target_dir_for_drop(QPoint(-1000, -1000)) == "/home/user"


def test_target_dir_uses_directory_when_dropped_on_dir_row(browser):
    rect = browser.tree.visualItemRect(browser._dir_item)
    # Translate the tree's rect into browser coords.
    center_in_tree = rect.center()
    center_in_browser = browser.tree.mapTo(browser, center_in_tree)
    assert browser._target_dir_for_drop(center_in_browser) == "/home/user/src"


def test_target_dir_falls_through_when_dropped_on_file_row(browser):
    rect = browser.tree.visualItemRect(browser._file_item)
    center_in_browser = browser.tree.mapTo(browser, rect.center())
    # Dropping on a file row uploads to cwd (not into "the file").
    assert browser._target_dir_for_drop(center_in_browser) == "/home/user"


def test_accept_drops_is_enabled(browser):
    assert browser.acceptDrops()


def test_drop_queues_files_when_already_transferring(browser, tmp_path, monkeypatch):
    """If a transfer is in-flight when the drop fires, new files go into the
    queue instead of clobbering the current transfer."""
    # Pretend SFTP is attached so the gate passes.
    browser.sftp = MagicMock()
    browser.sftp.stat.side_effect = OSError("missing")
    # Pretend a transfer is already running.
    browser._transfer = MagicMock()

    started: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        browser, "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )

    f1 = tmp_path / "a.txt"
    f1.write_text("a")
    f2 = tmp_path / "b.txt"
    f2.write_text("b")

    event = _make_drop_event([str(f1), str(f2)])
    browser.dropEvent(event)

    # Nothing started — current transfer keeps going; both files queued.
    assert started == []
    assert len(browser._upload_queue) == 2


def test_drop_starts_first_and_queues_rest_when_idle(browser, tmp_path, monkeypatch):
    browser.sftp = MagicMock()
    browser.sftp.stat.side_effect = OSError("missing")
    browser._transfer = None

    started: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        browser, "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )

    f1 = tmp_path / "a.txt"; f1.write_text("a")
    f2 = tmp_path / "b.txt"; f2.write_text("b")
    f3 = tmp_path / "c.txt"; f3.write_text("c")
    event = _make_drop_event([str(f1), str(f2), str(f3)])
    browser.dropEvent(event)

    assert len(started) == 1
    assert started[0][0] == "upload"
    assert started[0][2] == "/home/user/a.txt"
    assert len(browser._upload_queue) == 2  # b and c remain queued


def test_drop_queues_directories_recursively(browser, tmp_path, monkeypatch):
    browser.sftp = MagicMock()
    browser.sftp.stat.side_effect = OSError("missing")
    browser._transfer = None
    started: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        browser, "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )

    sub = tmp_path / "sub"
    sub.mkdir()
    f = tmp_path / "x.txt"
    f.write_text("x")
    browser.dropEvent(_make_drop_event([str(sub), str(f)]))

    assert len(started) == 1
    assert started[0][1] == str(sub)
    assert started[0][2] == "/home/user/sub"
    assert browser._upload_queue == [(str(f), "/home/user/x.txt")]


def test_drop_ignored_when_no_sftp(browser, tmp_path, monkeypatch):
    browser.sftp = None
    started: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        browser, "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )
    f = tmp_path / "x.txt"; f.write_text("x")
    event = _make_drop_event([str(f)])
    browser.dropEvent(event)
    assert started == []
    # The event must be ignored so the drag source sees a rejection.
    assert event.ignored is True


# ---------------------------------------------------------------------------
# Tiny test double for QDropEvent — covers what dropEvent actually touches.
# ---------------------------------------------------------------------------

class _FakeUrl:
    def __init__(self, path: str):
        self._path = path

    def isLocalFile(self) -> bool:
        return True

    def toLocalFile(self) -> str:
        return self._path


class _FakeMime:
    def __init__(self, paths: list[str]):
        self._urls = [_FakeUrl(p) for p in paths]

    def hasUrls(self) -> bool:
        return bool(self._urls)

    def urls(self):
        return self._urls


class _FakeDropEvent:
    def __init__(self, paths: list[str]):
        self._mime = _FakeMime(paths)
        self.ignored = False
        self.accepted = False

    def mimeData(self):
        return self._mime

    def position(self):
        from PyQt6.QtCore import QPointF
        return QPointF(-1000, -1000)  # outside the tree → target is cwd

    def acceptProposedAction(self):
        self.accepted = True

    def ignore(self):
        self.ignored = True


def _make_drop_event(paths: list[str]) -> _FakeDropEvent:
    return _FakeDropEvent(paths)

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


def test_cleanup_transfer_chains_queue(browser, monkeypatch):
    browser.sftp = MagicMock()
    started: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        browser, "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )
    browser._upload_queue = [("/a", "/r/a"), ("/b", "/r/b")]
    # Simulate transfer just finished.
    browser._transfer = MagicMock()
    browser._cleanup_transfer()
    assert started == [("upload", "/a", "/r/a")]
    assert browser._upload_queue == [("/b", "/r/b")]


def test_cleanup_transfer_hides_progress_when_queue_empty(browser):
    browser._begin_transfer_progress("download", "C:/tmp/report.log", "/var/log/report.log")
    browser._transfer = MagicMock()

    browser._cleanup_transfer()

    assert browser.transfer_panel.isHidden()
    assert browser.progress.value() == 0
    assert browser.transfer_status.text() == ""


def test_transfer_progress_shows_upload_bytes(browser):
    browser._begin_transfer_progress("upload", "C:/tmp/archive.tar", "/remote/archive.tar")
    browser._on_transfer_progress(512, 2048)

    assert not browser.transfer_panel.isHidden()
    assert browser.progress.value() == 25
    assert browser.progress.format() == "25%"
    assert "Uploading archive.tar" in browser.transfer_status.text()
    assert "512 B / 2.0 KB" in browser.transfer_status.text()


def test_transfer_progress_shows_download_name_and_completion(browser):
    browser._begin_transfer_progress("download", "C:/tmp/report.log", "/var/log/report.log")
    browser._on_transfer_progress(5 * 1024 * 1024, 10 * 1024 * 1024)
    browser._on_transfer_done("Downloaded report.log")

    assert browser.progress.value() == 100
    assert browser.progress.format() == "100%"
    assert browser.transfer_status.text() == "Downloaded report.log"

    browser._cleanup_transfer()
    assert browser.transfer_panel.isHidden()


def test_detach_hides_transfer_progress(browser):
    browser._begin_transfer_progress("upload", "C:/tmp/a.txt", "/remote/a.txt")
    browser.detach()

    assert browser.transfer_panel.isHidden()
    assert browser.progress.value() == 0

def test_remote_path_for_item_tracks_tree_metadata(browser):
    assert browser._remote_path_for_item(browser._file_item) == "/home/user/README"
    assert browser._remote_path_for_item(browser._dir_item) == "/home/user/src"


def test_open_remote_folder_refreshes_listing(browser, monkeypatch):
    refreshed = []
    monkeypatch.setattr(browser, "_refresh", lambda: refreshed.append(True))

    browser._open_remote_folder("/home/user/src")

    assert browser.cwd == "/home/user/src"
    assert refreshed == [True]


def test_delete_remote_file_uses_remove(browser, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    browser.sftp = MagicMock()
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(browser, "_refresh", lambda: None)

    browser._delete_remote("/home/user/README", is_dir=False)

    browser.sftp.remove.assert_called_once_with("/home/user/README")
    browser.sftp.rmdir.assert_not_called()


def test_delete_remote_folder_recursively_removes_contents(browser, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    browser.sftp = MagicMock()
    attr = lambda name, mode: type("Attr", (), {"filename": name, "st_mode": mode})()
    browser.sftp.listdir_attr.side_effect = lambda path: {
        "/home/user/src": [
            attr("README.md", 0o100644),
            attr("nested", 0o040755),
        ],
        "/home/user/src/nested": [
            attr("child.txt", 0o100644),
        ],
    }[path]
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(browser, "_refresh", lambda: None)

    browser._delete_remote("/home/user/src", is_dir=True)

    assert browser.sftp.remove.call_args_list == [
        (("/home/user/src/README.md",),),
        (("/home/user/src/nested/child.txt",),),
    ]
    assert browser.sftp.rmdir.call_args_list == [
        (("/home/user/src/nested",),),
        (("/home/user/src",),),
    ]


def test_edit_permissions_applies_octal_mode(browser, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    browser.sftp = MagicMock()
    browser.sftp.stat.return_value = type("Attr", (), {"st_mode": 0o100644})()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("600", True))
    monkeypatch.setattr(browser, "_refresh", lambda: None)

    browser._edit_permissions("/home/user/README", browser._file_item)

    browser.sftp.chmod.assert_called_once_with("/home/user/README", 0o600)


def test_transfer_thread_uploads_local_directory_recursively(qapp, tmp_path):
    from widgets.sftp_browser import _TransferThread

    root = tmp_path / "bundle"
    nested = root / "nested"
    nested.mkdir(parents=True)
    (root / "a.txt").write_text("a")
    (nested / "b.txt").write_text("bb")

    class FakeSftp:
        def __init__(self):
            self.mkdirs = []
            self.puts = []

        def mkdir(self, remote):
            self.mkdirs.append(remote)

        def put(self, local, remote, callback=None):
            self.puts.append((os.path.basename(local), remote))
            if callback:
                size = os.path.getsize(local)
                callback(size, size)

    fake = FakeSftp()
    thread = _TransferThread(fake, "upload", str(root), "/remote/bundle")
    total = thread._local_size(str(root))
    done = thread._upload_dir(str(root), "/remote/bundle", 0, total)

    assert done == 3
    assert fake.mkdirs == ["/remote/bundle", "/remote/bundle/nested"]
    assert fake.puts == [
        ("a.txt", "/remote/bundle/a.txt"),
        ("b.txt", "/remote/bundle/nested/b.txt"),
    ]


def test_download_remote_folder_uses_directory_picker(browser, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog

    browser.sftp = MagicMock()
    started = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "C:/Downloads")
    monkeypatch.setattr(
        browser,
        "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )

    browser._download_remote("/home/user/src", is_dir=True)

    assert started == [("download", os.path.join("C:/Downloads", "src"), "/home/user/src")]


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

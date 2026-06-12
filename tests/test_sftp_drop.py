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


def test_failed_transfer_does_not_auto_start_next_queued(browser, monkeypatch):
    browser.sftp = MagicMock()
    started = []
    monkeypatch.setattr(
        browser,
        "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )
    browser._transfer = MagicMock()
    browser._upload_queue = [("/a", "/r/a")]
    browser._last_transfer_failed = True

    browser._cleanup_transfer()

    assert started == []
    assert browser._upload_queue == [("/a", "/r/a")]


def test_transfer_queue_records_queued_and_done(browser):
    browser._add_queued_transfer("upload", "/tmp/a.txt", "/remote/a.txt")
    assert browser.transfer_queue.topLevelItemCount() == 1
    assert browser.transfer_queue.topLevelItem(0).text(0) == "Queued"

    browser._mark_transfer_active("upload", "/tmp/a.txt", "/remote/a.txt")
    assert browser.transfer_queue.topLevelItemCount() == 1
    active = browser.transfer_queue.topLevelItem(0)
    assert active.text(0) == "Active"

    browser._mark_transfer_finished("Done")
    assert active.text(0) == "Done"


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


def test_sftp_tree_allows_extended_row_selection(browser):
    from PyQt6.QtWidgets import QAbstractItemView

    assert browser.tree.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection
    assert browser.tree.selectionBehavior() == QAbstractItemView.SelectionBehavior.SelectRows


def test_selected_remote_items_returns_all_selected_rows(browser):
    browser._dir_item.setSelected(True)
    browser._file_item.setSelected(True)

    assert browser._selected_remote_items() == [
        ("/home/user/src", True),
        ("/home/user/README", False),
    ]


def test_download_selected_items_starts_first_and_queues_rest(browser, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog

    browser.sftp = MagicMock()
    browser._transfer = None
    browser._dir_item.setSelected(True)
    browser._file_item.setSelected(True)
    started = []
    queued = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "C:/Downloads")
    monkeypatch.setattr(
        browser,
        "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )
    monkeypatch.setattr(
        browser,
        "_add_queued_transfer",
        lambda mode, local, remote: queued.append((mode, local, remote)),
    )

    browser._download()

    assert started == [("download", os.path.join("C:/Downloads", "src"), "/home/user/src")]
    assert browser._download_queue == [(os.path.join("C:/Downloads", "README"), "/home/user/README")]
    assert queued == [("download", os.path.join("C:/Downloads", "README"), "/home/user/README")]


def test_download_selected_items_sanitizes_local_names(browser, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog

    browser.sftp = MagicMock()
    started = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "C:/Downloads")
    monkeypatch.setattr(
        browser,
        "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )

    browser._download_remote_items([
        ("/home/user/bad:name?.txt", False),
        ("/home/user/trailing. ", False),
    ])

    assert started == [("download", os.path.join("C:/Downloads", "bad_name_.txt"), "/home/user/bad:name?.txt")]
    assert browser._download_queue == [(os.path.join("C:/Downloads", "trailing"), "/home/user/trailing. ")]


def test_safe_local_name_avoids_windows_reserved_device_names():
    from widgets.sftp_browser import _safe_local_name

    assert _safe_local_name("CON") == "CON_"
    assert _safe_local_name("com1.txt") == "com1_.txt"
    assert _safe_local_name("report.txt") == "report.txt"


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


def test_transfer_thread_reports_eof_error(qapp, tmp_path):
    from widgets.sftp_browser import _TransferThread

    local = tmp_path / "upload.txt"
    local.write_text("data")

    class FakeSftp:
        def put(self, local_path, remote_path, callback=None):
            raise EOFError()

    failures = []
    thread = _TransferThread(FakeSftp(), "upload", str(local), "/remote/upload.txt")
    thread.failed.connect(failures.append)

    thread.run()

    assert failures == ["EOFError"]


def test_transfer_thread_does_not_report_success_after_cancel(qapp, tmp_path):
    from widgets.sftp_browser import _TransferThread

    local = tmp_path / "download.txt"

    class FakeSftp:
        def stat(self, remote_path):
            return type("Attr", (), {"st_mode": 0o100644, "st_size": 4})()

        def get(self, remote_path, local_path, callback=None):
            if callback:
                callback(4, 4)

    thread = _TransferThread(FakeSftp(), "download", str(local), "/remote/download.txt")
    done = []
    cancelled = []
    thread.finished_ok.connect(done.append)
    thread.cancelled.connect(cancelled.append)

    thread.cancel()
    thread.run()

    assert done == []
    assert cancelled == ["Transfer cancelled"]


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


def test_download_remote_folder_sanitizes_local_folder_name(browser, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog

    browser.sftp = MagicMock()
    started = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "C:/Downloads")
    monkeypatch.setattr(
        browser,
        "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )

    browser._download_remote("/home/user/bad:folder?", is_dir=True)

    assert started == [("download", os.path.join("C:/Downloads", "bad_folder_"), "/home/user/bad:folder?")]


def test_transfer_thread_download_dir_sanitizes_local_child_names(qapp, tmp_path):
    from widgets.sftp_browser import _TransferThread

    class FakeSftp:
        def listdir_attr(self, remote):
            return [
                type("Attr", (), {"filename": "bad:name?.txt", "st_mode": 0o100644, "st_size": 4})(),
            ]

        def get(self, remote, local, callback=None):
            if callback:
                callback(4, 4)
            with open(local, "w", encoding="utf-8") as f:
                f.write("data")

    thread = _TransferThread(FakeSftp(), "download", str(tmp_path), "/remote")
    done = thread._download_dir("/remote", str(tmp_path), 0, 4)

    assert done == 4
    assert (tmp_path / "bad_name_.txt").read_text() == "data"


def test_new_folder_creates_remote_directory(browser, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    browser.sftp = MagicMock()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("new-dir", True))
    monkeypatch.setattr(browser, "_refresh", lambda: None)

    browser._new_folder()

    browser.sftp.mkdir.assert_called_once_with("/home/user/new-dir")


def test_new_folder_rejects_path_like_name(browser, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox

    warnings = []
    browser.sftp = MagicMock()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("../bad", True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))

    browser._new_folder()

    browser.sftp.mkdir.assert_not_called()
    assert warnings


def test_rename_remote_rejects_path_like_name(browser, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox

    warnings = []
    browser.sftp = MagicMock()
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("nested/name", True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))

    browser._rename_remote("/home/user/README")

    browser.sftp.rename.assert_not_called()
    assert warnings


def test_cancel_transfer_marks_thread_cancelled(browser):
    thread = MagicMock()
    browser._transfer = thread

    browser._cancel_transfer()

    thread.cancel.assert_called_once()
    assert not browser.cancel_btn.isEnabled()


def test_cancel_transfer_closes_sftp_to_unblock_download(browser):
    thread = MagicMock()
    sftp = MagicMock()
    browser._transfer = thread
    browser.sftp = sftp

    browser._cancel_transfer()

    assert browser.sftp is None
    sftp.close.assert_called_once()
    thread.cancel.assert_called_once()


def test_cancelled_cleanup_reopens_sftp_and_does_not_chain_queue(browser, monkeypatch):
    old_sftp = MagicMock()
    new_sftp = MagicMock()
    ssh_client = MagicMock()
    ssh_client.open_sftp.return_value = new_sftp
    browser._ssh_client = ssh_client
    browser.sftp = old_sftp
    browser._transfer = MagicMock()
    browser._last_transfer_cancelled = True
    browser._download_queue = [("/tmp/a", "/remote/a")]
    browser._upload_queue = [("/tmp/b", "/remote/b")]
    started = []
    monkeypatch.setattr(browser, "_start_transfer", lambda *args: started.append(args))
    monkeypatch.setattr(browser, "_refresh", lambda: None)

    browser._cleanup_transfer()

    assert browser.sftp is new_sftp
    assert started == []
    assert browser._download_queue == [("/tmp/a", "/remote/a")]
    assert browser._upload_queue == [("/tmp/b", "/remote/b")]


def test_stale_transfer_cleanup_does_not_clear_current_transfer(browser, monkeypatch):
    old_thread = MagicMock()
    current_thread = MagicMock()
    browser._transfer = current_thread
    browser._last_transfer_cancelled = True
    monkeypatch.setattr(browser, "_reopen_sftp_after_cancel", lambda: None)

    browser._cleanup_transfer(old_thread)

    assert browser._transfer is current_thread
    assert browser._last_transfer_cancelled is True


def test_detach_does_not_reopen_sftp_after_cancel_cleanup(browser, monkeypatch):
    browser._detaching = True
    browser._transfer = MagicMock()
    browser._last_transfer_cancelled = True
    reopened = []
    monkeypatch.setattr(browser, "_reopen_sftp_after_cancel", lambda: reopened.append(True))

    browser._cleanup_transfer(browser._transfer)

    assert reopened == []
    assert browser._transfer is None


def test_stuck_cancelled_transfer_detaches_ui_and_reopens_sftp(browser, monkeypatch):
    old_sftp = MagicMock()
    new_sftp = MagicMock()
    ssh_client = MagicMock()
    ssh_client.open_sftp.return_value = new_sftp
    transfer = MagicMock()
    transfer.isRunning.return_value = True
    browser._ssh_client = ssh_client
    browser.sftp = old_sftp
    browser._transfer = transfer
    browser._last_transfer_cancelled = True
    monkeypatch.setattr(browser, "_disconnect_transfer_signals", lambda t: None)
    monkeypatch.setattr(browser, "_refresh", lambda: None)

    browser._finish_stuck_cancelled_transfer(transfer)

    assert browser._transfer is None
    assert browser._last_transfer_cancelled is False
    assert browser.sftp is new_sftp
    assert not browser.cancel_btn.isEnabled()


def test_upload_conflict_skip_apply_all(browser, monkeypatch):
    browser.sftp = MagicMock()
    browser.sftp.stat.return_value = object()
    monkeypatch.setattr(browser, "_prompt_upload_conflict", lambda remote: ("skip", True))

    resolved = browser._resolve_upload_conflicts([
        ("/tmp/a.txt", "/home/user/a.txt"),
        ("/tmp/b.txt", "/home/user/b.txt"),
    ])

    assert resolved == []


def test_upload_conflict_overwrite_apply_all(browser, monkeypatch):
    browser.sftp = MagicMock()
    browser.sftp.stat.return_value = object()
    prompts = []

    def prompt(remote):
        prompts.append(remote)
        return "overwrite", True

    monkeypatch.setattr(browser, "_prompt_upload_conflict", prompt)

    queue = [
        ("/tmp/a.txt", "/home/user/a.txt"),
        ("/tmp/b.txt", "/home/user/b.txt"),
    ]
    assert browser._resolve_upload_conflicts(queue) == queue
    assert prompts == ["/home/user/a.txt"]


def test_upload_conflict_rename(browser, monkeypatch):
    browser.sftp = MagicMock()

    def stat(remote):
        if remote in {"/home/user/a.txt", "/home/user/a (1).txt"}:
            return object()
        raise OSError("missing")

    browser.sftp.stat.side_effect = stat
    monkeypatch.setattr(browser, "_prompt_upload_conflict", lambda remote: ("rename", False))
    monkeypatch.setattr(browser, "_prompt_remote_rename", lambda remote: "/home/user/a (2).txt")

    assert browser._resolve_upload_conflicts([
        ("/tmp/a.txt", "/home/user/a.txt"),
    ]) == [("/tmp/a.txt", "/home/user/a (2).txt")]


def test_upload_conflict_rename_rejects_path_like_name(browser, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog, QMessageBox

    warnings = []
    browser.sftp = MagicMock()
    browser.sftp.stat.side_effect = OSError("missing")
    monkeypatch.setattr(QInputDialog, "getText", lambda *args, **kwargs: ("../renamed", True))
    monkeypatch.setattr(QMessageBox, "warning", lambda *args, **kwargs: warnings.append(args))

    assert browser._prompt_remote_rename("/home/user/a.txt") is None
    assert warnings


def test_next_available_remote_name(browser):
    browser.sftp = MagicMock()

    def stat(remote):
        if remote in {"/home/user/a.txt", "/home/user/a (1).txt"}:
            return object()
        raise OSError("missing")

    browser.sftp.stat.side_effect = stat

    assert browser._next_available_remote_name("/home/user/a.txt") == "/home/user/a (2).txt"


def test_remote_exists_treats_ssh_exception_as_missing(browser):
    import paramiko

    browser.sftp = MagicMock()
    browser.sftp.stat.side_effect = paramiko.SSHException("channel closed")

    assert browser._remote_exists("/home/user/a.txt") is False


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

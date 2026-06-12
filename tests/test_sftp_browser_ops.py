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
    dir_item = QTreeWidgetItem(b.tree, ["src", "<DIR>", "-"])
    dir_item.setData(0, Qt.ItemDataRole.UserRole, {"is_dir": True, "name": "src"})
    file_item = QTreeWidgetItem(b.tree, ["README", "1 KB", "-"])
    file_item.setData(0, Qt.ItemDataRole.UserRole, {"is_dir": False, "name": "README"})
    b._dir_item = dir_item
    b._file_item = file_item
    return b


def test_cleanup_transfer_chains_queue(browser, monkeypatch):
    browser.sftp = MagicMock()
    started: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        browser, "_start_transfer",
        lambda mode, local, remote: started.append((mode, local, remote)),
    )
    browser._upload_queue = [("/a", "/r/a"), ("/b", "/r/b")]
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
    monkeypatch.setattr(browser, "_start_transfer", lambda mode, local, remote: started.append((mode, local, remote)))
    monkeypatch.setattr(browser, "_add_queued_transfer", lambda mode, local, remote: queued.append((mode, local, remote)))

    browser._download()

    assert started == [("download", os.path.join("C:/Downloads", "src"), "/home/user/src")]
    assert browser._download_queue == [(os.path.join("C:/Downloads", "README"), "/home/user/README")]
    assert queued == [("download", os.path.join("C:/Downloads", "README"), "/home/user/README")]


def test_download_selected_items_sanitizes_local_names(browser, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog

    browser.sftp = MagicMock()
    started = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "C:/Downloads")
    monkeypatch.setattr(browser, "_start_transfer", lambda mode, local, remote: started.append((mode, local, remote)))

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
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(browser, "_refresh", lambda: None)

    browser._delete_remote("/home/user/README", is_dir=False)

    browser.sftp.remove.assert_called_once_with("/home/user/README")
    browser.sftp.rmdir.assert_not_called()


def test_delete_remote_folder_recursively_removes_contents(browser, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    browser.sftp = MagicMock()
    attr = lambda name, mode: type("Attr", (), {"filename": name, "st_mode": mode})()
    browser.sftp.listdir_attr.side_effect = lambda path: {
        "/home/user/src": [attr("README.md", 0o100644), attr("nested", 0o040755)],
        "/home/user/src/nested": [attr("child.txt", 0o100644)],
    }[path]
    monkeypatch.setattr(QMessageBox, "question", lambda *args, **kwargs: QMessageBox.StandardButton.Yes)
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

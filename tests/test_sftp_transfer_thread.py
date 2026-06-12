import os

import pytest


@pytest.fixture
def browser(qapp):
    from widgets.sftp_browser import SftpBrowser

    b = SftpBrowser()
    b.cwd = "/home/user"
    return b


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
    from unittest.mock import MagicMock

    browser.sftp = MagicMock()
    started = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "C:/Downloads")
    monkeypatch.setattr(browser, "_start_transfer", lambda mode, local, remote: started.append((mode, local, remote)))

    browser._download_remote("/home/user/src", is_dir=True)

    assert started == [("download", os.path.join("C:/Downloads", "src"), "/home/user/src")]


def test_download_remote_folder_sanitizes_local_folder_name(browser, monkeypatch):
    from PyQt6.QtWidgets import QFileDialog
    from unittest.mock import MagicMock

    browser.sftp = MagicMock()
    started = []
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", lambda *args, **kwargs: "C:/Downloads")
    monkeypatch.setattr(browser, "_start_transfer", lambda mode, local, remote: started.append((mode, local, remote)))

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

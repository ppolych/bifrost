from unittest.mock import MagicMock

import pytest


@pytest.fixture
def browser(qapp):
    from widgets.sftp_browser import SftpBrowser

    b = SftpBrowser()
    b.cwd = "/home/user"
    return b


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


def test_cancel_transfer_clears_pending_queue(browser, monkeypatch):
    new_sftp = MagicMock()
    ssh_client = MagicMock()
    ssh_client.open_sftp.return_value = new_sftp
    browser._ssh_client = ssh_client
    browser.sftp = MagicMock()
    browser._transfer = MagicMock()
    browser._download_queue = [("/tmp/a", "/remote/a")]
    browser._upload_queue = [("/tmp/b", "/remote/b")]
    browser._add_queued_transfer("download", "/tmp/a", "/remote/a")
    browser._add_queued_transfer("upload", "/tmp/b", "/remote/b")
    started = []
    monkeypatch.setattr(browser, "_start_transfer", lambda *args: started.append(args))
    monkeypatch.setattr(browser, "_refresh", lambda: None)

    browser._cancel_transfer()
    browser._cleanup_transfer()

    assert browser.sftp is new_sftp
    assert started == []
    assert browser._download_queue == []
    assert browser._upload_queue == []
    assert browser.transfer_queue.topLevelItemCount() == 0


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
    new_sftp = MagicMock()
    ssh_client = MagicMock()
    ssh_client.open_sftp.return_value = new_sftp
    transfer = MagicMock()
    transfer.isRunning.return_value = True
    browser._ssh_client = ssh_client
    browser.sftp = MagicMock()
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

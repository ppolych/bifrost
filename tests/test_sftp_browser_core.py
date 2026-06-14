import posixpath
import stat
from unittest.mock import MagicMock


def test_sftp_format_size():
    from widgets.sftp_browser import _format_size

    assert _format_size(0) == "0 B"
    assert _format_size(512) == "512 B"
    assert _format_size(2048) == "2.0 KB"
    assert _format_size(5 * 1024 * 1024) == "5.0 MB"


def test_sftp_path_navigation_uses_posix(qapp):
    """Even on Windows, remote paths must stay POSIX."""
    from widgets.sftp_browser import SftpBrowser

    browser = SftpBrowser()
    fake_sftp = MagicMock()
    fake_sftp.listdir_attr.return_value = []
    fake_sftp.normalize.return_value = "/home/user"

    fake_client = MagicMock()
    fake_client.open_sftp.return_value = fake_sftp

    browser.attach(fake_client)
    assert browser.cwd == "/home/user"

    browser.cwd = posixpath.join(browser.cwd, "sub")
    browser._refresh()
    assert browser.cwd == "/home/user/sub"

    browser._go_up()
    assert browser.cwd == "/home/user"

    browser.detach()
    assert not browser.is_attached()


def test_sftp_listing_shows_parent_directory_row(qapp):
    from PyQt6.QtCore import Qt
    from widgets.sftp_browser import SftpBrowser

    attr = type("Attr", (), {"filename": "src", "st_mode": stat.S_IFDIR | 0o755, "st_size": 0, "st_mtime": 0})()
    browser = SftpBrowser()
    browser.sftp = MagicMock()
    browser.sftp.listdir_attr.return_value = [attr]
    browser.cwd = "/home/user"

    browser._refresh()

    parent = browser.tree.topLevelItem(0)
    child = browser.tree.topLevelItem(1)
    assert parent.text(0) == ".."
    assert parent.data(0, Qt.ItemDataRole.UserRole)["is_parent"] is True
    assert child.text(0) == "src"
    assert browser._remote_path_for_item(parent) is None


def test_sftp_parent_directory_row_goes_up_on_double_click(qapp):
    from widgets.sftp_browser import SftpBrowser

    browser = SftpBrowser()
    browser.sftp = MagicMock()
    browser.sftp.listdir_attr.return_value = []
    browser.cwd = "/home/user/project"
    browser._refresh()

    parent = browser.tree.topLevelItem(0)
    browser._on_double_click(parent, 0)

    assert browser.cwd == "/home/user"


def test_sftp_root_does_not_show_parent_directory_row(qapp):
    from widgets.sftp_browser import SftpBrowser

    browser = SftpBrowser()
    browser.sftp = MagicMock()
    browser.sftp.listdir_attr.return_value = []
    browser.cwd = "/"

    browser._refresh()

    assert browser.tree.topLevelItemCount() == 0

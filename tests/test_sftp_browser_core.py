import posixpath
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

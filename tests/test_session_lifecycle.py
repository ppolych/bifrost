"""Session creation routing and remote-file context changes."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("session, method, kwargs", [
    ({"type": "Telnet", "host": "router", "port": 2323}, "new_terminal_tab",
     {"kind": "Telnet", "host": "router", "port": 2323}),
    ({"type": "Serial", "device": "/dev/ttyUSB0", "baudrate": 9600}, "new_terminal_tab",
     {"kind": "Serial", "device": "/dev/ttyUSB0", "baud": 9600}),
    ({"type": "Local", "cmd": ["sh", "-l"]}, "new_terminal_tab",
     {"command": ["sh", "-l"]}),
    ({"type": "VNC", "host": "desktop"}, "open_vnc_session", {}),
    ({"type": "RDP", "host": "desktop"}, "open_rdp_session", {}),
])
def test_new_session_uses_protocol_router(monkeypatch, session, method, kwargs):
    from bifrost_app_persistence_tabs import BifrostPersistenceTabsMixin
    from bifrost_app_sessions import BifrostSessionsMixin

    class App(BifrostPersistenceTabsMixin, BifrostSessionsMixin):
        pass

    app = App()
    app.session_manager = MagicMock()
    app.sidebar = MagicMock()
    app._refresh_credentials_view = MagicMock()
    app.new_terminal_tab = MagicMock()
    app.open_vnc_session = MagicMock()
    app.open_rdp_session = MagicMock()
    session = {"name": "new session", **session}
    dialog = MagicMock()
    dialog.get_data.return_value = session
    monkeypatch.setattr("bifrost_app_persistence_tabs.SessionDialog", lambda _: dialog)

    app.open_session_dialog()

    if method == "new_terminal_tab":
        app.new_terminal_tab.assert_called_once_with(
            "new session", session_data=session, **kwargs,
        )
    else:
        getattr(app, method).assert_called_once_with(session)
        app.new_terminal_tab.assert_not_called()


@pytest.mark.parametrize("ready", [False, True])
def test_switch_to_pending_or_failed_ssh_clears_old_sftp(qapp, monkeypatch, ready):
    from bifrost_app_ssh_status import BifrostSshStatusMixin
    from widgets.sftp_browser import SftpBrowser

    app = BifrostSshStatusMixin()
    browser = SftpBrowser()
    client = MagicMock()
    client.open_sftp.return_value.normalize.return_value = "/old-host"
    client.open_sftp.return_value.listdir_attr.return_value = []
    browser.attach(client)
    app.sidebar = SimpleNamespace(sftp_widget=browser)
    app._refresh_ssh_browser = MagicMock()
    app.status_bar = MagicMock()
    backend = SimpleNamespace(
        client=None, connect_error=OSError("connection failed") if ready else None,
        wait_ready=lambda timeout: ready,
    )
    monkeypatch.setattr("bifrost_app_ssh_status.QTimer.singleShot", lambda *args: None)
    try:
        app._attach_sftp_when_ready(backend)
        assert not browser.is_attached()
        assert not browser.upload_btn.isEnabled()
        assert browser.tree.topLevelItemCount() == 0
        client.open_sftp.return_value.close.assert_called_once()
    finally:
        browser.detach()
        browser.close()


def test_last_tab_removal_clears_sftp():
    from bifrost_app_ssh_status import BifrostSshStatusMixin

    app = BifrostSshStatusMixin()
    app._refresh_ssh_browser = MagicMock()
    app.sidebar = MagicMock()
    app.remote_monitor = MagicMock()

    app.on_tab_changed(-1)

    app.sidebar.sftp_widget.detach.assert_called_once()
    app.sidebar.hide_sftp_pane.assert_called_once()

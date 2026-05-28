"""Tests for SSH backend and SFTP browser pieces that don't need a real server."""

import posixpath
from unittest.mock import MagicMock

import pytest


def test_credentials_from_session_minimal():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session({"host": "h", "user": "u", "port": "2222"})
    assert creds.host == "h"
    assert creds.username == "u"
    assert creds.port == 2222
    assert creds.auth == "agent"  # default


def test_credentials_from_session_with_key():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session(
        {
            "host": "h",
            "user": "u",
            "port": 22,
            "auth": "key",
            "key_path": "~/.ssh/id_ed25519",
            "command": "uptime",
        }
    )
    assert creds.auth == "key"
    assert creds.key_filename == "~/.ssh/id_ed25519"
    assert creds.startup_command == "uptime"


def test_credentials_from_session_with_advanced_ssh_fields():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session({
        "host": "h",
        "user": "u",
        "connect_timeout": 45,
        "agent_forwarding": True,
        "keepalive_interval": 60,
        "tcp_keepalive": True,
        "known_hosts_file": "~/.ssh/custom_known_hosts",
        "tunnels": ["L 127.0.0.1:5432 db:5432"],
    })

    assert creds.connect_timeout == 45
    assert creds.agent_forwarding is True
    assert creds.keepalive_interval == 60
    assert creds.tcp_keepalive is True
    assert creds.known_hosts_file == "~/.ssh/custom_known_hosts"
    assert creds.tunnels == ["L 127.0.0.1:5432 db:5432"]


def test_credentials_port_coercion_handles_empty():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session({"host": "h", "port": ""})
    assert creds.port == 22


def test_backend_emits_connecting_hint_before_ready():
    """Until the connect thread sets _ready, read() returns a 'Connecting…' hint
    rather than blocking the GUI thread indefinitely."""
    from core.ssh_backend import ParamikoBackend, SshCredentials

    backend = ParamikoBackend(SshCredentials(host="example.invalid", username="u"))
    # Don't call start() — _ready stays unset.
    out = backend.read()
    assert out.startswith(b"Connecting to u@example.invalid")


def test_backend_emits_error_once():
    from core.ssh_backend import ParamikoBackend, SshCredentials

    backend = ParamikoBackend(SshCredentials(host="h", username="u"))
    backend._connect_error = RuntimeError("nope")
    backend._ready.set()
    first = backend.read()
    assert b"connection failed" in first
    # Second read should not repeat the error
    second = backend.read()
    assert second == b""


def test_sftp_format_size():
    from widgets.sftp_browser import _format_size

    assert _format_size(0) == "0 B"
    assert _format_size(512) == "512 B"
    assert _format_size(2048) == "2.0 KB"
    assert _format_size(5 * 1024 * 1024) == "5.0 MB"


def test_sftp_path_navigation_uses_posix(qapp):
    """Even on Windows, remote paths must stay POSIX. Regression guard for
    accidental os.path.join usage."""
    from widgets.sftp_browser import SftpBrowser

    browser = SftpBrowser()
    fake_sftp = MagicMock()
    fake_sftp.listdir_attr.return_value = []
    fake_sftp.normalize.return_value = "/home/user"

    fake_client = MagicMock()
    fake_client.open_sftp.return_value = fake_sftp

    browser.attach(fake_client)
    assert browser.cwd == "/home/user"

    # Simulate entering a subdirectory.
    browser.cwd = posixpath.join(browser.cwd, "sub")
    browser._refresh()
    assert browser.cwd == "/home/user/sub"

    # Up should land back at parent (POSIX style).
    browser._go_up()
    assert browser.cwd == "/home/user"

    browser.detach()
    assert not browser.is_attached()


def test_session_manager_find_by_name(qapp, tmp_path, monkeypatch):
    import core.persistence as persistence

    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))

    sm = persistence.SessionManager()
    sm.add_session("User sessions", {"name": "prod-1", "type": "SSH", "host": "1.1.1.1"})
    sm.add_session("Work Folders/Production", {"name": "prod-2", "type": "SSH", "host": "2.2.2.2"})

    assert sm.find_by_name("prod-1")["host"] == "1.1.1.1"
    assert sm.find_by_name("prod-2")["host"] == "2.2.2.2"
    assert sm.find_by_name("missing") is None


def test_session_dialog_emits_ssh_auth_fields(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog()
    # default is SSH tab + agent auth
    data = dlg.get_data()
    assert data["type"] == "SSH"
    assert data["auth"] == "agent"
    assert data["host"] == "127.0.0.1"
    assert data["user"] == "root"
    assert data["port"] == "22"
    assert data["key_path"] is None
    # password is never in the dict
    assert "password" not in data


def test_session_dialog_loads_existing_ssh_session(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog(session={
        "name": "prod",
        "type": "SSH",
        "host": "prod.example.com",
        "user": "admin",
        "port": "2222",
        "auth": "key",
        "key_path": "~/.ssh/prod",
        "command": "tmux attach || tmux",
    })

    data = dlg.get_data()
    assert data["name"] == "prod"
    assert data["host"] == "prod.example.com"
    assert data["auth"] == "key"
    assert data["key_path"] == "~/.ssh/prod"
    assert data["command"] == "tmux attach || tmux"


def test_session_dialog_exposes_advanced_ssh_and_network_sections(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog(session={
        "name": "prod",
        "type": "SSH",
        "host": "prod.example.com",
        "user": "admin",
        "connect_timeout": 45,
        "agent_forwarding": True,
        "keepalive_interval": 60,
        "tcp_keepalive": True,
        "known_hosts_file": "~/.ssh/prod_known_hosts",
        "tunnels": ["D 127.0.0.1:1080"],
        "mac": "AA:BB:CC:11:22:33",
        "wol_broadcast": "10.0.0.255",
    })

    dlg.set_current_section("advanced_ssh")
    assert dlg.tabs.currentWidget() is dlg.advanced_ssh_tab
    dlg.set_current_section("network")
    assert dlg.tabs.currentWidget() is dlg.network_tab

    data = dlg.get_data()
    assert data["connect_timeout"] == 45
    assert data["agent_forwarding"] is True
    assert data["keepalive_interval"] == 60
    assert data["tcp_keepalive"] is True
    assert data["known_hosts_file"] == "~/.ssh/prod_known_hosts"
    assert data["tunnels"] == ["D 127.0.0.1:1080"]
    assert data["mac"] == "AA:BB:CC:11:22:33"
    assert data["wol_broadcast"] == "10.0.0.255"

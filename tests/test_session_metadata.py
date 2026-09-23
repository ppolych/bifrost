"""Saved session types and appearance survive terminal creation."""

import pytest

from tests.test_cluster import app


class Backend:
    def __init__(self, *args): pass
    def start(self): pass
    def read(self, size): return b""
    def write(self, data): pass
    def set_winsize(self, rows, cols): pass
    def close(self): pass


@pytest.fixture
def backends(monkeypatch):
    monkeypatch.setattr("bifrost_app_terminal_sessions.TelnetBackend", Backend)
    monkeypatch.setattr("bifrost_app_terminal_sessions.SerialBackend", Backend)
    monkeypatch.setattr("widgets.terminal.TerminalBackend", Backend)
    monkeypatch.setattr("bifrost_app_terminal_sessions.wsl.spawn_command", lambda distro: ["wsl", distro])


@pytest.mark.parametrize("kind", ["WSL", "Telnet", "Serial"])
def test_non_ssh_session_keeps_appearance_and_source(app, backends, kind):
    session = {
        "name": "saved", "type": kind, "host": "router",
        "device": "/dev/ttyUSB0", "distro": "Ubuntu",
        "overrides": {"scheme": "Solarized Dark", "font": "Monospace,19"},
    }
    app.on_session_activated(session)
    container = app.tabs.currentWidget()
    assert container.source_session_id == id(session)
    assert container.settings["term_bg"] == "#002b36"
    assert container.settings["font"].pointSize() == 19
    assert container.ssh_session is None


@pytest.mark.parametrize("kind", ["Local", "SSH"])
def test_wsl_in_name_does_not_change_session_type(app, backends, monkeypatch, kind):
    def unexpected_wsl(_distro):
        pytest.fail("Session name must not select the WSL backend")

    monkeypatch.setattr("bifrost_app_terminal_sessions.wsl.spawn_command", unexpected_wsl)
    ssh_calls = []
    monkeypatch.setattr(app, "_build_ssh_backend", lambda *args: ssh_calls.append(args) or Backend())
    session = {"name": "WSL server", "type": kind, "host": "host", "cmd": ["sh"]}
    app.on_session_activated(session)
    container = app.tabs.currentWidget()
    if kind == "SSH":
        assert ssh_calls == [(session["name"], session)]
        assert container.ssh_session == session
    else:
        assert container.command == ["sh"]
        assert not ssh_calls


def test_public_quick_connect_parser_preserves_ipv6_port():
    from bifrost_app import parse_quick_connect_command

    assert parse_quick_connect_command("Local", "ssh -p 2222 alice@2001:db8::1") == (
        "SSH", "alice@[2001:db8::1]:2222",
    )

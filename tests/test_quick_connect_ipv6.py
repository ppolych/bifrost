"""IPv6 targets must reach connection backends without truncation."""

from unittest.mock import MagicMock

import pytest

from bifrost_app_sessions import BifrostSessionsMixin


@pytest.mark.parametrize("method, default_port", [
    ("SSH", 22), ("Telnet", 23), ("VNC", 5900), ("RDP", 3389),
])
@pytest.mark.parametrize("target, host, port", [
    ("2001:db8::1", "2001:db8::1", None),
    ("::1", "::1", None),
    ("[2001:db8::1]", "2001:db8::1", None),
    ("[2001:db8::1]:2222", "2001:db8::1", 2222),
])
def test_ipv6_quick_connect(method, default_port, target, host, port):
    app = BifrostSessionsMixin()
    app.settings = {"ssh_default_user": "alice", "ssh_default_port": 22}
    app.new_terminal_tab = MagicMock()
    app.open_vnc_session = MagicMock()
    app.open_rdp_session = MagicMock()

    app.on_quick_connect(method, target)

    if method == "SSH":
        session = app.new_terminal_tab.call_args.kwargs["ssh_session"]
    elif method == "Telnet":
        session = app.new_terminal_tab.call_args.kwargs
    else:
        session = getattr(app, f"open_{method.lower()}_session").call_args.args[0]
    assert session["host"] == host
    assert int(session["port"]) == (port or default_port)


@pytest.mark.parametrize("command, method, port", [
    ("ssh -p 2222 alice@2001:db8::1", "SSH", 2222),
    ("ssh alice@[2001:db8::1] -p2222", "SSH", 2222),
    ("telnet 2001:db8::1 2323", "Telnet", 2323),
    ("rdp [2001:db8::1] 3390", "RDP", 3390),
])
def test_ipv6_command_preserves_explicit_port(command, method, port):
    app = BifrostSessionsMixin()
    app.settings = {"ssh_default_user": "", "ssh_default_port": 22}
    app.new_terminal_tab = MagicMock()
    app.open_rdp_session = MagicMock()
    app.on_quick_connect("Local", command)
    if method == "SSH":
        session = app.new_terminal_tab.call_args.kwargs["ssh_session"]
        assert session["user"] == "alice"
    elif method == "Telnet":
        session = app.new_terminal_tab.call_args.kwargs
    else:
        session = app.open_rdp_session.call_args.args[0]
    assert session["host"] == "2001:db8::1"
    assert int(session["port"]) == port


@pytest.mark.parametrize("host", ["2001:db8::1", "[2001:db8::1]"])
@pytest.mark.parametrize("system", ["Linux", "Windows"])
def test_rdp_launcher_brackets_ipv6_host(host, system):
    from core.rdp import build_rdp_command

    command = build_rdp_command(
        {"host": host, "port": 3390}, system=system,
        which=lambda name: name if name in {"xfreerdp", "mstsc.exe"} else None,
    )
    assert command[1] == "/v:[2001:db8::1]:3390"

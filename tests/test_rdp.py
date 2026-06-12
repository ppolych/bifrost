from unittest.mock import MagicMock


def test_rdp_command_uses_xfreerdp_with_custom_port_and_user():
    from core.rdp import build_rdp_command

    def fake_which(name):
        return "/usr/bin/xfreerdp" if name == "xfreerdp" else None

    command = build_rdp_command(
        {"host": "rdp.example.com", "port": "3390", "user": "alice"},
        system="Linux",
        which=fake_which,
    )

    assert command == ["/usr/bin/xfreerdp", "/v:rdp.example.com:3390", "/u:alice"]


def test_rdp_command_falls_back_to_default_port():
    from core.rdp import build_rdp_command

    def fake_which(name):
        return "/usr/bin/rdesktop" if name == "rdesktop" else None

    command = build_rdp_command(
        {"host": "rdp.example.com", "port": ""},
        system="Linux",
        which=fake_which,
    )

    assert command == ["/usr/bin/rdesktop", "rdp.example.com:3389"]


def test_rdp_command_uses_mstsc_on_windows():
    from core.rdp import build_rdp_command

    command = build_rdp_command(
        {"host": "winhost", "port": "3391"},
        system="Windows",
        which=lambda name: None,
    )

    assert command == ["mstsc.exe", "/v:winhost:3391"]


def test_rdp_command_uses_open_url_on_macos():
    from core.rdp import build_rdp_command

    command = build_rdp_command(
        {"host": "mac-host", "port": "3389"},
        system="Darwin",
        which=lambda name: "/usr/bin/open" if name == "open" else None,
    )

    assert command == ["/usr/bin/open", "rdp://full%20address=s:mac-host:3389"]


def test_session_activation_routes_rdp(qapp):
    from bifrost_app import BifrostApp

    app = BifrostApp.__new__(BifrostApp)
    received = {}
    app.open_rdp_session = lambda session: received.update(session)

    BifrostApp.on_session_activated(
        app, {"name": "desktop", "type": "RDP", "host": "h", "port": "3390"},
    )

    assert received["host"] == "h"
    assert received["port"] == "3390"


def test_quick_connect_routes_rdp(qapp):
    from bifrost_app import BifrostApp

    app = BifrostApp.__new__(BifrostApp)
    received = {}
    app.open_rdp_session = lambda session: received.update(session)

    BifrostApp.on_quick_connect(app, "RDP", "rdp.example.com:3390")

    assert received == {
        "name": "rdp.example.com:3390",
        "type": "RDP",
        "host": "rdp.example.com",
        "port": "3390",
    }


def test_open_rdp_session_reports_launcher_errors(qapp, monkeypatch):
    import bifrost_app
    from bifrost_app import BifrostApp
    from core.rdp import RdpLaunchError

    warnings = []
    app = BifrostApp.__new__(BifrostApp)
    app.session_manager = MagicMock()
    app.status_bar = MagicMock()
    monkeypatch.setattr(
        bifrost_app,
        "launch_rdp_session",
        lambda session: (_ for _ in ()).throw(RdpLaunchError("missing client")),
    )
    monkeypatch.setattr(
        bifrost_app.QMessageBox,
        "warning",
        lambda *args, **kwargs: warnings.append(args),
    )

    BifrostApp.open_rdp_session(app, {"name": "desktop", "host": "h", "port": "3389"})

    assert warnings
    app.session_manager.add_to_recents.assert_not_called()

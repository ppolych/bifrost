"""Quick-connect routing tests — verify the method dropdown lands in the
right backend path without spawning real processes/SSH sessions."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def toolbar(qapp):
    from widgets.toolbar import MainToolBar
    return MainToolBar()


def test_quick_connect_emits_method_and_text(toolbar):
    received = []
    toolbar.quick_connect_triggered.connect(lambda m, t: received.append((m, t)))

    # SSH
    toolbar.qc_method.setCurrentIndex(0)
    toolbar.qc_input.setText("alice@host:2222")
    toolbar.on_qc_enter()
    assert received[-1] == ("SSH", "alice@host:2222")

    # WSL — text may be blank, signal still fires
    toolbar.qc_method.setCurrentIndex(
        next(i for i in range(toolbar.qc_method.count())
             if toolbar.qc_method.itemData(i) == "WSL")
    )
    toolbar.qc_input.setText("")
    toolbar.on_qc_enter()
    assert received[-1] == ("WSL", "")


def test_quick_connect_ssh_skips_empty(toolbar):
    received = []
    toolbar.quick_connect_triggered.connect(lambda m, t: received.append((m, t)))
    toolbar.qc_method.setCurrentIndex(0)  # SSH
    toolbar.qc_input.setText("   ")
    toolbar.on_qc_enter()
    assert received == []


def test_placeholder_changes_with_method(toolbar):
    placeholders = set()
    for i in range(toolbar.qc_method.count()):
        toolbar.qc_method.setCurrentIndex(i)
        placeholders.add(toolbar.qc_input.placeholderText())
    assert len(placeholders) == toolbar.qc_method.count()


def _bare_app():
    """Construct an BifrostApp stub that bypasses __init__ (Qt + SessionManager + …)."""
    from bifrost_app import BifrostApp
    app = BifrostApp.__new__(BifrostApp)
    app.settings = {"ssh_default_user": "", "ssh_default_port": 22}
    return app


def test_quick_connect_ssh_parses_user_host_port(qapp):
    from bifrost_app import BifrostApp

    app = _bare_app()
    received = {}
    app.new_terminal_tab = lambda name, **k: received.update(k, name=name)
    BifrostApp.on_quick_connect(app, "SSH", "alice@10.0.0.5:2222")

    assert received["ssh_session"]["host"] == "10.0.0.5"
    assert received["ssh_session"]["user"] == "alice"
    assert received["ssh_session"]["port"] == 2222
    assert received["name"] == "alice@10.0.0.5"


def test_quick_connect_ssh_uses_default_user_when_omitted(qapp):
    from bifrost_app import BifrostApp

    app = _bare_app()
    app.settings["ssh_default_user"] = "bob"
    app.settings["ssh_default_port"] = 2200
    received = {}
    app.new_terminal_tab = lambda name, **k: received.update(k, name=name)

    BifrostApp.on_quick_connect(app, "SSH", "host.example.com")
    assert received["ssh_session"]["user"] == "bob"
    assert received["ssh_session"]["port"] == 2200


def test_quick_connect_telnet_builds_command(qapp):
    from bifrost_app import BifrostApp

    app = _bare_app()
    received = {}
    app.new_terminal_tab = lambda name, **k: received.update(k, name=name)
    BifrostApp.on_quick_connect(app, "Telnet", "bbs.example.com:23")
    assert received["command"] == ["telnet", "bbs.example.com", "23"]


def test_quick_connect_local_uses_command_path(qapp):
    from bifrost_app import BifrostApp

    app = _bare_app()
    received = {}
    app.new_terminal_tab = lambda name, **k: received.update(k, name=name)
    BifrostApp.on_quick_connect(app, "Local", "/bin/zsh")
    assert received["command"] == ["/bin/zsh"]

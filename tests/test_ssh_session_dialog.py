def test_session_dialog_emits_ssh_auth_fields(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog()
    data = dlg.get_data()
    assert data["type"] == "SSH"
    assert data["auth"] == "agent"
    assert data["host"] == "127.0.0.1"
    assert data["user"] == "root"
    assert data["port"] == "22"
    assert data["key_path"] is None
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
        "certificate_path": "~/.ssh/prod-cert.pub",
        "command": "tmux attach || tmux",
    })

    data = dlg.get_data()
    assert data["name"] == "prod"
    assert data["host"] == "prod.example.com"
    assert data["auth"] == "key"
    assert data["key_path"] == "~/.ssh/prod"
    assert data["certificate_path"] == "~/.ssh/prod-cert.pub"
    assert data["command"] == "tmux attach || tmux"


def test_session_dialog_tmux_preset_sets_startup_command(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog()
    idx = dlg.tmux_preset.findText("Attach or create")

    dlg.tmux_preset.setCurrentIndex(idx)

    assert dlg.command_input.text() == "tmux new-session -A -s main"
    assert dlg.tmux_preset.currentIndex() == 0


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
        "proxy_jump": "ops@bastion:2222",
        "proxy_command": "ssh -W %h:%p bastion",
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
    assert data["proxy_jump"] == "ops@bastion:2222"
    assert data["proxy_command"] == "ssh -W %h:%p bastion"
    assert data["tunnels"] == ["D 127.0.0.1:1080"]
    assert data["mac"] == "AA:BB:CC:11:22:33"
    assert data["wol_broadcast"] == "10.0.0.255"

def test_build_ssh_backend_prompts_for_missing_key(qapp, monkeypatch):
    from bifrost_app import BifrostApp

    app = BifrostApp.__new__(BifrostApp)
    app.settings = {
        "ssh_startup_command": "",
        "credential_save_policy": "never",
        "ssh_connect_timeout": 15,
        "ssh_agent_forwarding": False,
        "known_hosts_file": "",
        "ssh_keepalive_interval": 0,
        "ssh_tcp_keepalive": True,
    }
    app.host_key_prompter = object()

    monkeypatch.setattr("bifrost_app.credentials.is_available", lambda: False)
    monkeypatch.setattr("bifrost_app.credentials.provider_label", lambda: "system keyring")
    monkeypatch.setattr("bifrost_app.credentials.get_passphrase", lambda _path: "")
    monkeypatch.setattr(
        "bifrost_app.QFileDialog.getOpenFileName",
        lambda *args, **kwargs: ("/home/user/.ssh/id_ed25519", ""),
    )

    session = {"name": "prod", "type": "SSH", "host": "h", "user": "u", "auth": "key"}
    backend = BifrostApp._build_ssh_backend(app, "prod", session)

    assert backend is not None
    assert backend.creds.key_filename == "/home/user/.ssh/id_ed25519"
    assert session["key_path"] == "/home/user/.ssh/id_ed25519"


def test_build_ssh_backend_cancels_missing_key(qapp, monkeypatch):
    from bifrost_app import BifrostApp

    app = BifrostApp.__new__(BifrostApp)
    app.settings = {
        "ssh_startup_command": "",
        "credential_save_policy": "never",
        "ssh_connect_timeout": 15,
        "ssh_agent_forwarding": False,
        "known_hosts_file": "",
        "ssh_keepalive_interval": 0,
        "ssh_tcp_keepalive": True,
    }
    app.host_key_prompter = object()

    warnings = []
    monkeypatch.setattr("bifrost_app.credentials.is_available", lambda: False)
    monkeypatch.setattr("bifrost_app.credentials.provider_label", lambda: "system keyring")
    monkeypatch.setattr("bifrost_app.QFileDialog.getOpenFileName", lambda *args, **kwargs: ("", ""))
    monkeypatch.setattr("bifrost_app.QMessageBox.warning", lambda *args, **kwargs: warnings.append(args))

    session = {"name": "prod", "type": "SSH", "host": "h", "user": "u", "auth": "key"}

    assert BifrostApp._build_ssh_backend(app, "prod", session) is None
    assert warnings

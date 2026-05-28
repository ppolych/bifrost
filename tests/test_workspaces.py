def test_workspace_manager_saves_sanitized_profiles(tmp_path, monkeypatch):
    import core.workspaces as workspaces

    monkeypatch.setattr(workspaces, "config_path", lambda name: str(tmp_path / name))

    manager = workspaces.WorkspaceManager()
    manager.upsert(
        "Prod",
        [
            {
                "name": "prod-db",
                "type": "SSH",
                "host": "db.internal",
                "user": "admin",
                "password": "secret",
                "passphrase": "also-secret",
                "tunnels": ["L 127.0.0.1:15432 db.internal:5432"],
            }
        ],
    )

    assert manager.names() == ["Prod"]
    saved = manager.get("Prod")
    assert saved[0]["host"] == "db.internal"
    assert saved[0]["tunnels"] == ["L 127.0.0.1:15432 db.internal:5432"]
    assert "password" not in saved[0]
    assert "passphrase" not in saved[0]

    saved[0]["host"] = "changed"
    assert manager.get("Prod")[0]["host"] == "db.internal"


def test_workspace_manager_rejects_empty_profile(tmp_path, monkeypatch):
    import pytest

    import core.workspaces as workspaces

    monkeypatch.setattr(workspaces, "config_path", lambda name: str(tmp_path / name))

    manager = workspaces.WorkspaceManager()
    with pytest.raises(ValueError):
        manager.upsert("Empty", [])

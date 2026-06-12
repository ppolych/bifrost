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
    profile = manager.get_profile("Prod")
    assert profile["version"] == workspaces.WORKSPACE_SCHEMA_VERSION
    assert profile["sessions"][0]["host"] == "db.internal"


def test_workspace_manager_rejects_empty_profile(tmp_path, monkeypatch):
    import pytest

    import core.workspaces as workspaces

    monkeypatch.setattr(workspaces, "config_path", lambda name: str(tmp_path / name))

    manager = workspaces.WorkspaceManager()
    with pytest.raises(ValueError):
        manager.upsert("Empty", [])


def test_workspace_manager_round_trips_layout(tmp_path, monkeypatch):
    import core.workspaces as workspaces

    monkeypatch.setattr(workspaces, "config_path", lambda name: str(tmp_path / name))

    manager = workspaces.WorkspaceManager()
    manager.upsert(
        "Ops",
        [{"name": "ops", "type": "SSH", "host": "ops.internal"}],
        layout={
            "main_splitter_sizes": ["300", 900],
            "sidebar_splitter_sizes": [500, 250],
            "last_sidebar_tab": "2",
            "active_tab": 3,
            "ignored": "value",
        },
    )

    profile = manager.get_profile("Ops")
    assert profile["layout"] == {
        "main_splitter_sizes": [300, 900],
        "sidebar_splitter_sizes": [500, 250],
        "last_sidebar_tab": 2,
        "active_tab": 3,
    }
    profile["layout"]["active_tab"] = 99
    assert manager.get_profile("Ops")["layout"]["active_tab"] == 3


def test_workspace_manager_reads_legacy_list_profiles(tmp_path, monkeypatch):
    import core.workspaces as workspaces

    monkeypatch.setattr(workspaces, "config_path", lambda name: str(tmp_path / name))

    manager = workspaces.WorkspaceManager()
    manager.profiles["Legacy"] = [
        {"name": "legacy", "type": "SSH", "host": "legacy.internal"}
    ]

    assert manager.get("Legacy")[0]["host"] == "legacy.internal"
    assert manager.get_profile("Legacy")["layout"] == {}

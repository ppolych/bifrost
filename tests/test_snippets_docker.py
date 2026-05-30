def test_snippet_manager_update_moves_snippet(tmp_path, monkeypatch):
    import core.snippets as snippets

    monkeypatch.setattr(snippets, "config_path", lambda name: str(tmp_path / name))

    manager = snippets.SnippetManager()
    manager.add_snippet("System", "Whoami", "whoami")
    assert manager.update_snippet("System", "Whoami", "SSH", "Uptime", "uptime")

    assert manager.get_snippet("System", "Whoami") is None
    assert manager.get_snippet("SSH", "Uptime") == "uptime"


def test_docker_action_rejects_unknown_action():
    import pytest

    from core.docker_utils import container_action

    with pytest.raises(ValueError):
        container_action("container", "remove")

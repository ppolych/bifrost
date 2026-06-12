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


def test_parse_containers_output():
    from core.docker_utils import parse_containers

    containers = parse_containers("abc|web|nginx:latest|Up 2 hours\n")

    assert containers == [{
        "id": "abc",
        "name": "web",
        "image": "nginx:latest",
        "status": "Up 2 hours",
    }]


def test_local_container_listing_reports_cli_errors(monkeypatch):
    import subprocess

    import core.docker_utils as docker_utils

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0], stderr="daemon unavailable")

    monkeypatch.setattr(docker_utils.subprocess, "check_output", fail)

    containers, error = docker_utils.list_containers_with_error()

    assert containers == []
    assert error == "daemon unavailable"


def test_remote_container_listing_uses_backend_exec():
    from core.docker_utils import list_remote_containers

    class Backend:
        def __init__(self):
            self.commands = []

        def exec_command_text(self, command, timeout=10):
            self.commands.append((command, timeout))
            return 0, "abc|web|nginx|Up\n", ""

    backend = Backend()
    containers, error = list_remote_containers(backend)

    assert error == ""
    assert containers[0]["name"] == "web"
    assert "docker ps -a" in backend.commands[0][0]


def test_remote_container_listing_reports_disconnect():
    import paramiko

    from core.docker_utils import list_remote_containers

    class Backend:
        def exec_command_text(self, command, timeout=10):
            raise paramiko.SSHException("SSH session is not connected")

    containers, error = list_remote_containers(Backend())

    assert containers == []
    assert error == "SSH session is not connected"


def test_remote_container_action_uses_backend_exec():
    from core.docker_utils import container_action

    class Backend:
        def __init__(self):
            self.command = ""

        def exec_command_text(self, command, timeout=10):
            self.command = command
            return 0, "", ""

    backend = Backend()
    ok, error = container_action("web", "restart", backend=backend)

    assert ok is True
    assert error == ""
    assert backend.command == "docker restart web"


def test_remote_container_action_reports_disconnect():
    from core.docker_utils import container_action

    class Backend:
        def exec_command_text(self, command, timeout=10):
            raise EOFError()

    ok, error = container_action("web", "restart", backend=Backend())

    assert ok is False
    assert error == "EOFError"


def test_docker_shell_signal_preserves_remote_session_dict(qapp):
    from widgets.docker_dashboard import DockerDashboard

    class Creds:
        host = "remote.example"

    class Backend:
        status = "connected"
        creds = Creds()

        def exec_command_text(self, command, timeout=10):
            return 0, "abc|web|nginx|Up\n", ""

    widget = DockerDashboard()
    widget.set_ssh_context(Backend(), {"host": "remote.example", "user": "root", "type": "SSH"})
    received = []
    widget.container_shell_requested.connect(lambda name, payload: received.append((name, payload)))

    widget._open_shell("web")

    assert received[0][0] == "Docker: web"
    assert isinstance(received[0][1], dict)
    assert received[0][1]["host"] == "remote.example"
    assert received[0][1]["command"].startswith("docker exec -it web")

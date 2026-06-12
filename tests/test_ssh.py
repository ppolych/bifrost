"""Tests for SSH backend pieces that don't need a real server."""

import os

import pytest


def test_credentials_from_session_minimal():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session({"host": "h", "user": "u", "port": "2222"})
    assert creds.host == "h"
    assert creds.username == "u"
    assert creds.port == 2222
    assert creds.auth == "agent"  # default


def test_credentials_from_session_with_key():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session(
        {
            "host": "h",
            "user": "u",
            "port": 22,
            "auth": "key",
            "key_path": "~/.ssh/id_ed25519",
            "certificate_path": "~/.ssh/id_ed25519-cert.pub",
            "command": "uptime",
        }
    )
    assert creds.auth == "key"
    assert creds.key_filename == "~/.ssh/id_ed25519"
    assert creds.certificate_filename == "~/.ssh/id_ed25519-cert.pub"
    assert creds.startup_command == "uptime"


def test_credentials_from_session_with_advanced_ssh_fields():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session({
        "host": "h",
        "user": "u",
        "connect_timeout": 45,
        "agent_forwarding": True,
        "keepalive_interval": 60,
        "tcp_keepalive": True,
        "known_hosts_file": "~/.ssh/custom_known_hosts",
        "tunnels": ["L 127.0.0.1:5432 db:5432"],
        "proxy_jump": "jump.example.com",
        "proxy_command": "ssh -W %h:%p jump.example.com",
    })

    assert creds.connect_timeout == 45
    assert creds.agent_forwarding is True
    assert creds.keepalive_interval == 60
    assert creds.tcp_keepalive is True
    assert creds.known_hosts_file == "~/.ssh/custom_known_hosts"
    assert creds.tunnels == ["L 127.0.0.1:5432 db:5432"]
    assert creds.proxy_jump == "jump.example.com"
    assert creds.proxy_command == "ssh -W %h:%p jump.example.com"


def test_parse_proxy_jump():
    from core.ssh_backend import ParamikoBackend

    assert ParamikoBackend._parse_proxy_jump("bastion") == ("", "bastion", 22)
    assert ParamikoBackend._parse_proxy_jump("ops@bastion:2222") == ("ops", "bastion", 2222)
    assert ParamikoBackend._parse_proxy_jump("bastion:nope") is None


def test_proxy_command_substitutes_host_and_port(monkeypatch):
    from core import ssh_backend
    from core.ssh_backend import ParamikoBackend, SshCredentials

    commands = []

    class FakeProxy:
        def __init__(self, command):
            commands.append(command)

    monkeypatch.setattr(ssh_backend.paramiko.proxy, "ProxyCommand", FakeProxy)
    backend = ParamikoBackend(
        SshCredentials(host="target.example.com", port=2222, proxy_command="ssh -W %h:%p jump")
    )

    assert isinstance(backend._proxy_socket(), FakeProxy)
    assert commands == ["ssh -W target.example.com:2222 jump"]


def test_load_private_key_with_explicit_certificate(monkeypatch):
    from core import ssh_backend
    from core.ssh_backend import ParamikoBackend, SshCredentials

    calls = []

    class FakeKey:
        @classmethod
        def from_private_key_file(cls, path, password=None):
            calls.append(("load", path, password))
            return cls()

        def load_certificate(self, path):
            calls.append(("cert", path))

    class RejectKey:
        @classmethod
        def from_private_key_file(cls, path, password=None):
            raise ssh_backend.paramiko.SSHException("wrong kind")

    monkeypatch.setattr(ssh_backend.paramiko, "RSAKey", RejectKey)
    monkeypatch.setattr(ssh_backend.paramiko, "ECDSAKey", FakeKey)

    backend = ParamikoBackend(SshCredentials(
        host="h",
        username="u",
        key_filename="~/.ssh/id",
        certificate_filename="~/.ssh/custom-cert.pub",
        passphrase="secret",
    ))

    assert isinstance(backend._load_private_key_with_certificate(), FakeKey)
    assert calls == [
        ("load", os.path.expanduser("~/.ssh/id"), "secret"),
        ("cert", os.path.expanduser("~/.ssh/custom-cert.pub")),
    ]


def test_parse_local_remote_and_dynamic_tunnels():
    from core.ssh_backend import parse_tunnel_spec

    local = parse_tunnel_spec("L 127.0.0.1:15432 db.internal:5432")
    assert local.kind == "L"
    assert local.bind_host == "127.0.0.1"
    assert local.bind_port == 15432
    assert local.target_host == "db.internal"
    assert local.target_port == 5432

    remote = parse_tunnel_spec("R 0.0.0.0:8080 127.0.0.1:80")
    assert remote.kind == "R"
    assert remote.bind_host == "0.0.0.0"
    assert remote.target_host == "127.0.0.1"

    dynamic = parse_tunnel_spec("D 1080")
    assert dynamic.kind == "D"
    assert dynamic.bind_host == "127.0.0.1"
    assert dynamic.bind_port == 1080


def test_parse_tunnel_rejects_bad_shape():
    from core.ssh_backend import parse_tunnel_spec

    with pytest.raises(ValueError):
        parse_tunnel_spec("L 127.0.0.1:15432")
    with pytest.raises(ValueError):
        parse_tunnel_spec("X 127.0.0.1:15432 db:5432")


def test_credentials_port_coercion_handles_empty():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session({"host": "h", "port": ""})
    assert creds.port == 22


def test_credentials_from_session_defaults_invalid_numeric_fields():
    from core.ssh_backend import SshCredentials

    creds = SshCredentials.from_session({
        "host": "h",
        "port": "not-a-port",
        "connect_timeout": "slow",
        "keepalive_interval": "often",
        "tunnels": "L 127.0.0.1:1 h:1",
    })

    assert creds.port == 22
    assert creds.connect_timeout == 15.0
    assert creds.keepalive_interval == 0
    assert creds.tunnels == []


def test_credentials_from_session_rejects_out_of_range_port():
    from core.ssh_backend import SshCredentials

    assert SshCredentials.from_session({"host": "h", "port": 0}).port == 22
    assert SshCredentials.from_session({"host": "h", "port": 70000}).port == 22


def test_backend_emits_connecting_hint_before_ready():
    """Until the connect thread sets _ready, read() returns a 'Connecting…' hint
    rather than blocking the GUI thread indefinitely."""
    from core.ssh_backend import ParamikoBackend, SshCredentials

    backend = ParamikoBackend(SshCredentials(host="example.invalid", username="u"))
    # Don't call start() — _ready stays unset.
    out = backend.read()
    assert out.startswith(b"Connecting to u@example.invalid")


def test_backend_emits_error_once():
    from core.ssh_backend import ParamikoBackend, SshCredentials

    backend = ParamikoBackend(SshCredentials(host="h", username="u"))
    backend._connect_error = RuntimeError("nope")
    backend._ready.set()
    first = backend.read()
    assert b"connection failed" in first
    # Second read should not repeat the error
    second = backend.read()
    assert second == b""


def test_backend_status_classifies_connection_states():
    import paramiko

    from core.ssh_backend import ParamikoBackend, SshCredentials

    backend = ParamikoBackend(SshCredentials(host="h", username="u"))
    assert backend.status == "connecting"

    backend._connect_error = paramiko.AuthenticationException("bad password")
    backend._ready.set()
    assert backend.status == "auth failed"
    assert backend.reconnectable

    backend._connect_error = None
    backend._closed = True
    assert backend.status == "closed"


def test_backend_status_detects_host_key_failures():
    from core.ssh_backend import ParamikoBackend, SshCredentials

    backend = ParamikoBackend(SshCredentials(host="h", username="u"))
    backend._connect_error = RuntimeError("Host key for h rejected by user")
    backend._ready.set()
    assert backend.status == "host-key failed"


def test_tunnel_status_and_stop(monkeypatch):
    from core.ssh_backend import LocalPortForwarder, ParamikoBackend, SshCredentials

    started = []

    def fake_start(self):
        started.append(self.spec.label)

        class Listener:
            def close(self):
                pass

        self._listener = Listener()

    monkeypatch.setattr(LocalPortForwarder, "start", fake_start)
    backend = ParamikoBackend(SshCredentials(
        host="h",
        username="u",
        tunnels=["L 127.0.0.1:15432 db:5432"],
    ))

    class FakeClient:
        def get_transport(self):
            return object()

    backend._start_tunnels(FakeClient())

    assert started == ["L 127.0.0.1:15432 db:5432"]
    assert backend.tunnel_count == 1
    assert backend.tunnel_statuses()[0]["active"] is True
    assert backend.stop_tunnel(0) is True
    assert backend.tunnel_statuses()[0]["active"] is False
    assert backend.stop_tunnel(99) is False


def test_session_manager_find_by_name(qapp, tmp_path, monkeypatch):
    import core.persistence as persistence

    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))

    sm = persistence.SessionManager()
    sm.add_session("User sessions", {"name": "prod-1", "type": "SSH", "host": "1.1.1.1"})
    sm.add_session("Work Folders/Production", {"name": "prod-2", "type": "SSH", "host": "2.2.2.2"})

    assert sm.find_by_name("prod-1")["host"] == "1.1.1.1"
    assert sm.find_by_name("prod-2")["host"] == "2.2.2.2"
    assert sm.find_by_name("missing") is None

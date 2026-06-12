from core.ssh_config_import import ROOT_GROUP, parse_ssh_config


def test_parse_ssh_config_imports_concrete_hosts():
    result = parse_ssh_config(
        """
        Host *
          User default-user

        Host prod
          HostName prod.example.com
          User deploy
          Port 2222
          IdentityFile ~/.ssh/prod
          CertificateFile ~/.ssh/prod-cert.pub
          ForwardAgent yes
          ProxyJump bastion
          LocalForward 127.0.0.1:15432 db.internal:5432

        Host web-1 web-2
          HostName %h.example.com
          ProxyCommand ssh -W %h:%p bastion
        """
    )

    sessions = result.tree[ROOT_GROUP]

    assert result.imported == 3
    assert result.skipped == 1
    assert sessions[0] == {
        "name": "prod",
        "type": "SSH",
        "host": "prod.example.com",
        "port": "2222",
        "auth": "key",
        "overrides": {"font": None, "scheme": "Default"},
        "user": "deploy",
        "key_path": "~/.ssh/prod",
        "certificate_path": "~/.ssh/prod-cert.pub",
        "agent_forwarding": True,
        "proxy_jump": "bastion",
        "tunnels": ["L 127.0.0.1:15432 db.internal:5432"],
    }
    assert sessions[1]["name"] == "web-1"
    assert sessions[1]["host"] == "%h.example.com"
    assert sessions[1]["proxy_command"] == "ssh -W %h:%p bastion"
    assert sessions[2]["name"] == "web-2"


def test_parse_ssh_config_ignores_negated_and_wildcard_hosts():
    result = parse_ssh_config(
        """
        Host !blocked *.example.com
          User ignored
        """
    )

    assert result.imported == 0
    assert result.skipped == 2
    assert result.tree[ROOT_GROUP] == []

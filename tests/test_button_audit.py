"""Audit tests for buttons that were demos until the audit:
- Sidebar Export/Import (round-trip through SessionManager).
- Pin/unpin tab uses the correct Qt enum (QTabBar.ButtonPosition).
- Tools: IP calculator math, key generation file shape.
- Active-sessions browser populates from open SSH backends.
"""

from __future__ import annotations

import os

import pytest


# ---------------------------------------------------------------------------
# IP calculator
# ---------------------------------------------------------------------------


def test_ip_tools_basic_v4():
    from core.ip_tools import calculate

    info = calculate("10.0.0.0/24")
    assert info["Network"] == "10.0.0.0"
    assert info["Broadcast"] == "10.0.0.255"
    assert info["Netmask"] == "255.255.255.0"
    assert info["Prefix"] == "/24"
    assert info["Total hosts"] == "256"
    assert info["Usable hosts"] == "254"
    assert info["First host"] == "10.0.0.1"
    assert info["Last host"] == "10.0.0.254"
    assert info["Version"] == "IPv4"


def test_ip_tools_host_address_falls_through_to_slash32():
    from core.ip_tools import calculate

    info = calculate("192.168.1.5")
    assert info["Network"] == "192.168.1.5"
    assert info["Prefix"] == "/32"


def test_ip_tools_v6():
    from core.ip_tools import calculate

    info = calculate("2001:db8::/64")
    assert info["Network"] == "2001:db8::"
    assert info["Version"] == "IPv6"
    assert info["Broadcast"] == "—"


def test_ip_tools_rejects_garbage():
    from core.ip_tools import calculate

    with pytest.raises(ValueError):
        calculate("not-an-ip")


def test_port_scan_uses_platform_address_resolution(monkeypatch):
    import core.network_tools as nt

    attempts = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    def fake_create_connection(address, timeout):
        attempts.append((address, timeout))
        host, port = address
        if host == "localhost" and port == 2:
            return Conn()
        raise OSError("closed")

    monkeypatch.setattr(nt.socket, "create_connection", fake_create_connection)

    assert nt.scan_ports("localhost", 1, 3) == [2]
    assert attempts[0] == (("localhost", 1), 0.05)


# ---------------------------------------------------------------------------
# Key generation
# ---------------------------------------------------------------------------


def test_keygen_produces_private_and_public(tmp_path):
    from core.keygen import generate_keypair

    out = tmp_path / "id_test"
    priv, pub = generate_keypair(str(out), algorithm="ed25519")
    assert os.path.exists(priv)
    assert os.path.exists(pub)
    with open(pub) as f:
        line = f.read()
    assert line.startswith("ssh-ed25519 ")
    assert "bifrost-generated" in line
    # Private key permission tightening (best-effort).
    mode = os.stat(priv).st_mode & 0o777
    assert mode == 0o600


def test_keygen_refuses_overwrite(tmp_path):
    from core.keygen import generate_keypair

    out = tmp_path / "id_test"
    generate_keypair(str(out))
    with pytest.raises(FileExistsError):
        generate_keypair(str(out))


# ---------------------------------------------------------------------------
# Tab pin uses the right enum
# ---------------------------------------------------------------------------


def test_qtabbar_button_position_is_what_we_use():
    """If Qt ever renamed the enum, this test catches it before runtime."""
    from PyQt6.QtWidgets import QTabBar

    # The enum value we use in pin/unpin must exist.
    assert hasattr(QTabBar, "ButtonPosition")
    assert hasattr(QTabBar.ButtonPosition, "RightSide")


# ---------------------------------------------------------------------------
# Session import/export
# ---------------------------------------------------------------------------


def test_session_export_import_round_trip(qapp, tmp_path, monkeypatch):
    import core.persistence as persistence

    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))

    src = persistence.SessionManager()
    src.add_session("User sessions", {"name": "host-A", "type": "SSH", "host": "1.1.1.1"})
    export_path = tmp_path / "exported.json"
    src.export_sessions(str(export_path))

    # Use a different config_path target for the importing manager so we
    # exercise a "fresh install" path.
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    monkeypatch.setattr(persistence, "config_path", lambda name: str(other_dir / name))
    dst = persistence.SessionManager()
    assert dst.find_by_name("host-A") is None
    dst.import_sessions(str(export_path))
    assert dst.find_by_name("host-A")["host"] == "1.1.1.1"


def test_local_http_server_binds_loopback_and_reuses_port():
    from widgets.local_servers import LocalTcpServer

    server = LocalTcpServer(("127.0.0.1", 0), object)
    try:
        assert server.server_address[0] == "127.0.0.1"
        assert LocalTcpServer.allow_reuse_address is True
    finally:
        server.server_close()


# ---------------------------------------------------------------------------
# Active SSH browser
# ---------------------------------------------------------------------------


def test_ssh_browser_shows_placeholder_when_empty(qapp):
    from widgets.ssh_browser import SshBrowser

    b = SshBrowser()
    assert b.tree.topLevelItemCount() == 1  # placeholder row
    placeholder = b.tree.topLevelItem(0)
    assert placeholder.isDisabled()


def test_ssh_browser_populates_from_connections(qapp):
    from widgets.ssh_browser import ActiveConnection, SshBrowser

    b = SshBrowser()
    b.update_from_tabs([
        ActiveConnection(tab_index=2, host="prod.example.com",
                         user="root", port=22, status="connected"),
        ActiveConnection(tab_index=5, host="db.example.com",
                         user="dba", port=2222, status="connecting"),
    ])
    assert b.tree.topLevelItemCount() == 2
    item0 = b.tree.topLevelItem(0)
    assert item0.text(0) == "prod.example.com"
    assert item0.text(3) == "connected"


def test_ssh_browser_emits_focus_on_double_click(qapp):
    from widgets.ssh_browser import ActiveConnection, SshBrowser

    b = SshBrowser()
    b.update_from_tabs([
        ActiveConnection(tab_index=7, host="h", user="u", port=22, status="connected"),
    ])
    received: list[int] = []
    b.focus_tab.connect(received.append)
    b._on_double_click(b.tree.topLevelItem(0), 0)
    assert received == [7]


def test_ssh_browser_emits_reconnect_for_selection(qapp):
    from widgets.ssh_browser import ActiveConnection, SshBrowser

    b = SshBrowser()
    b.update_from_tabs([
        ActiveConnection(tab_index=4, host="h", user="u", port=22, status="closed"),
    ])
    received: list[int] = []
    b.reconnect_tab.connect(received.append)
    b.tree.setCurrentItem(b.tree.topLevelItem(0))
    b._reconnect_selected()
    assert received == [4]


def test_ssh_browser_emits_reconnect_all(qapp):
    from widgets.ssh_browser import SshBrowser

    b = SshBrowser()
    received: list[bool] = []
    b.reconnect_all.connect(lambda: received.append(True))
    b.reconnect_all_btn.click()
    assert received == [True]


def test_ssh_browser_shows_tunnel_count(qapp):
    from widgets.ssh_browser import ActiveConnection, SshBrowser

    b = SshBrowser()
    b.update_from_tabs([
        ActiveConnection(
            tab_index=1,
            host="h",
            user="u",
            port=22,
            status="connected",
            tunnels=[
                {"index": 0, "label": "L 127.0.0.1:15432 db:5432", "active": True},
                {
                    "index": 1,
                    "label": "D 127.0.0.1:1080",
                    "endpoint": "127.0.0.1:1080",
                    "target": "SOCKS proxy",
                    "active": False,
                },
            ],
        ),
    ])

    item = b.tree.topLevelItem(0)
    assert item.text(4) == "1/2"
    assert "SOCKS proxy" in item.toolTip(4)

"""Audit tests for buttons that were demos until the audit:
- Sidebar Export/Import (round-trip through SessionManager).
- Pin/unpin tab uses the correct Qt enum (QTabBar.ButtonPosition).
- Tools: IP calculator math, key generation file shape.
- Active-sessions browser populates from open SSH backends.
- Credentials view reflects keyring slots.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock

import keyring
import keyring.backend
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
                {"index": 1, "label": "D 127.0.0.1:1080", "active": False},
            ],
        ),
    ])

    item = b.tree.topLevelItem(0)
    assert item.text(4) == "1"
    assert "15432" in item.toolTip(4)


# ---------------------------------------------------------------------------
# CredentialManager
# ---------------------------------------------------------------------------


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 999

    def __init__(self):
        super().__init__()
        self.store: dict[tuple[str, str], str] = {}

    def get_password(self, service, username):
        return self.store.get((service, username))

    def set_password(self, service, username, password):
        self.store[(service, username)] = password

    def delete_password(self, service, username):
        if (service, username) in self.store:
            del self.store[(service, username)]


@pytest.fixture
def mem_keyring():
    backend = _MemKeyring()
    prev = keyring.get_keyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(prev)


def test_credential_manager_lists_only_sessions_with_keyring_entries(qapp, mem_keyring):
    from core import credentials
    from widgets.credential_manager import CredentialManager

    # Two SSH sessions; only one has a stored password.
    s1 = {"type": "SSH", "name": "a@h", "host": "h", "user": "a", "port": 22}
    s2 = {"type": "SSH", "name": "b@h", "host": "h", "user": "b", "port": 22}
    credentials.set_password(s1["user"], s1["host"], s1["port"], "secret")

    mgr = CredentialManager()
    mgr.set_sessions([s1, s2])

    assert mgr.tree.topLevelItemCount() == 2
    assert mgr.tree.topLevelItem(0).text(1) == "a@h:22"
    assert mgr.tree.topLevelItem(0).text(2) == "Password"
    assert mgr.tree.topLevelItem(0).text(3) == "Saved"
    assert mgr.tree.topLevelItem(1).text(1) == "b@h:22"
    assert mgr.tree.topLevelItem(1).text(3) == "Missing"


def test_credential_manager_placeholder_when_nothing_saved(qapp, mem_keyring):
    from widgets.credential_manager import CredentialManager

    mgr = CredentialManager()
    mgr.set_sessions([
        {"type": "SSH", "name": "a@h", "host": "h", "user": "a", "port": 22},
    ])
    assert mgr.tree.topLevelItemCount() == 1
    assert not mgr.tree.topLevelItem(0).isDisabled()
    assert mgr.tree.topLevelItem(0).text(3) == "Missing"


def test_credential_manager_shows_passphrase_account(qapp, mem_keyring):
    from core import credentials
    from widgets.credential_manager import CredentialManager

    session = {
        "type": "SSH",
        "name": "keyed",
        "host": "h",
        "user": "a",
        "port": 22,
        "key_path": "/home/u/.ssh/id_ed25519",
    }
    credentials.set_passphrase(session["key_path"], "secret")

    mgr = CredentialManager()
    mgr.set_sessions([session])

    assert mgr.tree.topLevelItemCount() == 2
    assert mgr.tree.topLevelItem(1).text(1) == "/home/u/.ssh/id_ed25519"
    assert mgr.tree.topLevelItem(1).text(2) == "Passphrase"
    assert mgr.tree.topLevelItem(1).text(3) == "Saved"

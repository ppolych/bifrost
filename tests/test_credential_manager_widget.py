import keyring
import keyring.backend
import pytest


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

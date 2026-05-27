"""Keyring credential storage tests.

Uses keyring's built-in `keyrings.alt.file.EncryptedKeyring`-like setup is
overkill; we instead install a tiny in-memory backend directly with
`keyring.set_keyring`. That way the tests never touch the host keyring and
each test starts from a clean slate.
"""

from __future__ import annotations

import keyring
import keyring.backend
import pytest


class _MemKeyring(keyring.backend.KeyringBackend):
    priority = 999  # arbitrary positive number — keyring needs > 0 to use it

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
        else:
            raise keyring.errors.PasswordDeleteError("not found")


@pytest.fixture
def mem_keyring(monkeypatch):
    backend = _MemKeyring()
    prev = keyring.get_keyring()
    keyring.set_keyring(backend)
    yield backend
    keyring.set_keyring(prev)


def test_is_available_with_working_backend(mem_keyring):
    from core import credentials
    assert credentials.is_available() is True


def test_password_round_trip(mem_keyring):
    from core import credentials

    assert credentials.get_password("alice", "host", 22) is None
    assert credentials.set_password("alice", "host", 22, "s3cret") is True
    assert credentials.get_password("alice", "host", 22) == "s3cret"
    assert credentials.forget_password("alice", "host", 22) is True
    assert credentials.get_password("alice", "host", 22) is None


def test_passphrase_round_trip(mem_keyring):
    from core import credentials

    assert credentials.set_passphrase("/home/u/.ssh/id_ed25519", "phr@s3") is True
    assert credentials.get_passphrase("/home/u/.ssh/id_ed25519") == "phr@s3"
    assert credentials.forget_passphrase("/home/u/.ssh/id_ed25519") is True


def test_set_password_refuses_empty(mem_keyring):
    from core import credentials
    assert credentials.set_password("a", "h", 22, "") is False


def test_password_port_independence(mem_keyring):
    from core import credentials

    credentials.set_password("a", "h", 22, "p22")
    credentials.set_password("a", "h", 2222, "p2222")
    assert credentials.get_password("a", "h", 22) == "p22"
    assert credentials.get_password("a", "h", 2222) == "p2222"


def test_is_available_false_when_fail_backend(monkeypatch):
    """The 'fail' backend silently drops writes — is_available must reject it
    so we don't pretend to save passwords that get lost."""
    from keyring.backends import fail as fail_backend

    prev = keyring.get_keyring()
    keyring.set_keyring(fail_backend.Keyring())
    try:
        from core import credentials
        assert credentials.is_available() is False
        # And set_password should refuse rather than throw or pretend to save.
        assert credentials.set_password("a", "h", 22, "p") is False
    finally:
        keyring.set_keyring(prev)


def test_credential_prompt_returns_text_and_remember(qapp, monkeypatch):
    """Prompt the dialog without actually showing UI; verify the data shape."""
    from PyQt6.QtWidgets import QDialog
    from widgets.credential_prompt import CredentialPrompt

    dlg = CredentialPrompt("T", "P", remember_enabled=True)
    dlg._input.setText("password!")
    dlg._remember.setChecked(True)

    # Bypass exec() — directly accept.
    dlg.accept()
    assert dlg.value() == "password!"
    assert dlg.remember() is True


def test_credential_prompt_disables_remember_without_keyring(qapp):
    from widgets.credential_prompt import CredentialPrompt

    dlg = CredentialPrompt("T", "P", remember_enabled=False)
    dlg._input.setText("x")
    dlg._remember.setChecked(True)  # user can't actually check it; widget is disabled
    # Even if forced, remember() returns False when the checkbox is disabled.
    assert dlg.remember() is False

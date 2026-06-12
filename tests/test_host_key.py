"""Host-key policy tests — no real SSH server, no GUI dialog."""

from unittest.mock import MagicMock

import paramiko
import pytest


class _StubPrompter:
    def __init__(self, accept: bool):
        self.accept = accept
        self.calls = []

    def prompt(self, hostname, key):
        self.calls.append((hostname, key))
        return self.accept


def _make_fake_key():
    key = MagicMock(spec=paramiko.PKey)
    key.get_name.return_value = "ssh-ed25519"
    key.get_fingerprint.return_value = b"\x01\x02\x03\x04"
    return key


def test_policy_raises_when_user_rejects(tmp_path):
    from core.host_key_prompt import QtHostKeyPolicy

    policy = QtHostKeyPolicy(_StubPrompter(accept=False), save_path=str(tmp_path / "known_hosts"))
    client = MagicMock()
    with pytest.raises(paramiko.SSHException):
        policy.missing_host_key(client, "example.com", _make_fake_key())
    client.save_host_keys.assert_not_called()


def test_policy_persists_when_user_accepts(tmp_path):
    from core.host_key_prompt import QtHostKeyPolicy

    save_path = tmp_path / "known_hosts"
    policy = QtHostKeyPolicy(_StubPrompter(accept=True), save_path=str(save_path))
    client = MagicMock()
    host_keys = MagicMock()
    client.get_host_keys.return_value = host_keys

    policy.missing_host_key(client, "example.com", _make_fake_key())

    host_keys.add.assert_called_once()
    client.save_host_keys.assert_called_once_with(str(save_path))


def test_policy_persists_to_bare_filename(monkeypatch):
    from core import host_key_prompt
    from core.host_key_prompt import QtHostKeyPolicy

    makedirs = MagicMock()
    monkeypatch.setattr(host_key_prompt.os, "makedirs", makedirs)
    policy = QtHostKeyPolicy(_StubPrompter(accept=True), save_path="known_hosts")
    client = MagicMock()
    host_keys = MagicMock()
    client.get_host_keys.return_value = host_keys

    policy.missing_host_key(client, "example.com", _make_fake_key())

    makedirs.assert_not_called()
    client.save_host_keys.assert_called_once_with("known_hosts")


def test_prompter_runs_dialog_on_gui_thread(qapp, monkeypatch):
    """The prompt is thread-safe: a worker thread calling .prompt() should not
    spin forever. We force the dialog to resolve immediately via monkeypatch."""
    import threading

    from PyQt6.QtWidgets import QMessageBox

    from core.host_key_prompt import HostKeyPrompter

    # Force QMessageBox.exec to return Yes without actually showing UI.
    monkeypatch.setattr(QMessageBox, "exec", lambda self: QMessageBox.StandardButton.Yes)

    prompter = HostKeyPrompter()
    result_box = {}

    def worker():
        result_box["accepted"] = prompter.prompt("example.com", _make_fake_key())

    t = threading.Thread(target=worker, daemon=True)
    t.start()
    # Process Qt events so the queued signal is delivered. We loop briefly to
    # let the worker post into the GUI thread and read back.
    import time
    for _ in range(50):
        qapp.processEvents()
        if not t.is_alive():
            break
        time.sleep(0.01)
    t.join(timeout=1.0)
    assert not t.is_alive()
    assert result_box["accepted"] is True

"""Cross-thread host-key prompt for paramiko.

`HostKeyPrompter` lives in the GUI thread; `QtHostKeyPolicy` is what paramiko
calls from its connect worker thread. The policy emits a queued signal into
the prompter, then blocks on a `threading.Event` until the user accepts or
rejects in the QDialog.

On accept, the new key is added to `~/.ssh/known_hosts` via paramiko's
`save_host_keys` — we explicitly `load_host_keys` from the same path in
`ParamikoBackend._connect` so save doesn't wipe existing entries.
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import paramiko
from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import QMessageBox

log = logging.getLogger(__name__)


def known_hosts_path() -> str:
    return os.path.expanduser("~/.ssh/known_hosts")


def _format_fingerprint(key: paramiko.PKey) -> str:
    fp = key.get_fingerprint().hex()
    return ":".join(fp[i : i + 2] for i in range(0, len(fp), 2))


class HostKeyPrompter(QObject):
    """GUI-thread host-key prompter. Construct with a Qt parent."""

    _request = pyqtSignal(str, object, object)  # hostname, key, decision-holder dict

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        # Queued connection: ensures the slot runs in the prompter's thread
        # (the GUI thread) even if `request` is emitted from a worker thread.
        self._request.connect(self._show_dialog, Qt.ConnectionType.QueuedConnection)

    def prompt(self, hostname: str, key: paramiko.PKey) -> bool:
        holder = {"event": threading.Event(), "result": False}
        self._request.emit(hostname, key, holder)
        holder["event"].wait()
        return holder["result"]

    def _show_dialog(self, hostname: str, key, holder: dict):
        # Runs on GUI thread.
        try:
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Unknown host key")
            msg.setText(f"The server <b>{hostname}</b> presented an unknown host key.")
            msg.setInformativeText(
                f"<b>Key type:</b> {key.get_name()}<br>"
                f"<b>Fingerprint:</b> {_format_fingerprint(key)}<br><br>"
                "If you trust this host, the key will be added to ~/.ssh/known_hosts."
            )
            msg.setStandardButtons(
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            holder["result"] = msg.exec() == QMessageBox.StandardButton.Yes
        finally:
            holder["event"].set()


class QtHostKeyPolicy(paramiko.MissingHostKeyPolicy):
    """Defers the trust decision to a `HostKeyPrompter` (GUI thread)."""

    def __init__(self, prompter: HostKeyPrompter, save_path: Optional[str] = None):
        self.prompter = prompter
        self.save_path = save_path or known_hosts_path()

    def missing_host_key(self, client, hostname, key):  # type: ignore[override]
        accepted = self.prompter.prompt(hostname, key)
        if not accepted:
            raise paramiko.SSHException(
                f"Host key for {hostname} rejected by user"
            )
        client.get_host_keys().add(hostname, key.get_name(), key)
        try:
            directory = os.path.dirname(self.save_path)
            if directory:
                os.makedirs(directory, exist_ok=True)
            client.save_host_keys(self.save_path)
            log.info("Added host key for %s to %s", hostname, self.save_path)
        except OSError:
            log.exception("Failed to persist host key for %s", hostname)

"""Credential viewer driven by the saved-sessions list and the keyring.

We never list keyring entries directly — keyring backends don't enumerate.
Instead we walk known SSH sessions (with their saved `user@host:port`) and
query the keyring for each. That gives the user a "what does Bifrost remember?"
view they can curate, without depending on a keyring extension.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import credentials


class CredentialManager(QWidget):
    """Lists saved-session credentials with their keyring status."""

    refresh_requested = pyqtSignal()
    forget_requested = pyqtSignal(dict)   # session dict

    def __init__(self, parent=None):
        super().__init__(parent)
        self._sessions: list[dict] = []

        self.layout = QVBoxLayout(self)

        title = QLabel("Saved credentials (system keyring)")
        title.setStyleSheet("font-weight: bold; color: #aaa;")
        self.layout.addWidget(title)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #888; font-size: 10px;")
        self.layout.addWidget(self.status_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Account", "Type", "Stored"])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: #2b2b2b; color: #ccc; border: none; }"
        )
        self.layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.forget_btn = QPushButton("Forget")
        self.forget_btn.clicked.connect(self._forget_selected)
        for b in (self.refresh_btn, self.forget_btn):
            btn_row.addWidget(b)
        self.layout.addLayout(btn_row)

        self._update_status_label()

    def set_sessions(self, sessions: list[dict]) -> None:
        """Refresh the listing from a list of SSH session dicts."""
        self._sessions = sessions
        self.tree.clear()

        for session in sessions:
            if session.get("type") != "SSH":
                continue
            user = session.get("user", "")
            host = session.get("host", "")
            port = int(session.get("port", 22) or 22)
            account = f"{user}@{host}:{port}"

            pw_stored = credentials.get_password(user, host, port) is not None
            key_path = session.get("key_path") or ""
            pp_stored = credentials.get_passphrase(key_path) is not None if key_path else False

            if pw_stored:
                item = QTreeWidgetItem(self.tree, [account, "Password", "✓"])
                item.setData(0, Qt.ItemDataRole.UserRole, session)
            if pp_stored:
                item = QTreeWidgetItem(
                    self.tree, [f"{account}  ({key_path})", "Passphrase", "✓"],
                )
                item.setData(0, Qt.ItemDataRole.UserRole, session)

        if self.tree.topLevelItemCount() == 0:
            placeholder = QTreeWidgetItem(
                self.tree, ["(no saved credentials yet)", "", ""],
            )
            placeholder.setDisabled(True)

        self._update_status_label()

    def _forget_selected(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        session = item.data(0, Qt.ItemDataRole.UserRole)
        if not session:
            return
        reply = QMessageBox.question(
            self, "Forget credential",
            f"Remove saved credentials for {session.get('user')}@{session.get('host')}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.forget_requested.emit(session)

    def _update_status_label(self) -> None:
        if credentials.is_available():
            self.status_label.setText("Keyring backend: available")
        else:
            self.status_label.setText(
                "No usable keyring backend — credentials cannot be saved on this system."
            )

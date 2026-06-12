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

        self.title = QLabel("")
        self.title.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.title)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 10px;")
        self.layout.addWidget(self.status_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Session", "Account", "Secret", "Status", "Provider"])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
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

        provider = credentials.provider_label()
        for session in sessions:
            if session.get("type") != "SSH":
                continue
            user = session.get("user", "")
            host = session.get("host", "")
            port = int(session.get("port", 22) or 22)
            account = credentials.password_account(user, host, port)
            session_name = session.get("name") or account

            pw_stored = credentials.get_password(user, host, port) is not None
            key_path = session.get("key_path") or ""
            pp_stored = credentials.get_passphrase(key_path) is not None if key_path else False

            self._add_audit_row(
                session=session,
                session_name=session_name,
                account=account,
                secret_type="Password",
                stored=pw_stored,
                provider=provider,
            )
            if pp_stored:
                self._add_audit_row(
                    session=session,
                    session_name=session_name,
                    account=credentials.passphrase_account(key_path),
                    secret_type="Passphrase",
                    stored=True,
                    provider=provider,
                )
            elif key_path:
                self._add_audit_row(
                    session=session,
                    session_name=session_name,
                    account=credentials.passphrase_account(key_path),
                    secret_type="Passphrase",
                    stored=False,
                    provider=provider,
                )

        if self.tree.topLevelItemCount() == 0:
            placeholder = QTreeWidgetItem(
                self.tree, ["(no SSH sessions)", "", "", "", ""],
            )
            placeholder.setDisabled(True)

        self._update_status_label()

    def _add_audit_row(
        self,
        *,
        session: dict,
        session_name: str,
        account: str,
        secret_type: str,
        stored: bool,
        provider: str,
    ) -> None:
        item = QTreeWidgetItem(
            self.tree,
            [session_name, account, secret_type, "Saved" if stored else "Missing", provider],
        )
        item.setData(0, Qt.ItemDataRole.UserRole, session)
        item.setData(0, Qt.ItemDataRole.UserRole + 1, stored)
        if not stored:
            item.setForeground(3, Qt.GlobalColor.gray)

    def _forget_selected(self) -> None:
        item = self.tree.currentItem()
        if item is None:
            return
        session = item.data(0, Qt.ItemDataRole.UserRole)
        if not session:
            return
        if not item.data(0, Qt.ItemDataRole.UserRole + 1):
            QMessageBox.information(self, "Forget credential", "No credential is saved for this row.")
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
        label = credentials.provider_label()
        self.title.setText(f"Saved credentials ({label})")
        if credentials.is_available():
            self.status_label.setText(f"{label}: available")
        else:
            self.status_label.setText(f"No usable {label} backend - credentials cannot be saved on this system.")

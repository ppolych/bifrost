"""Credential prompt with a Remember-in-keyring checkbox.

Returned tuple is (text, remember). Caller is responsible for actually saving;
this dialog never touches keyring itself, so it stays unit-testable.
"""

from __future__ import annotations

from typing import Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)


class CredentialPrompt(QDialog):
    def __init__(
        self,
        title: str,
        prompt: str,
        *,
        remember_enabled: bool = True,
        remember_label: str = "Remember in system keyring",
        parent=None,
    ):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)

        layout = QVBoxLayout(self)

        self._label = QLabel(prompt)
        self._label.setWordWrap(True)
        layout.addWidget(self._label)

        self._input = QLineEdit()
        self._input.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addWidget(self._input)

        self._remember = QCheckBox(remember_label)
        self._remember.setEnabled(remember_enabled)
        if not remember_enabled:
            self._remember.setToolTip("No usable keyring backend detected.")
        layout.addWidget(self._remember)

        self._buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        self._buttons.accepted.connect(self.accept)
        self._buttons.rejected.connect(self.reject)
        layout.addWidget(self._buttons)

        self._input.setFocus()

    def value(self) -> str:
        return self._input.text()

    def remember(self) -> bool:
        return self._remember.isChecked() and self._remember.isEnabled()

    @classmethod
    def ask(
        cls,
        title: str,
        prompt: str,
        *,
        remember_enabled: bool = True,
        remember_label: str = "Remember in system keyring",
        parent=None,
    ) -> Tuple[Optional[str], bool]:
        """Convenience: returns (text, remember) or (None, False) if cancelled."""
        dlg = cls(
            title, prompt,
            remember_enabled=remember_enabled,
            remember_label=remember_label,
            parent=parent,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return None, False
        return dlg.value(), dlg.remember()

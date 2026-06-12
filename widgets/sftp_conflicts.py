import posixpath

import paramiko
from PyQt6.QtWidgets import QCheckBox, QInputDialog, QMessageBox

from widgets.sftp_utils import valid_remote_leaf_name as _valid_remote_leaf_name


class SftpConflictMixin:
    def _remote_exists(self, remote: str) -> bool:
        if self.sftp is None:
            return False
        try:
            self.sftp.stat(remote)
            return True
        except (OSError, paramiko.SSHException):
            return False

    def _resolve_upload_conflicts(self, queue: list[tuple[str, str]]) -> list[tuple[str, str]]:
        resolved: list[tuple[str, str]] = []
        apply_choice: str | None = None
        for local, remote in queue:
            if not self._remote_exists(remote):
                resolved.append((local, remote))
                continue
            choice = apply_choice
            apply_to_all = False
            if choice is None:
                choice, apply_to_all = self._prompt_upload_conflict(remote)
            if choice == "cancel":
                return []
            if choice == "skip":
                if apply_to_all:
                    apply_choice = "skip"
                continue
            if choice == "overwrite":
                if apply_to_all:
                    apply_choice = "overwrite"
                resolved.append((local, remote))
                continue
            if choice == "rename":
                renamed = self._prompt_remote_rename(remote)
                if not renamed:
                    return []
                resolved.append((local, renamed))
        return resolved

    def _prompt_upload_conflict(self, remote: str) -> tuple[str, bool]:
        msg = QMessageBox(self)
        msg.setWindowTitle("Remote item exists")
        msg.setText(f"'{posixpath.basename(remote)}' already exists.")
        msg.setInformativeText("Choose how to handle this upload.")
        overwrite = msg.addButton("Overwrite", QMessageBox.ButtonRole.AcceptRole)
        skip = msg.addButton("Skip", QMessageBox.ButtonRole.DestructiveRole)
        rename = msg.addButton("Rename...", QMessageBox.ButtonRole.ActionRole)
        cancel = msg.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        checkbox = QCheckBox("Apply to remaining conflicts")
        msg.setCheckBox(checkbox)
        msg.setDefaultButton(overwrite)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is overwrite:
            return "overwrite", checkbox.isChecked()
        if clicked is skip:
            return "skip", checkbox.isChecked()
        if clicked is rename:
            return "rename", False
        if clicked is cancel:
            return "cancel", False
        return "cancel", False

    def _prompt_remote_rename(self, remote: str) -> str | None:
        directory = posixpath.dirname(remote)
        current = posixpath.basename(remote)
        suggested = self._next_available_remote_name(remote)
        new_name, ok = QInputDialog.getText(
            self,
            "Rename upload",
            "Remote name:",
            text=posixpath.basename(suggested) or current,
        )
        new_name = new_name.strip()
        if not ok or not new_name:
            return None
        if not _valid_remote_leaf_name(new_name):
            QMessageBox.warning(self, "Invalid name", "Enter a single file or folder name.")
            return None
        candidate = posixpath.join(directory, new_name)
        if self._remote_exists(candidate):
            QMessageBox.warning(self, "Rename upload", f"'{new_name}' already exists.")
            return None
        return candidate

    def _next_available_remote_name(self, remote: str) -> str:
        directory = posixpath.dirname(remote)
        name = posixpath.basename(remote)
        stem, ext = posixpath.splitext(name)
        for i in range(1, 1000):
            candidate = posixpath.join(directory, f"{stem} ({i}){ext}")
            if not self._remote_exists(candidate):
                return candidate
        return posixpath.join(directory, f"{stem} copy{ext}")

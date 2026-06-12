import os
import posixpath
import stat
from datetime import datetime

import paramiko
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QInputDialog, QLineEdit, QMenu, QMessageBox, QTreeWidgetItem

from core.icons import named_icon
from widgets.sftp_utils import format_size as _format_size, safe_local_name as _safe_local_name, valid_remote_leaf_name as _valid_remote_leaf_name


class SftpContextMixin:
    def _show_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        if self.sftp is None or item is None:
            return
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        remote = self._remote_path_for_item(item)
        if not remote:
            return
        is_dir = bool(meta.get("is_dir"))

        menu = QMenu(self)
        if is_dir:
            open_act = menu.addAction(named_icon("folder.svg"), "Open folder")
            open_act.triggered.connect(lambda: self._open_remote_folder(remote))
        else:
            open_act = menu.addAction("Open")
            open_act.triggered.connect(lambda: self.file_double_clicked.emit(remote))
            text_act = menu.addAction(named_icon("edit.svg"), "Open in text editor")
            text_act.triggered.connect(lambda: self.file_text_editor_requested.emit(remote))
            custom_act = menu.addAction("Open with command...")
            custom_act.triggered.connect(lambda: self._prompt_open_with(remote))
            default_act = menu.addAction("Open with system default")
            default_act.triggered.connect(lambda: self.file_system_open_requested.emit(remote))
        menu.addSeparator()
        download_act = menu.addAction(named_icon("download.svg"), "Download")
        download_act.triggered.connect(lambda: self._download_context_selection(item, remote, is_dir))

        menu.addSeparator()
        rename_act = menu.addAction(named_icon("edit.svg"), "Rename")
        rename_act.triggered.connect(lambda: self._rename_remote(remote))
        delete_act = menu.addAction("Delete")
        delete_act.triggered.connect(lambda: self._delete_remote(remote, is_dir))

        menu.addSeparator()
        copy_act = menu.addAction("Copy remote path")
        copy_act.triggered.connect(lambda: QApplication.clipboard().setText(remote))
        send_act = menu.addAction("Send path to active terminal")
        send_act.triggered.connect(lambda: self.path_to_terminal_requested.emit(remote))
        props_act = menu.addAction("Properties")
        props_act.triggered.connect(lambda: self._show_properties(remote, item))
        perms_act = menu.addAction("Permissions")
        perms_act.triggered.connect(lambda: self._edit_permissions(remote, item))

        menu.exec(self.tree.mapToGlobal(pos))

    def _download_context_selection(
        self,
        item: QTreeWidgetItem,
        fallback_remote: str,
        fallback_is_dir: bool,
    ) -> None:
        if item.isSelected():
            selected = self._selected_remote_items()
            if len(selected) > 1:
                self._download_remote_items(selected)
                return
        self._download_remote(fallback_remote, fallback_is_dir)

    def _open_remote_folder(self, remote: str) -> None:
        self.cwd = posixpath.normpath(remote) or "/"
        self._refresh()

    def _prompt_open_with(self, remote: str) -> None:
        command, ok = QInputDialog.getText(
            self,
            "Open with command",
            "Command:",
            QLineEdit.EchoMode.Normal,
            "",
        )
        command = command.strip()
        if ok and command:
            self.file_open_with_requested.emit(remote, command)

    def _download_remote(self, remote: str, is_dir: bool = False) -> None:
        if self.sftp is None or self._transfer is not None:
            return
        name = _safe_local_name(posixpath.basename(remote))
        if is_dir:
            parent = QFileDialog.getExistingDirectory(self, "Download folder to", "")
            if parent:
                self._start_transfer("download", os.path.join(parent, name), remote)
        else:
            local, _ = QFileDialog.getSaveFileName(self, "Save as", name)
            if local:
                self._start_transfer("download", local, remote)

    def _download_remote_items(self, items: list[tuple[str, bool]]) -> None:
        if self.sftp is None or self._transfer is not None or not items:
            return
        if len(items) == 1:
            remote, is_dir = items[0]
            self._download_remote(remote, is_dir)
            return
        parent = QFileDialog.getExistingDirectory(self, "Download selected items to", "")
        if not parent:
            return
        queue = [
            (os.path.join(parent, _safe_local_name(posixpath.basename(remote))), remote)
            for remote, _is_dir in items
        ]
        first_local, first_remote = queue[0]
        self._download_queue.extend(queue[1:])
        for local, remote in queue[1:]:
            self._add_queued_transfer("download", local, remote)
        self._start_transfer("download", first_local, first_remote)

    def _rename_remote(self, remote: str) -> None:
        if self.sftp is None:
            return
        current_name = posixpath.basename(remote)
        new_name, ok = QInputDialog.getText(
            self, "Rename remote item", "New name:", text=current_name,
        )
        new_name = new_name.strip()
        if not ok or not new_name or new_name == current_name:
            return
        if not _valid_remote_leaf_name(new_name):
            QMessageBox.warning(self, "Invalid name", "Enter a single file or folder name.")
            return
        target = posixpath.join(posixpath.dirname(remote), new_name)
        try:
            self.sftp.rename(remote, target)
        except (OSError, paramiko.SSHException) as e:
            QMessageBox.warning(self, "Rename failed", str(e))
            return
        self._refresh()

    def _delete_remote(self, remote: str, is_dir: bool) -> None:
        if self.sftp is None:
            return
        name = posixpath.basename(remote)
        detail = " and everything inside it" if is_dir else ""
        reply = QMessageBox.question(
            self,
            "Delete remote item",
            f"Delete '{name}'{detail}?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if is_dir:
                self._delete_remote_dir(remote)
            else:
                self.sftp.remove(remote)
        except (OSError, paramiko.SSHException) as e:
            QMessageBox.warning(self, "Delete failed", str(e))
            return
        self._refresh()

    def _delete_remote_dir(self, remote_dir: str) -> None:
        if self.sftp is None:
            return
        for child in self.sftp.listdir_attr(remote_dir):
            if child.filename in (".", ".."):
                continue
            child_path = posixpath.join(remote_dir, child.filename)
            if stat.S_ISDIR(child.st_mode or 0):
                self._delete_remote_dir(child_path)
            else:
                self.sftp.remove(child_path)
        self.sftp.rmdir(remote_dir)

    def _show_properties(self, remote: str, item: QTreeWidgetItem) -> None:
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        try:
            attr = self.sftp.stat(remote) if self.sftp is not None else None
        except (OSError, paramiko.SSHException) as e:
            QMessageBox.warning(self, "Properties failed", str(e))
            return
        mode = stat.filemode(attr.st_mode or 0) if attr is not None else "-"
        size = "<DIR>" if meta.get("is_dir") else _format_size(attr.st_size or 0)
        modified = "-"
        if attr is not None and attr.st_mtime:
            modified = datetime.fromtimestamp(attr.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        QMessageBox.information(
            self,
            "Remote item properties",
            f"Path: {remote}\nType: {'Folder' if meta.get('is_dir') else 'File'}\n"
            f"Size: {size}\nModified: {modified}\nPermissions: {mode}",
        )

    def _edit_permissions(self, remote: str, item: QTreeWidgetItem) -> None:
        if self.sftp is None:
            return
        try:
            attr = self.sftp.stat(remote)
        except (OSError, paramiko.SSHException) as e:
            QMessageBox.warning(self, "Permissions failed", str(e))
            return
        current = f"{(attr.st_mode or 0) & 0o777:03o}"
        value, ok = QInputDialog.getText(
            self,
            "Remote permissions",
            "Octal mode:",
            text=current,
        )
        value = value.strip()
        if not ok or not value or value == current:
            return
        try:
            mode = int(value, 8)
        except ValueError:
            QMessageBox.warning(self, "Invalid permissions", "Use an octal mode such as 644 or 755.")
            return
        try:
            self.sftp.chmod(remote, mode)
        except (OSError, paramiko.SSHException) as e:
            QMessageBox.warning(self, "Permissions failed", str(e))
            return
        self._refresh()

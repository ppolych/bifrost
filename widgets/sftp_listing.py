import logging
import os
import posixpath
import stat
from datetime import datetime
from typing import Optional

import paramiko
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QMessageBox, QTreeWidgetItem

from widgets.sftp_utils import EXT_THEME_ICONS as _EXT_THEME_ICONS, format_size as _format_size

log = logging.getLogger(__name__)


class SftpListingMixin:

    def _icon_for(self, filename: str, attr) -> QIcon:
        """Pick an icon for a single listing entry."""
        mode = (attr.st_mode or 0)
        if stat.S_ISDIR(mode):
            return self._dir_icon
        if stat.S_ISLNK(mode):
            return self._link_icon
        ext = os.path.splitext(filename)[1].lower()
        theme_name = _EXT_THEME_ICONS.get(ext)
        if theme_name:
            icon = QIcon.fromTheme(theme_name)
            if not icon.isNull():
                return icon
        return self._file_icon

    def _refresh(self) -> None:
        if self.sftp is None:
            return
        self.tree.clear()
        self.path_label.setText(self.cwd)
        try:
            entries = self.sftp.listdir_attr(self.cwd)
        except (OSError, paramiko.SSHException) as e:
            log.warning("listdir failed: %s", e)
            QMessageBox.warning(self, "SFTP", f"Failed to list {self.cwd}:\n{e}")
            return

        if self.cwd not in ("", "/"):
            parent = QTreeWidgetItem(self.tree, ["..", "<DIR>", ""])
            parent.setIcon(0, self._dir_icon)
            parent.setData(0, Qt.ItemDataRole.UserRole, {"is_dir": True, "is_parent": True})

        # Directories first, then files; both alphabetically.
        def sort_key(attr):
            is_dir = stat.S_ISDIR(attr.st_mode or 0)
            return (0 if is_dir else 1, attr.filename.lower())

        for attr in sorted(entries, key=sort_key):
            name = attr.filename
            if name in (".", ".."):
                continue
            if not self.show_hidden and name.startswith("."):
                continue
            is_dir = stat.S_ISDIR(attr.st_mode or 0)
            size = "<DIR>" if is_dir else _format_size(attr.st_size or 0)
            mtime = "—"
            if attr.st_mtime:
                mtime = datetime.fromtimestamp(attr.st_mtime).strftime("%Y-%m-%d %H:%M")
            item = QTreeWidgetItem(self.tree, [name, size, mtime])
            item.setIcon(0, self._icon_for(name, attr))
            item.setData(0, Qt.ItemDataRole.UserRole, {"is_dir": is_dir, "name": name})

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        if self.sftp is None:
            return
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if meta.get("is_parent"):
            self._go_up()
            return
        if meta.get("is_dir"):
            new_path = posixpath.normpath(posixpath.join(self.cwd, meta["name"]))
            self.cwd = new_path if new_path else "/"
            self._refresh()
        else:
            self.file_double_clicked.emit(posixpath.join(self.cwd, meta["name"]))

    def _go_up(self) -> None:
        if self.sftp is None or self.cwd in ("", "/"):
            return
        self.cwd = posixpath.normpath(posixpath.join(self.cwd, ".."))
        self._refresh()

    def _navigate_to_path_input(self) -> None:
        if self.sftp is None:
            self.path_label.setText("Not connected")
            return
        text = self.path_input.text().strip()
        if not text:
            self.path_label.setText(self.cwd)
            return
        target = text if text.startswith("/") else posixpath.join(self.cwd, text)
        target = posixpath.normpath(target) or "/"
        try:
            attr = self.sftp.stat(target)
        except (OSError, paramiko.SSHException) as e:
            self.path_label.setText(self.cwd)
            QMessageBox.warning(self, "SFTP", f"Failed to open {target}:\n{e}")
            return
        if not stat.S_ISDIR(attr.st_mode or 0):
            self.path_label.setText(self.cwd)
            QMessageBox.warning(self, "SFTP", f"{target} is not a directory.")
            return
        self.cwd = target
        self._refresh()

    # ----- transfers -----

    def _selected_remote_path(self) -> Optional[str]:
        item = self.tree.currentItem()
        if item is None:
            return None
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if meta.get("is_dir"):
            return None
        return posixpath.join(self.cwd, meta["name"])

    def _selected_remote_items(self) -> list[tuple[str, bool]]:
        items = self.tree.selectedItems()
        if not items and self.tree.currentItem() is not None:
            items = [self.tree.currentItem()]
        selected: list[tuple[str, bool]] = []
        seen: set[str] = set()
        for item in items:
            remote = self._remote_path_for_item(item)
            if not remote or remote in seen:
                continue
            meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
            selected.append((remote, bool(meta.get("is_dir"))))
            seen.add(remote)
        return selected

    def _remote_path_for_item(self, item: QTreeWidgetItem | None) -> Optional[str]:
        if item is None:
            return None
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        name = meta.get("name")
        if not name or meta.get("is_parent"):
            return None
        return posixpath.join(self.cwd, name)

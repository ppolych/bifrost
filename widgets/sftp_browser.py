"""SFTP browser that reuses an existing paramiko SSHClient.

Attach via `attach(ssh_client)` once the SSH terminal has connected. The
browser opens its own SFTPClient channel on that connection, so credentials
and host-key verification are shared with the terminal tab.

File transfers run on a QThread with progress callbacks so the UI stays
responsive on slow links.
"""

from __future__ import annotations

import logging
import os
import posixpath
import stat
from datetime import datetime
from typing import Optional

import paramiko
from PyQt6.QtCore import QSize, Qt, QThread, pyqtSignal
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QStyle,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.icons import named_icon


# Extension → freedesktop icon name. QIcon.fromTheme returns null on systems
# without that icon, and we fall through to the generic file icon below.
_EXT_THEME_ICONS = {
    ".py": "text-x-python",
    ".sh": "application-x-shellscript",
    ".bash": "application-x-shellscript",
    ".zsh": "application-x-shellscript",
    ".pl": "application-x-perl",
    ".rb": "application-x-ruby",
    ".go": "text-x-go",
    ".rs": "text-rust",
    ".c": "text-x-csrc",
    ".h": "text-x-chdr",
    ".cpp": "text-x-c++src",
    ".hpp": "text-x-c++hdr",
    ".java": "text-x-java",
    ".js": "application-javascript",
    ".ts": "application-typescript",
    ".html": "text-html",
    ".htm": "text-html",
    ".css": "text-css",
    ".md": "text-markdown",
    ".rst": "text-x-rst",
    ".txt": "text-x-generic",
    ".log": "text-x-log",
    ".conf": "text-x-generic",
    ".ini": "text-x-generic",
    ".cfg": "text-x-generic",
    ".toml": "text-x-generic",
    ".env": "text-x-generic",
    ".json": "application-json",
    ".xml": "application-xml",
    ".yaml": "application-yaml",
    ".yml": "application-yaml",
    ".png": "image-png",
    ".jpg": "image-jpeg",
    ".jpeg": "image-jpeg",
    ".gif": "image-gif",
    ".bmp": "image-bmp",
    ".svg": "image-svg+xml",
    ".webp": "image-webp",
    ".ico": "image-x-ico",
    ".pdf": "application-pdf",
    ".zip": "application-zip",
    ".tar": "application-x-tar",
    ".gz": "application-gzip",
    ".tgz": "application-gzip",
    ".bz2": "application-x-bzip",
    ".xz": "application-x-xz",
    ".7z": "application-x-7z-compressed",
    ".rar": "application-x-rar",
    ".deb": "application-x-deb",
    ".rpm": "application-x-rpm",
    ".doc": "application-msword",
    ".docx": "application-msword",
    ".xls": "application-vnd.ms-excel",
    ".xlsx": "application-vnd.ms-excel",
    ".ppt": "application-vnd.ms-powerpoint",
    ".pptx": "application-vnd.ms-powerpoint",
    ".mp3": "audio-mpeg",
    ".wav": "audio-x-wav",
    ".flac": "audio-flac",
    ".ogg": "audio-ogg",
    ".mp4": "video-mp4",
    ".mkv": "video-x-matroska",
    ".webm": "video-webm",
    ".avi": "video-x-msvideo",
    ".mov": "video-quicktime",
}

log = logging.getLogger(__name__)


def _format_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    for unit in ("KB", "MB", "GB", "TB"):
        n /= 1024
        if n < 1024:
            return f"{n:.1f} {unit}"
    return f"{n:.1f} PB"


class _TransferThread(QThread):
    progress = pyqtSignal(int, int)       # bytes_done, bytes_total
    finished_ok = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, sftp: paramiko.SFTPClient, mode: str, local_path: str, remote_path: str):
        super().__init__()
        self.sftp = sftp
        self.mode = mode  # "upload" | "download"
        self.local_path = local_path
        self.remote_path = remote_path

    def run(self):
        try:
            if self.mode == "upload":
                if os.path.isdir(self.local_path):
                    total = self._local_size(self.local_path)
                    done = 0
                    self._emit_progress(0, total)
                    done = self._upload_dir(self.local_path, self.remote_path, done, total)
                    self._emit_progress(done, total)
                    self.finished_ok.emit(f"Uploaded folder {os.path.basename(self.local_path)}")
                else:
                    self.sftp.put(self.local_path, self.remote_path, callback=self._callback)
                    self.finished_ok.emit(f"Uploaded {os.path.basename(self.local_path)}")
            else:
                if self._remote_is_dir(self.remote_path):
                    total = self._remote_size(self.remote_path)
                    done = 0
                    self._emit_progress(0, total)
                    done = self._download_dir(self.remote_path, self.local_path, done, total)
                    self._emit_progress(done, total)
                    self.finished_ok.emit(f"Downloaded folder {posixpath.basename(self.remote_path)}")
                else:
                    self.sftp.get(self.remote_path, self.local_path, callback=self._callback)
                    self.finished_ok.emit(f"Downloaded {posixpath.basename(self.remote_path)}")
        except (OSError, paramiko.SSHException) as e:
            log.exception("SFTP transfer failed")
            self.failed.emit(str(e))

    def _callback(self, done: int, total: int):
        self.progress.emit(done, total)

    def _emit_progress(self, done: int, total: int) -> None:
        self.progress.emit(done, total)

    def _mkdir_if_missing(self, remote_path: str) -> None:
        try:
            self.sftp.mkdir(remote_path)
        except OSError:
            # Existing directories are fine; put/get will report real failures.
            pass

    def _local_size(self, local_path: str) -> int:
        if os.path.isfile(local_path):
            return os.path.getsize(local_path)
        total = 0
        for root, _dirs, files in os.walk(local_path):
            for name in files:
                path = os.path.join(root, name)
                try:
                    total += os.path.getsize(path)
                except OSError:
                    log.debug("could not stat %s", path, exc_info=True)
        return total

    def _remote_is_dir(self, remote_path: str) -> bool:
        attr = self.sftp.stat(remote_path)
        return stat.S_ISDIR(attr.st_mode or 0)

    def _remote_size(self, remote_path: str) -> int:
        attr = self.sftp.stat(remote_path)
        if not stat.S_ISDIR(attr.st_mode or 0):
            return attr.st_size or 0
        total = 0
        for child in self.sftp.listdir_attr(remote_path):
            if child.filename in (".", ".."):
                continue
            child_path = posixpath.join(remote_path, child.filename)
            if stat.S_ISDIR(child.st_mode or 0):
                total += self._remote_size(child_path)
            else:
                total += child.st_size or 0
        return total

    def _upload_dir(self, local_dir: str, remote_dir: str, done: int, total: int) -> int:
        self._mkdir_if_missing(remote_dir)
        for name in sorted(os.listdir(local_dir)):
            local_child = os.path.join(local_dir, name)
            remote_child = posixpath.join(remote_dir, name)
            if os.path.isdir(local_child):
                done = self._upload_dir(local_child, remote_child, done, total)
            elif os.path.isfile(local_child):
                base = done

                def callback(sent: int, _file_total: int, base=base):
                    self._emit_progress(base + sent, total)

                self.sftp.put(local_child, remote_child, callback=callback)
                done += os.path.getsize(local_child)
                self._emit_progress(done, total)
        return done

    def _download_dir(self, remote_dir: str, local_dir: str, done: int, total: int) -> int:
        os.makedirs(local_dir, exist_ok=True)
        for child in sorted(self.sftp.listdir_attr(remote_dir), key=lambda a: a.filename.lower()):
            if child.filename in (".", ".."):
                continue
            remote_child = posixpath.join(remote_dir, child.filename)
            local_child = os.path.join(local_dir, child.filename)
            if stat.S_ISDIR(child.st_mode or 0):
                done = self._download_dir(remote_child, local_child, done, total)
            else:
                base = done

                def callback(received: int, _file_total: int, base=base):
                    self._emit_progress(base + received, total)

                self.sftp.get(remote_child, local_child, callback=callback)
                done += child.st_size or 0
                self._emit_progress(done, total)
        return done


class SftpBrowser(QWidget):
    file_double_clicked = pyqtSignal(str)
    file_text_editor_requested = pyqtSignal(str)
    file_open_with_requested = pyqtSignal(str, str)
    file_system_open_requested = pyqtSignal(str)
    path_to_terminal_requested = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.sftp: Optional[paramiko.SFTPClient] = None
        self.cwd: str = "/"
        self._transfer: Optional[_TransferThread] = None
        # Pending uploads chained behind the current transfer (drag-and-drop).
        self._upload_queue: list[tuple[str, str]] = []  # (local, remote)
        # Hide dotfiles by default; flipped via set_show_hidden() from settings.
        self.show_hidden: bool = False

        # Accept local-file drops anywhere in the browser. dragEnter/drop
        # gating below filters non-file mime types and rejects when no SFTP
        # is attached.
        self.setAcceptDrops(True)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        # Toolbar — icon-only buttons with tooltips for the labels.
        self.toolbar = QToolBar()
        self.toolbar.setIconSize(QSize(16, 16))
        self.up_btn = QPushButton(named_icon("arrow_upward.svg"), "")
        self.up_btn.setToolTip("Up")
        self.refresh_btn = QPushButton(named_icon("refresh.svg"), "")
        self.refresh_btn.setToolTip("Refresh")
        self.upload_btn = QPushButton(named_icon("upload.svg"), "")
        self.upload_btn.setToolTip("Upload…")
        self.download_btn = QPushButton(named_icon("download.svg"), "")
        self.download_btn.setToolTip("Download…")
        for b in [self.up_btn, self.refresh_btn, self.upload_btn, self.download_btn]:
            b.setProperty("compact", True)
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(QSize(28, 24))
            b.setStyleSheet(
                "QPushButton { background-color: #3c3f41; border: 1px solid #555; }"
                "QPushButton:hover { background-color: #4b4b4b; }"
                "QPushButton:disabled { background-color: #2b2b2b; border-color: #444; }"
            )
            self.toolbar.addWidget(b)
        self.layout.addWidget(self.toolbar)

        self.up_btn.clicked.connect(self._go_up)
        self.refresh_btn.clicked.connect(self._refresh)
        self.upload_btn.clicked.connect(self._upload)
        self.download_btn.clicked.connect(self._download)

        # Path label
        self.path_label = QLabel("Not connected")
        self.path_label.setStyleSheet("color: #aaa; padding: 4px;")
        self.layout.addWidget(self.path_label)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size", "Modified"])
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: #1e1e1e; color: #ccc; border: none; }"
        )
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.layout.addWidget(self.tree)

        # Default icons from the OS style (cross-platform; native-looking).
        style = self.style()
        self._dir_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self._file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        # Optional link icon used when we detect a symlink in listdir_attr.
        self._link_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon)

        # Transfer status (hidden until an upload/download starts).
        self.transfer_panel = QWidget()
        transfer_layout = QHBoxLayout(self.transfer_panel)
        transfer_layout.setContentsMargins(4, 3, 4, 3)
        transfer_layout.setSpacing(8)
        self.transfer_status = QLabel("")
        self.transfer_status.setStyleSheet("color: #cfcfcf;")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setMinimumWidth(140)
        self.progress.setStyleSheet(
            "QProgressBar { background-color: #1e1e1e; border: 1px solid #555; "
            "color: #f0f0f0; height: 14px; text-align: center; }"
            "QProgressBar::chunk { background-color: #4ea1f3; }"
        )
        transfer_layout.addWidget(self.transfer_status, 1)
        transfer_layout.addWidget(self.progress, 2)
        self.transfer_panel.hide()
        self.layout.addWidget(self.transfer_panel)
        self._transfer_mode: Optional[str] = None
        self._transfer_name: str = ""

        self._set_buttons_enabled(False)

    # ----- attach / detach -----

    def attach(self, ssh_client: paramiko.SSHClient) -> None:
        """Open an SFTP channel on the given SSHClient and populate the browser."""
        self.detach()
        try:
            self.sftp = ssh_client.open_sftp()
        except (OSError, paramiko.SSHException) as e:
            log.exception("open_sftp failed")
            self.path_label.setText(f"SFTP unavailable: {e}")
            self.sftp = None
            return
        try:
            self.cwd = self.sftp.normalize(".")
        except (OSError, paramiko.SSHException):
            self.cwd = "/"
        self._set_buttons_enabled(True)
        self._refresh()

    def detach(self) -> None:
        if self.sftp is not None:
            try:
                self.sftp.close()
            except Exception:
                log.debug("sftp close failed", exc_info=True)
            self.sftp = None
        self.tree.clear()
        self.path_label.setText("Not connected")
        self._reset_transfer_progress()
        self._set_buttons_enabled(False)

    def is_attached(self) -> bool:
        return self.sftp is not None

    def set_show_hidden(self, value: bool) -> None:
        """Toggle dotfile visibility; refresh the listing if we're attached."""
        value = bool(value)
        if value == self.show_hidden:
            return
        self.show_hidden = value
        if self.sftp is not None:
            self._refresh()

    # ----- listing / navigation -----

    def _set_buttons_enabled(self, enabled: bool) -> None:
        for b in (self.up_btn, self.refresh_btn, self.upload_btn, self.download_btn):
            b.setEnabled(enabled)

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

    # ----- transfers -----

    def _selected_remote_path(self) -> Optional[str]:
        item = self.tree.currentItem()
        if item is None:
            return None
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if meta.get("is_dir"):
            return None
        return posixpath.join(self.cwd, meta["name"])

    def _remote_path_for_item(self, item: QTreeWidgetItem | None) -> Optional[str]:
        if item is None:
            return None
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        name = meta.get("name")
        if not name:
            return None
        return posixpath.join(self.cwd, name)

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
        download_act.triggered.connect(lambda: self._download_remote(remote, is_dir))

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
        if is_dir:
            parent = QFileDialog.getExistingDirectory(self, "Download folder to", "")
            if parent:
                self._start_transfer("download", os.path.join(parent, posixpath.basename(remote)), remote)
        else:
            local, _ = QFileDialog.getSaveFileName(self, "Save as", posixpath.basename(remote))
            if local:
                self._start_transfer("download", local, remote)

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
        reply = QMessageBox.question(
            self,
            "Delete remote item",
            f"Delete '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            if is_dir:
                self.sftp.rmdir(remote)
            else:
                self.sftp.remove(remote)
        except (OSError, paramiko.SSHException) as e:
            QMessageBox.warning(self, "Delete failed", str(e))
            return
        self._refresh()

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

    def _upload(self) -> None:
        if self.sftp is None or self._transfer is not None:
            return
        local, _ = QFileDialog.getOpenFileName(self, "Upload file", "")
        if not local:
            return
        remote = posixpath.join(self.cwd, os.path.basename(local))
        self._start_transfer("upload", local, remote)

    def _download(self) -> None:
        if self.sftp is None or self._transfer is not None:
            return
        remote = self._selected_remote_path()
        if not remote:
            QMessageBox.information(self, "SFTP", "Select a file (not a directory) to download.")
            return
        local, _ = QFileDialog.getSaveFileName(
            self, "Save as", posixpath.basename(remote)
        )
        if not local:
            return
        self._start_transfer("download", local, remote)

    def _start_transfer(self, mode: str, local: str, remote: str) -> None:
        self._begin_transfer_progress(mode, local, remote)
        self._set_buttons_enabled(False)

        t = _TransferThread(self.sftp, mode, local, remote)
        t.progress.connect(self._on_transfer_progress)
        t.finished_ok.connect(self._on_transfer_done)
        t.failed.connect(self._on_transfer_failed)
        t.finished.connect(lambda: self._cleanup_transfer())
        self._transfer = t
        t.start()

    def _on_transfer_progress(self, done: int, total: int) -> None:
        self._update_transfer_progress(done, total)

    def _begin_transfer_progress(self, mode: str, local: str, remote: str) -> None:
        self._transfer_mode = mode
        self._transfer_name = (
            os.path.basename(local) if mode == "upload" else posixpath.basename(remote)
        )
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat("0%")
        self.transfer_panel.show()
        self._update_transfer_progress(0, 0)

    def _update_transfer_progress(self, done: int, total: int) -> None:
        if total > 0:
            percent = max(0, min(100, int(done * 100 / total)))
            size_text = f"{_format_size(done)} / {_format_size(total)}"
        else:
            percent = 0
            size_text = _format_size(done)
        self.progress.setValue(percent)
        self.progress.setFormat(f"{percent}%")

        action = "Uploading" if self._transfer_mode == "upload" else "Downloading"
        if self._transfer_name:
            self.transfer_status.setText(f"{action} {self._transfer_name}  -  {size_text}")
        else:
            self.transfer_status.setText(f"{action}  -  {size_text}")

    def _reset_transfer_progress(self) -> None:
        self._transfer_mode = None
        self._transfer_name = ""
        self.progress.setValue(0)
        self.progress.setFormat("0%")
        self.transfer_status.clear()
        self.transfer_panel.hide()

    def _on_transfer_done(self, message: str) -> None:
        self.progress.setValue(100)
        self.progress.setFormat("100%")
        self.transfer_status.setText(message)
        self.transfer_panel.show()
        self.path_label.setText(f"{self.cwd}   ·   {message}")
        self._refresh()

    def _on_transfer_failed(self, message: str) -> None:
        self.transfer_status.setText(f"Transfer failed: {message}")
        self.transfer_panel.show()
        QMessageBox.warning(self, "SFTP transfer failed", message)

    def _cleanup_transfer(self) -> None:
        self._set_buttons_enabled(True)
        self._transfer = None
        self._reset_transfer_progress()
        # Chain into the next queued upload (drag-and-drop with multiple files).
        if self._upload_queue and self.sftp is not None:
            local, remote = self._upload_queue.pop(0)
            self._start_transfer("upload", local, remote)

    # ----- drag-and-drop uploads -----

    def _target_dir_for_drop(self, pos) -> str:
        """If the drop landed on a directory row, upload into that directory;
        otherwise use the current cwd. Used by dropEvent (and a unit test)."""
        tree_pos = self.tree.mapFrom(self, pos)
        item = self.tree.itemAt(tree_pos)
        if item is None:
            return self.cwd
        meta = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if meta.get("is_dir") and meta.get("name"):
            return posixpath.join(self.cwd, meta["name"])
        return self.cwd

    def dragEnterEvent(self, event) -> None:
        if self.sftp is None:
            event.ignore()
            return
        md = event.mimeData()
        if md.hasUrls() and any(u.isLocalFile() for u in md.urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        # Same gate as dragEnter — many platforms only consult this one once a
        # drag is already inside.
        if self.sftp is not None and event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:
        if self.sftp is None:
            event.ignore()
            return
        paths = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        if not paths:
            event.ignore()
            return

        target_dir = self._target_dir_for_drop(event.position().toPoint())

        # Queue both files and folders; folders upload recursively.
        upload_items: list[str] = []
        for p in paths:
            if os.path.isdir(p) or os.path.isfile(p):
                upload_items.append(p)

        if not upload_items:
            event.acceptProposedAction()
            return

        # Build the upload queue. If nothing's transferring, kick off the first
        # immediately; the rest chain via _cleanup_transfer.
        new_queue = [
            (local, posixpath.join(target_dir, os.path.basename(local)))
            for local in upload_items
        ]
        if self._transfer is not None:
            self._upload_queue.extend(new_queue)
        else:
            first_local, first_remote = new_queue[0]
            self._upload_queue.extend(new_queue[1:])
            self._start_transfer("upload", first_local, first_remote)

        event.acceptProposedAction()

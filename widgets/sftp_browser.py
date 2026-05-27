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
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
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
                self.sftp.put(self.local_path, self.remote_path, callback=self._callback)
                self.finished_ok.emit(f"Uploaded {os.path.basename(self.local_path)}")
            else:
                self.sftp.get(self.remote_path, self.local_path, callback=self._callback)
                self.finished_ok.emit(f"Downloaded {posixpath.basename(self.remote_path)}")
        except (OSError, paramiko.SSHException) as e:
            log.exception("SFTP transfer failed")
            self.failed.emit(str(e))

    def _callback(self, done: int, total: int):
        self.progress.emit(done, total)


class SftpBrowser(QWidget):
    file_double_clicked = pyqtSignal(str)

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
        self.layout.addWidget(self.tree)

        # Default icons from the OS style (cross-platform; native-looking).
        style = self.style()
        self._dir_icon = style.standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        self._file_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileIcon)
        # Optional link icon used when we detect a symlink in listdir_attr.
        self._link_icon = style.standardIcon(QStyle.StandardPixmap.SP_FileLinkIcon)

        # Progress bar (hidden until a transfer starts)
        self.progress = QProgressBar()
        self.progress.hide()
        self.layout.addWidget(self.progress)

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
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setFormat(f"{mode}: %p%")
        self.progress.show()
        self._set_buttons_enabled(False)

        t = _TransferThread(self.sftp, mode, local, remote)
        t.progress.connect(self._on_transfer_progress)
        t.finished_ok.connect(self._on_transfer_done)
        t.failed.connect(self._on_transfer_failed)
        t.finished.connect(lambda: self._cleanup_transfer())
        self._transfer = t
        t.start()

    def _on_transfer_progress(self, done: int, total: int) -> None:
        if total > 0:
            self.progress.setValue(int(done * 100 / total))

    def _on_transfer_done(self, message: str) -> None:
        self.path_label.setText(f"{self.cwd}   ·   {message}")
        self._refresh()

    def _on_transfer_failed(self, message: str) -> None:
        QMessageBox.warning(self, "SFTP transfer failed", message)

    def _cleanup_transfer(self) -> None:
        self.progress.hide()
        self._set_buttons_enabled(True)
        self._transfer = None
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

        # Split into files we'll upload and directories we'll skip with a notice
        # (recursive upload isn't implemented yet).
        files: list[str] = []
        skipped_dirs: list[str] = []
        for p in paths:
            if os.path.isdir(p):
                skipped_dirs.append(p)
            elif os.path.isfile(p):
                files.append(p)

        if skipped_dirs:
            self.path_label.setText(
                f"{self.cwd}   ·   skipped {len(skipped_dirs)} director"
                f"{'ies' if len(skipped_dirs) != 1 else 'y'} (only files supported)"
            )

        if not files:
            event.acceptProposedAction()
            return

        # Build the upload queue. If nothing's transferring, kick off the first
        # immediately; the rest chain via _cleanup_transfer.
        new_queue = [
            (local, posixpath.join(target_dir, os.path.basename(local)))
            for local in files
        ]
        if self._transfer is not None:
            self._upload_queue.extend(new_queue)
        else:
            first_local, first_remote = new_queue[0]
            self._upload_queue.extend(new_queue[1:])
            self._start_transfer("upload", first_local, first_remote)

        event.acceptProposedAction()

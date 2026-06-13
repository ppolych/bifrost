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
from typing import Optional

import paramiko
from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QProgressBar,
    QPushButton,
    QAbstractItemView,
    QStyle,
    QToolBar,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core.icons import named_icon
from widgets.sftp_conflicts import SftpConflictMixin
from widgets.sftp_context import SftpContextMixin
from widgets.sftp_drop import SftpDropMixin
from widgets.sftp_listing import SftpListingMixin
from widgets.sftp_transfer import TransferThread as _TransferThread
from widgets.sftp_transfer_ops import SftpTransferOpsMixin
from widgets.sftp_transfer_queue import SftpTransferQueueMixin
from widgets.sftp_utils import (
    EXT_THEME_ICONS as _EXT_THEME_ICONS,
    format_size as _format_size,
    safe_local_name as _safe_local_name,
    valid_remote_leaf_name as _valid_remote_leaf_name,
)

log = logging.getLogger(__name__)


class SftpBrowser(
    SftpListingMixin,
    SftpContextMixin,
    SftpConflictMixin,
    SftpTransferOpsMixin,
    SftpTransferQueueMixin,
    SftpDropMixin,
    QWidget,
):
    file_double_clicked = pyqtSignal(str)
    file_text_editor_requested = pyqtSignal(str)
    file_open_with_requested = pyqtSignal(str, str)
    file_system_open_requested = pyqtSignal(str)
    path_to_terminal_requested = pyqtSignal(str)
    column_widths_changed = pyqtSignal(list)

    def __init__(self):
        super().__init__()
        self._ssh_client: Optional[paramiko.SSHClient] = None
        self.sftp: Optional[paramiko.SFTPClient] = None
        self.cwd: str = "/"
        self._transfer: Optional[_TransferThread] = None
        # Pending uploads chained behind the current transfer (drag-and-drop).
        self._upload_queue: list[tuple[str, str]] = []  # (local, remote)
        self._download_queue: list[tuple[str, str]] = []  # (local, remote)
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
        self.upload_btn.setToolTip("Upload file...")
        self.upload_folder_btn = QPushButton(named_icon("folder.svg"), "")
        self.upload_folder_btn.setToolTip("Upload folder...")
        self.new_folder_btn = QPushButton(named_icon("add.svg"), "")
        self.new_folder_btn.setToolTip("New remote folder")
        self.download_btn = QPushButton(named_icon("download.svg"), "")
        self.download_btn.setToolTip("Download…")
        self.cancel_btn = QPushButton("X")
        self.cancel_btn.setToolTip("Cancel transfer")
        for b in [self.up_btn, self.refresh_btn, self.upload_btn, self.upload_folder_btn, self.new_folder_btn, self.download_btn, self.cancel_btn]:
            b.setProperty("compact", True)
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(QSize(28, 24))
            self.toolbar.addWidget(b)
        self.layout.addWidget(self.toolbar)

        self.up_btn.clicked.connect(self._go_up)
        self.refresh_btn.clicked.connect(self._refresh)
        self.upload_btn.clicked.connect(self._upload)
        self.upload_folder_btn.clicked.connect(self._upload_folder)
        self.new_folder_btn.clicked.connect(self._new_folder)
        self.download_btn.clicked.connect(self._download)
        self.cancel_btn.clicked.connect(self._cancel_transfer)

        # Path label
        self.path_label = QLabel("Not connected")
        self.path_label.setStyleSheet("padding: 4px;")
        self.layout.addWidget(self.path_label)

        # Tree
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Name", "Size", "Modified"])
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.header().sectionResized.connect(self._emit_column_widths_changed)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
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
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        self.progress.setTextVisible(True)
        self.progress.setMinimumWidth(140)
        transfer_layout.addWidget(self.transfer_status, 1)
        transfer_layout.addWidget(self.progress, 2)
        self.transfer_panel.hide()
        self.layout.addWidget(self.transfer_panel)
        self._transfer_mode: Optional[str] = None
        self._transfer_name: str = ""
        self._active_transfer_row: QTreeWidgetItem | None = None
        self._last_transfer_failed = False
        self._last_transfer_cancelled = False
        self._detaching = False

        self.transfer_queue = QTreeWidget()
        self.transfer_queue.setHeaderLabels(["Status", "Operation", "Item"])
        self.transfer_queue.setRootIsDecorated(False)
        self.transfer_queue.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.transfer_queue.setMaximumHeight(96)
        self.transfer_queue.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.transfer_queue.customContextMenuRequested.connect(self._show_transfer_context_menu)
        self.transfer_queue.hide()
        self.layout.addWidget(self.transfer_queue)

        self._set_buttons_enabled(False)

    def column_widths(self) -> list[int]:
        return [self.tree.columnWidth(i) for i in range(self.tree.columnCount())]

    def set_column_widths(self, widths: list[int]) -> None:
        if not isinstance(widths, list) or len(widths) != self.tree.columnCount():
            return
        header = self.tree.header()
        for i, width in enumerate(widths):
            try:
                value = int(width)
            except (TypeError, ValueError):
                continue
            if value > 0:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
                self.tree.setColumnWidth(i, value)

    def _emit_column_widths_changed(self, *_args) -> None:
        self.column_widths_changed.emit(self.column_widths())

    # ----- attach / detach -----

    def attach(self, ssh_client: paramiko.SSHClient) -> None:
        """Open an SFTP channel on the given SSHClient and populate the browser."""
        self.detach()
        self._ssh_client = ssh_client
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
        self._detaching = True
        self._stop_transfer(wait=True)
        self._ssh_client = None
        if self.sftp is not None:
            try:
                self.sftp.close()
            except Exception:
                log.debug("sftp close failed", exc_info=True)
            self.sftp = None
        self.tree.clear()
        self.path_label.setText("Not connected")
        self._reset_transfer_progress()
        self._upload_queue.clear()
        self._download_queue.clear()
        self.transfer_queue.clear()
        self.transfer_queue.hide()
        self._set_buttons_enabled(False)
        self._detaching = False

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
        for b in (self.up_btn, self.refresh_btn, self.upload_btn, self.upload_folder_btn, self.new_folder_btn, self.download_btn):
            b.setEnabled(enabled)
        self.cancel_btn.setEnabled(self._transfer is not None)



    # ----- drag-and-drop uploads -----

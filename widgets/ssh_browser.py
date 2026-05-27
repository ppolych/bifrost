"""Active SSH connections list.

Driven by BifrostApp via `update_from_tabs(connections)`. Each entry knows its
tab index so the user can jump to or disconnect the matching session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)


@dataclass
class ActiveConnection:
    tab_index: int
    host: str
    user: str
    port: int
    status: str  # "connecting" | "connected" | "closed" | "failed"


class SshBrowser(QWidget):
    """Read-only listing of active SSH backends; emits actions to BifrostApp."""

    refresh_requested = pyqtSignal()
    focus_tab = pyqtSignal(int)        # tab_index
    disconnect_tab = pyqtSignal(int)   # tab_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        self.label = QLabel("Active SSH connections")
        self.label.setStyleSheet("font-weight: bold; color: #aaa;")
        self.layout.addWidget(self.label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Host", "User", "Port", "Status"])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: #2b2b2b; color: #ccc; border: none; }"
        )
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.focus_btn = QPushButton("Focus tab")
        self.focus_btn.clicked.connect(self._focus_selected)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._disconnect_selected)
        for b in (self.refresh_btn, self.focus_btn, self.disconnect_btn):
            btn_row.addWidget(b)
        self.layout.addLayout(btn_row)

        self.update_from_tabs([])

    def update_from_tabs(self, connections: list[ActiveConnection]) -> None:
        self.tree.clear()
        if not connections:
            placeholder = QTreeWidgetItem(self.tree, ["(no active SSH sessions)", "", "", ""])
            placeholder.setDisabled(True)
            return
        for c in connections:
            item = QTreeWidgetItem(self.tree, [c.host, c.user, str(c.port), c.status])
            item.setData(0, Qt.ItemDataRole.UserRole, c.tab_index)

    def _selected_tab_index(self) -> Optional[int]:
        item = self.tree.currentItem()
        if item is None:
            return None
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        return int(idx) if idx is not None else None

    def _focus_selected(self) -> None:
        idx = self._selected_tab_index()
        if idx is not None:
            self.focus_tab.emit(idx)

    def _disconnect_selected(self) -> None:
        idx = self._selected_tab_index()
        if idx is not None:
            self.disconnect_tab.emit(idx)

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is not None:
            self.focus_tab.emit(int(idx))

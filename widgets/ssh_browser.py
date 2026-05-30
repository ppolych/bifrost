"""Active SSH connections list.

Driven by BifrostApp via `update_from_tabs(connections)`. Each entry knows its
tab index so the user can jump to or disconnect the matching session.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
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
    status: str
    tunnels: list[dict] | None = None


class SshBrowser(QWidget):
    """Read-only listing of active SSH backends; emits actions to BifrostApp."""

    refresh_requested = pyqtSignal()
    focus_tab = pyqtSignal(int)        # tab_index
    disconnect_tab = pyqtSignal(int)   # tab_index
    reconnect_tab = pyqtSignal(int)    # tab_index
    reconnect_all = pyqtSignal()
    stop_tunnel = pyqtSignal(int, int)  # tab_index, tunnel_index

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        self.label = QLabel("Active SSH connections")
        self.label.setStyleSheet("font-weight: bold; color: #aaa;")
        self.layout.addWidget(self.label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Host", "User", "Port", "Status", "Tunnels"])
        self.tree.setRootIsDecorated(False)
        self.tree.header().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.tree.setStyleSheet(
            "QTreeWidget { background-color: #2b2b2b; color: #ccc; border: none; }"
        )
        self.tree.itemDoubleClicked.connect(self._on_double_click)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        self.layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton("Refresh")
        self.refresh_btn.clicked.connect(self.refresh_requested.emit)
        self.focus_btn = QPushButton("Focus tab")
        self.focus_btn.clicked.connect(self._focus_selected)
        self.reconnect_btn = QPushButton("Reconnect")
        self.reconnect_btn.clicked.connect(self._reconnect_selected)
        self.reconnect_all_btn = QPushButton("Reconnect all")
        self.reconnect_all_btn.clicked.connect(self.reconnect_all.emit)
        self.disconnect_btn = QPushButton("Disconnect")
        self.disconnect_btn.clicked.connect(self._disconnect_selected)
        for b in (
            self.refresh_btn,
            self.focus_btn,
            self.reconnect_btn,
            self.reconnect_all_btn,
            self.disconnect_btn,
        ):
            btn_row.addWidget(b)
        self.layout.addLayout(btn_row)

        self.update_from_tabs([])

    def update_from_tabs(self, connections: list[ActiveConnection]) -> None:
        self.tree.clear()
        if not connections:
            placeholder = QTreeWidgetItem(self.tree, ["(no active SSH sessions)", "", "", "", ""])
            placeholder.setDisabled(True)
            return
        for c in connections:
            tunnels = c.tunnels or []
            active_tunnels = [t for t in tunnels if t.get("active")]
            tunnel_text = str(len(active_tunnels)) if active_tunnels else ""
            item = QTreeWidgetItem(self.tree, [c.host, c.user, str(c.port), c.status, tunnel_text])
            item.setData(0, Qt.ItemDataRole.UserRole, c.tab_index)
            item.setData(0, Qt.ItemDataRole.UserRole + 1, tunnels)
            color = {
                "connected": QColor("#6fcf97"),
                "connecting": QColor("#f2c94c"),
                "failed": QColor("#eb5757"),
                "auth failed": QColor("#eb5757"),
                "host-key failed": QColor("#eb5757"),
                "disconnected": QColor("#9aa0a6"),
                "closed": QColor("#9aa0a6"),
            }.get(c.status, QColor("#cccccc"))
            for col in range(5):
                item.setForeground(col, color)
            item.setToolTip(3, f"SSH session is {c.status}")
            if tunnels:
                item.setToolTip(4, "\n".join(
                    f"{t.get('label')} - {'active' if t.get('active') else 'stopped'}"
                    for t in tunnels
                ))

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

    def _reconnect_selected(self) -> None:
        idx = self._selected_tab_index()
        if idx is not None:
            self.reconnect_tab.emit(idx)

    def _on_double_click(self, item: QTreeWidgetItem, _column: int) -> None:
        idx = item.data(0, Qt.ItemDataRole.UserRole)
        if idx is not None:
            self.focus_tab.emit(int(idx))

    def _show_context_menu(self, pos) -> None:
        item = self.tree.itemAt(pos)
        idx = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if idx is None:
            return
        menu = QMenu(self)
        focus = menu.addAction("Focus tab")
        focus.triggered.connect(lambda: self.focus_tab.emit(int(idx)))
        reconnect = menu.addAction("Reconnect")
        reconnect.triggered.connect(lambda: self.reconnect_tab.emit(int(idx)))
        disconnect = menu.addAction("Disconnect")
        disconnect.triggered.connect(lambda: self.disconnect_tab.emit(int(idx)))
        tunnels = item.data(0, Qt.ItemDataRole.UserRole + 1) or []
        if tunnels:
            menu.addSeparator()
            tunnel_menu = menu.addMenu("SSH tunnels")
            for tunnel in tunnels:
                label = tunnel.get("label", "Tunnel")
                active = bool(tunnel.get("active"))
                tunnel_index = int(tunnel.get("index", -1))
                action = tunnel_menu.addAction(
                    f"Stop {label}" if active else f"{label} (stopped)"
                )
                action.setEnabled(active and tunnel_index >= 0)
                action.triggered.connect(
                    lambda _checked=False, ti=tunnel_index: self.stop_tunnel.emit(int(idx), ti)
                )
        menu.exec(self.tree.mapToGlobal(pos))

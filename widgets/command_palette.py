from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QDialog, QLineEdit, QListWidget, QListWidgetItem, QVBoxLayout


@dataclass(frozen=True)
class PaletteEntry:
    label: str
    action: Callable[[], None]


class CommandPalette(QDialog):
    def __init__(self, entries: list[PaletteEntry], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Command Palette")
        self.resize(640, 420)
        self.entries = entries

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Type a command or session name...")
        self.search.textChanged.connect(self._refresh)
        self.search.returnPressed.connect(self.activate_selected)
        layout.addWidget(self.search)

        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _item: self.activate_selected())
        layout.addWidget(self.list)
        self._refresh("")

    def _refresh(self, query: str) -> None:
        self.list.clear()
        terms = [part.casefold() for part in query.split() if part.strip()]
        for entry in self.entries:
            haystack = entry.label.casefold()
            if all(term in haystack for term in terms):
                item = QListWidgetItem(entry.label)
                item.setData(Qt.ItemDataRole.UserRole, entry)
                self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)

    def activate_selected(self) -> None:
        item = self.list.currentItem()
        if item is None:
            return
        entry = item.data(Qt.ItemDataRole.UserRole)
        self.accept()
        entry.action()

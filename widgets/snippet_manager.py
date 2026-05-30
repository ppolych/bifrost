from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, 
    QPushButton, QHBoxLayout, QInputDialog, QMessageBox, QMenu
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QAction
from core.icons import named_icon

class SnippetWidget(QWidget):
    snippet_triggered = pyqtSignal(str, bool) # command, execute immediately

    def __init__(self, snippet_manager):
        super().__init__()
        self.snippet_manager = snippet_manager
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.add_btn = QPushButton(named_icon("add.svg"), "")
        self.add_btn.setToolTip("Add new snippet")
        self.add_btn.clicked.connect(self.on_add_snippet)
        
        for b in [self.add_btn]:
            b.setProperty("compact", True)
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(QSize(28, 24))
            btn_row.addWidget(b)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.refresh()

    def refresh(self):
        self.tree.clear()
        for group, items in self.snippet_manager.snippets.items():
            group_item = QTreeWidgetItem(self.tree, [group])
            group_item.setFlags(group_item.flags() | Qt.ItemFlag.ItemIsAutoTristate)
            for name, cmd in items.items():
                child = QTreeWidgetItem(group_item, [name])
                child.setData(0, Qt.ItemDataRole.UserRole, cmd)
                child.setData(0, Qt.ItemDataRole.UserRole + 1, group)
                child.setData(0, Qt.ItemDataRole.UserRole + 2, name)
                child.setToolTip(0, cmd)
        self.tree.expandAll()

    def on_item_double_clicked(self, item, column):
        cmd = item.data(0, Qt.ItemDataRole.UserRole)
        if cmd:
            self.snippet_triggered.emit(cmd, True)

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        if item is not None and item.data(0, Qt.ItemDataRole.UserRole):
            insert_act = QAction("Insert command", self)
            insert_act.triggered.connect(lambda: self._emit_item(item, False))
            menu.addAction(insert_act)
            run_act = QAction("Run command", self)
            run_act.triggered.connect(lambda: self._emit_item(item, True))
            menu.addAction(run_act)
            menu.addSeparator()
            edit_act = QAction("Edit snippet...", self)
            edit_act.triggered.connect(lambda: self._edit_snippet(item))
            menu.addAction(edit_act)
            delete_act = QAction("Delete snippet...", self)
            delete_act.triggered.connect(lambda: self._delete_snippet(item))
            menu.addAction(delete_act)
        else:
            add_act = QAction("Add snippet...", self)
            add_act.triggered.connect(self.on_add_snippet)
            menu.addAction(add_act)
        menu.exec(self.tree.mapToGlobal(pos))

    def _emit_item(self, item, execute: bool):
        cmd = item.data(0, Qt.ItemDataRole.UserRole)
        if cmd:
            self.snippet_triggered.emit(cmd, execute)

    def on_add_snippet(self):
        data = self._prompt_snippet("New Snippet")
        if data is None:
            return
        group, name, cmd = data
        try:
            self.snippet_manager.add_snippet(group, name, cmd)
        except ValueError as e:
            QMessageBox.warning(self, "Snippet", str(e))
            return
        self.refresh()

    def _edit_snippet(self, item):
        old_group = item.data(0, Qt.ItemDataRole.UserRole + 1)
        old_name = item.data(0, Qt.ItemDataRole.UserRole + 2)
        old_cmd = item.data(0, Qt.ItemDataRole.UserRole)
        data = self._prompt_snippet("Edit Snippet", old_group, old_name, old_cmd)
        if data is None:
            return
        group, name, cmd = data
        try:
            ok = self.snippet_manager.update_snippet(old_group, old_name, group, name, cmd)
        except ValueError as e:
            QMessageBox.warning(self, "Snippet", str(e))
            return
        if not ok:
            QMessageBox.warning(self, "Snippet", "Snippet was not found.")
            return
        self.refresh()

    def _delete_snippet(self, item):
        group = item.data(0, Qt.ItemDataRole.UserRole + 1)
        name = item.data(0, Qt.ItemDataRole.UserRole + 2)
        reply = QMessageBox.question(
            self,
            "Delete snippet",
            f"Delete snippet '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.snippet_manager.delete_snippet(group, name):
            self.refresh()

    def _prompt_snippet(self, title, group="", name="", command=""):
        group, ok = QInputDialog.getText(self, title, "Group:", text=group or "System")
        if not ok:
            return None
        name, ok = QInputDialog.getText(self, title, "Name:", text=name or "")
        if not ok:
            return None
        command, ok = QInputDialog.getText(self, title, "Command:", text=command or "")
        if not ok:
            return None
        return group.strip(), name.strip(), command.strip()

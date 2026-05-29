from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, 
    QPushButton, QHBoxLayout, QInputDialog, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from core.icons import named_icon

class SnippetWidget(QWidget):
    snippet_triggered = pyqtSignal(str) # the command to execute

    def __init__(self, snippet_manager):
        super().__init__()
        self.snippet_manager = snippet_manager
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
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
                child.setToolTip(0, cmd)
        self.tree.expandAll()

    def on_item_double_clicked(self, item, column):
        cmd = item.data(0, Qt.ItemDataRole.UserRole)
        if cmd:
            self.snippet_triggered.emit(cmd)

    def on_add_snippet(self):
        group, ok = QInputDialog.getText(self, "New Snippet", "Group (e.g. Docker):")
        if not ok or not group: return
        name, ok = QInputDialog.getText(self, "New Snippet", "Name:")
        if not ok or not name: return
        cmd, ok = QInputDialog.getText(self, "New Snippet", "Command:")
        if not ok or not cmd: return
        
        self.snippet_manager.add_snippet(group, name, cmd)
        self.refresh()

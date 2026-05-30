from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, 
    QPushButton, QHBoxLayout, QLabel, QMenu, QMessageBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QAction
from core.icons import named_icon
from core import docker_utils

class DockerDashboard(QWidget):
    container_shell_requested = pyqtSignal(str, list) # name, command

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Container", "Status"])
        self.tree.setColumnWidth(0, 150)
        self.tree.itemDoubleClicked.connect(self.on_item_double_clicked)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_context_menu)
        layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        self.refresh_btn = QPushButton(named_icon("refresh.svg"), "")
        self.refresh_btn.setToolTip("Refresh containers")
        self.refresh_btn.clicked.connect(self.refresh)
        
        for b in [self.refresh_btn]:
            b.setProperty("compact", True)
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(QSize(28, 24))
            btn_row.addWidget(b)
        
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(10000) # Auto-refresh every 10s

        self.refresh()

    def refresh(self):
        containers = docker_utils.list_containers()
        self.tree.clear()
        if not containers:
            QTreeWidgetItem(self.tree, ["No containers found", ""])
            return
            
        for c in containers:
            item = QTreeWidgetItem(self.tree, [c["name"], c["status"]])
            item.setToolTip(0, f"ID: {c['id']}\nImage: {c['image']}")
            item.setData(0, Qt.ItemDataRole.UserRole, c["name"])

    def on_item_double_clicked(self, item, column):
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if name:
            cmd = docker_utils.exec_shell_command(name)
            self.container_shell_requested.emit(f"Docker: {name}", cmd)

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        name = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not name:
            return
        menu = QMenu(self)
        shell = QAction("Open shell", self)
        shell.triggered.connect(lambda: self.container_shell_requested.emit(
            f"Docker: {name}", docker_utils.exec_shell_command(name)
        ))
        menu.addAction(shell)
        logs = QAction("Follow logs", self)
        logs.triggered.connect(lambda: self.container_shell_requested.emit(
            f"Docker logs: {name}", docker_utils.logs_command(name)
        ))
        menu.addAction(logs)
        menu.addSeparator()
        for action in ("start", "stop", "restart"):
            act = QAction(action.capitalize(), self)
            act.triggered.connect(lambda _checked=False, a=action: self._run_action(name, a))
            menu.addAction(act)
        menu.exec(self.tree.mapToGlobal(pos))

    def _run_action(self, name, action):
        ok, error = docker_utils.container_action(name, action)
        if not ok:
            QMessageBox.warning(self, "Docker", error or f"docker {action} failed")
            return
        self.refresh()

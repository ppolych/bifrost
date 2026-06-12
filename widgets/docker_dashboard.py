from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, 
    QPushButton, QHBoxLayout, QLabel, QMenu, QMessageBox, QTextEdit, QDialog, QDialogButtonBox
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize, QTimer
from PyQt6.QtGui import QAction
from core.icons import named_icon
from core import docker_utils

class DockerDashboard(QWidget):
    container_shell_requested = pyqtSignal(str, object) # name, command list or SSH session dict

    def __init__(self):
        super().__init__()
        self.ssh_backend = None
        self.ssh_session = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        self.context_label = QLabel("Docker: Local")
        self.context_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(self.context_label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Container", "Image", "Status"])
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

    def set_ssh_context(self, backend, session=None):
        self.ssh_backend = backend if getattr(backend, "status", "") == "connected" else None
        self.ssh_session = dict(session) if isinstance(session, dict) else None
        if self.ssh_backend is not None:
            host = getattr(self.ssh_backend.creds, "host", "")
            self.context_label.setText(f"Docker: Current SSH ({host})")
        else:
            self.context_label.setText("Docker: Local")
        self.refresh()

    def refresh(self):
        error = ""
        if self.ssh_backend is not None:
            containers, error = docker_utils.list_remote_containers(self.ssh_backend)
        else:
            containers, error = docker_utils.list_containers_with_error()
        self.tree.clear()
        if not containers:
            message = error or "Docker is not running or has no containers"
            item = QTreeWidgetItem(self.tree, ["No containers found", "", message])
            item.setDisabled(True)
            return
            
        for c in containers:
            item = QTreeWidgetItem(self.tree, [c["name"], c["image"], c["status"]])
            item.setToolTip(0, f"ID: {c['id']}\nImage: {c['image']}")
            item.setData(0, Qt.ItemDataRole.UserRole, c["name"])

    def on_item_double_clicked(self, item, column):
        name = item.data(0, Qt.ItemDataRole.UserRole)
        if name:
            self._open_shell(name)

    def _show_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        name = item.data(0, Qt.ItemDataRole.UserRole) if item is not None else None
        if not name:
            return
        menu = QMenu(self)
        shell = QAction("Open shell", self)
        shell.triggered.connect(lambda: self._open_shell(name))
        menu.addAction(shell)
        logs = QAction("Follow logs", self)
        logs.triggered.connect(lambda: self._show_logs(name))
        menu.addAction(logs)
        menu.addSeparator()
        for action in ("start", "stop", "restart"):
            act = QAction(action.capitalize(), self)
            act.triggered.connect(lambda _checked=False, a=action: self._run_action(name, a))
            menu.addAction(act)
        menu.exec(self.tree.mapToGlobal(pos))

    def _run_action(self, name, action):
        ok, error = docker_utils.container_action(name, action, backend=self.ssh_backend)
        if not ok:
            QMessageBox.warning(self, "Docker", error or f"docker {action} failed")
            return
        self.refresh()

    def _open_shell(self, name):
        if self.ssh_backend is None:
            self.container_shell_requested.emit(f"Docker: {name}", docker_utils.exec_shell_command(name))
            return
        command = docker_utils.exec_shell_remote_command(name)
        session = dict(self.ssh_session or {})
        session["name"] = f"Docker: {name}"
        session["command"] = command
        self.container_shell_requested.emit(f"Docker: {name}", session)

    def _show_logs(self, name):
        if self.ssh_backend is None:
            self.container_shell_requested.emit(f"Docker logs: {name}", docker_utils.logs_command(name))
            return
        ok, text = docker_utils.remote_logs_text(self.ssh_backend, name)
        if not ok:
            QMessageBox.warning(self, "Docker logs", text)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Docker logs: {name}")
        layout = QVBoxLayout(dialog)
        viewer = QTextEdit()
        viewer.setReadOnly(True)
        viewer.setPlainText(text)
        layout.addWidget(viewer)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.resize(780, 520)
        dialog.exec()

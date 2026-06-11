from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QToolBar,
    QWidget,
)

from core.icons import named_icon, session_icon


# (display label, method key, session-dict skeleton for icon lookup)
QUICK_CONNECT_METHODS = [
    ("SSH", "SSH", {"type": "SSH"}),
    ("Telnet", "Telnet", {"type": "Telnet"}),
    ("VNC", "VNC", {"type": "VNC"}),
    ("Local", "Local", {"type": "Local"}),
    ("WSL", "WSL", {"type": "WSL"}),
]


class MainToolBar(QToolBar):
    multi_exec_toggled = pyqtSignal(bool)
    # Now emits (method, text) — method ∈ SSH/Telnet/Local/WSL.
    quick_connect_triggered = pyqtSignal(str, str)
    split_triggered = pyqtSignal(str)  # "vert", "horiz", "quad"
    diagnostics_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__("Main Toolbar", parent)
        self.setIconSize(QSize(16, 16))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setup_actions()

    def setup_actions(self):
        self.session_act = QAction(named_icon("add.svg"), "", self)
        self.session_act.setToolTip("Create a new session")
        self.addAction(self.session_act)

        self.servers_act = QAction(named_icon("hub.svg"), "", self)
        self.servers_act.setToolTip("Show local servers")
        self.addAction(self.servers_act)

        self.addSeparator()

        self.multi_act = QAction(named_icon("bolt.svg"), "", self)
        self.multi_act.setToolTip("Broadcast input to all terminal tabs")
        self.multi_act.setCheckable(True)
        self.multi_act.toggled.connect(self.multi_exec_toggled.emit)
        self.addAction(self.multi_act)

        self.addSeparator()

        self.split_vert = QAction(named_icon("terminal.svg"), "", self)
        self.split_vert.setToolTip("Split the current terminal vertically")
        self.split_vert.triggered.connect(lambda: self.split_triggered.emit("vert"))
        self.addAction(self.split_vert)

        self.split_horiz = QAction(named_icon("terminal.svg"), "", self)
        self.split_horiz.setToolTip("Split the current terminal horizontally")
        self.split_horiz.triggered.connect(lambda: self.split_triggered.emit("horiz"))
        self.addAction(self.split_horiz)

        self.split_quad = QAction(named_icon("terminal.svg"), "", self)
        self.split_quad.setToolTip("Split the current terminal into four panes")
        self.split_quad.triggered.connect(lambda: self.split_triggered.emit("quad"))
        self.addAction(self.split_quad)

        self.addSeparator()

        # ---- Quick Connect with method picker ----
        qc_widget = QWidget()
        qc_layout = QHBoxLayout(qc_widget)
        qc_layout.setContentsMargins(4, 0, 4, 0)
        qc_layout.setSpacing(4)

        qc_label = QLabel("Quick Connect:")
        qc_label.setStyleSheet("color: #aaa; font-size: 10px;")
        qc_layout.addWidget(qc_label)

        self.qc_method = QComboBox()
        for display, key, skeleton in QUICK_CONNECT_METHODS:
            self.qc_method.addItem(session_icon(skeleton), display, key)
        self.qc_method.setStyleSheet(
            "background: #2b2b2b; color: #ccc; border: 1px solid #555; padding: 2px;"
        )
        self.qc_method.currentIndexChanged.connect(self._update_placeholder)
        qc_layout.addWidget(self.qc_method)

        self.qc_input = QLineEdit()
        self.qc_input.setFixedWidth(200)
        self.qc_input.setStyleSheet(
            "background: #2b2b2b; color: #ccc; border: 1px solid #555;"
        )
        self.qc_input.returnPressed.connect(self.on_qc_enter)
        qc_layout.addWidget(self.qc_input)
        self._update_placeholder()

        self.addWidget(qc_widget)

        # Wake-on-LAN toolbar button — opens a small ad-hoc dialog.
        self.wol_act = QAction(named_icon("power_settings_new.svg"), "", self)
        self.wol_act.setToolTip("Send a Wake-on-LAN magic packet")
        self.addAction(self.wol_act)

        self.addSeparator()

        self.diagnostics_act = QAction(named_icon("build.svg"), "", self)
        self.diagnostics_act.setToolTip("Show runtime diagnostics")
        self.diagnostics_act.triggered.connect(self.diagnostics_requested.emit)
        self.addAction(self.diagnostics_act)

        self.settings_act = QAction(named_icon("settings.svg"), "", self)
        self.settings_act.setToolTip("Open settings")
        self.addAction(self.settings_act)

    def _update_placeholder(self):
        method = self.qc_method.currentData()
        placeholders = {
            "SSH": "user@host  or  user@host:port",
            "Telnet": "host  or  host:port",
            "VNC": "host  or  host:port (default 5900)",
            "Local": "/bin/bash  (path to shell)",
            "WSL": "Distro name (blank = default)",
        }
        self.qc_input.setPlaceholderText(placeholders.get(method, ""))

    def on_qc_enter(self):
        text = self.qc_input.text().strip()
        if not text and self.qc_method.currentData() not in ("WSL", "Local"):
            return
        self.quick_connect_triggered.emit(self.qc_method.currentData(), text)
        self.qc_input.clear()

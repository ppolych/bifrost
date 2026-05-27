from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget,
)

from core import wsl


class SessionDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Session Settings")
        self.resize(700, 500)

        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        # ---- Connection tab ----
        self.conn_tab = QWidget()
        self.conn_layout = QVBoxLayout(self.conn_tab)
        self.proto_tabs = QTabWidget()
        self.conn_layout.addWidget(self.proto_tabs)

        # SSH sub-tab
        self.ssh_tab = QWidget()
        self.ssh_layout = QFormLayout(self.ssh_tab)
        self.host_input = QLineEdit("127.0.0.1")
        self.user_input = QLineEdit("root")
        self.port_input = QLineEdit("22")
        self.ssh_layout.addRow("Remote Host:", self.host_input)
        self.ssh_layout.addRow("Username:", self.user_input)
        self.ssh_layout.addRow("Port:", self.port_input)

        self.auth_method = QComboBox()
        self.auth_method.addItems(["SSH agent", "Private key", "Password"])
        self.auth_method.currentTextChanged.connect(self._on_auth_changed)
        self.ssh_layout.addRow("Authentication:", self.auth_method)

        # Key picker row (private key)
        self.key_row = QWidget()
        key_row_layout = QHBoxLayout(self.key_row)
        key_row_layout.setContentsMargins(0, 0, 0, 0)
        self.key_path_input = QLineEdit()
        self.key_path_input.setPlaceholderText("~/.ssh/id_ed25519")
        self.key_browse_btn = QPushButton("Browse…")
        self.key_browse_btn.clicked.connect(self._pick_key_file)
        key_row_layout.addWidget(self.key_path_input)
        key_row_layout.addWidget(self.key_browse_btn)
        self.ssh_layout.addRow("Private key:", self.key_row)

        self.passphrase_note = QLabel(
            "Passphrase (if any) is prompted at connect time and never stored."
        )
        self.passphrase_note.setStyleSheet("color: #888; font-size: 10px;")
        self.ssh_layout.addRow(self.passphrase_note)

        self.password_note = QLabel(
            "Password is prompted at connect time and never stored on disk."
        )
        self.password_note.setStyleSheet("color: #888; font-size: 10px;")
        self.ssh_layout.addRow(self.password_note)

        # Wake-on-LAN: optional MAC + broadcast address
        self.mac_input = QLineEdit()
        self.mac_input.setPlaceholderText("AA:BB:CC:11:22:33  (optional, enables Wake on LAN)")
        self.ssh_layout.addRow("MAC address:", self.mac_input)
        self.broadcast_input = QLineEdit()
        self.broadcast_input.setPlaceholderText("255.255.255.255")
        self.ssh_layout.addRow("WoL broadcast:", self.broadcast_input)

        self.proto_tabs.addTab(self.ssh_tab, "SSH")

        # RDP sub-tab (placeholder, backend not implemented)
        self.rdp_tab = QWidget()
        self.rdp_layout = QFormLayout(self.rdp_tab)
        self.rdp_layout.addRow("Host:", QLineEdit())
        self.proto_tabs.addTab(self.rdp_tab, "RDP")

        # WSL sub-tab
        self.wsl_tab = QWidget()
        self.wsl_layout = QFormLayout(self.wsl_tab)
        self.wsl_distro = QComboBox()
        distros = wsl.list_distros()
        if distros:
            self.wsl_distro.addItems(distros)
        else:
            self.wsl_distro.addItem("(default)")
            if not wsl.is_wsl_available():
                self.wsl_distro.setEnabled(False)
                self.wsl_layout.addRow(QLabel("WSL is only available on Windows."))
        self.wsl_layout.addRow("Distro:", self.wsl_distro)
        self.proto_tabs.addTab(self.wsl_tab, "WSL")

        self.tabs.addTab(self.conn_tab, "Connection")

        # ---- Terminal Settings tab ----
        self.term_tab = QWidget()
        self.term_layout = QFormLayout(self.term_tab)

        self.font_override_cb = QCheckBox("Override global font")
        self.font_input = QLineEdit("DejaVu Sans Mono, 10")
        self.term_layout.addRow(self.font_override_cb)
        self.term_layout.addRow("Font:", self.font_input)

        self.color_scheme = QComboBox()
        self.color_scheme.addItems(["Default", "Solarized", "Monokai", "Black on White"])
        self.term_layout.addRow("Color Scheme:", self.color_scheme)

        self.tabs.addTab(self.term_tab, "Terminal Settings")

        # ---- Buttons ----
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        self.layout.addWidget(self.buttons)

        self._on_auth_changed(self.auth_method.currentText())

    def _pick_key_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", "", "All Files (*)")
        if path:
            self.key_path_input.setText(path)

    def _on_auth_changed(self, label: str):
        is_key = label == "Private key"
        is_pwd = label == "Password"
        self.key_row.setEnabled(is_key)
        self.passphrase_note.setVisible(is_key)
        self.password_note.setVisible(is_pwd)

    def _auth_value(self) -> str:
        return {
            "SSH agent": "agent",
            "Private key": "key",
            "Password": "password",
        }.get(self.auth_method.currentText(), "agent")

    def get_data(self):
        proto = self.proto_tabs.tabText(self.proto_tabs.currentIndex())
        overrides = {
            "font": self.font_input.text() if self.font_override_cb.isChecked() else None,
            "scheme": self.color_scheme.currentText(),
        }
        if proto == "WSL":
            distro = self.wsl_distro.currentText()
            distro_label = "" if distro == "(default)" else distro
            return {
                "name": f"WSL: {distro_label or 'default'}",
                "type": "WSL",
                "distro": distro_label,
                "overrides": overrides,
            }
        if proto == "SSH":
            return {
                "name": f"{self.user_input.text()}@{self.host_input.text()}",
                "type": "SSH",
                "host": self.host_input.text(),
                "user": self.user_input.text(),
                "port": self.port_input.text(),
                "auth": self._auth_value(),
                "key_path": self.key_path_input.text().strip() or None,
                "mac": self.mac_input.text().strip() or None,
                "wol_broadcast": self.broadcast_input.text().strip() or None,
                "overrides": overrides,
            }
        return {
            "name": f"{self.host_input.text()} ({self.user_input.text()})",
            "type": proto,
            "host": self.host_input.text(),
            "user": self.user_input.text(),
            "port": self.port_input.text(),
            "overrides": overrides,
        }

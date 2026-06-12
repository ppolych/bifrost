from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox, QFileDialog,
    QFormLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox,
    QTabWidget, QTextEdit, QVBoxLayout, QWidget,
)

from core import wsl
from core.color_schemes import scheme_names


class SessionDialog(QDialog):
    def __init__(self, parent=None, session: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Session Settings")
        self.resize(700, 500)

        self.layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.layout.addWidget(self.tabs)

        # ---- Connection tab ----
        self.conn_tab = QWidget()
        self.conn_layout = QVBoxLayout(self.conn_tab)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Leave blank to generate from connection details")
        self.conn_layout.addWidget(QLabel("Session name"))
        self.conn_layout.addWidget(self.name_input)
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

        self.command_input = QLineEdit()
        self.command_input.setPlaceholderText("Optional command sent after SSH shell opens")
        self.ssh_layout.addRow("Startup command:", self.command_input)

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

        self.cert_row = QWidget()
        cert_row_layout = QHBoxLayout(self.cert_row)
        cert_row_layout.setContentsMargins(0, 0, 0, 0)
        self.cert_path_input = QLineEdit()
        self.cert_path_input.setPlaceholderText("~/.ssh/id_ed25519-cert.pub")
        self.cert_browse_btn = QPushButton("Browse...")
        self.cert_browse_btn.clicked.connect(self._pick_cert_file)
        cert_row_layout.addWidget(self.cert_path_input)
        cert_row_layout.addWidget(self.cert_browse_btn)
        self.ssh_layout.addRow("Certificate:", self.cert_row)

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

        self.proto_tabs.addTab(self.ssh_tab, "SSH")

        # Advanced SSH settings tab
        self.advanced_ssh_tab = QWidget()
        self.advanced_ssh_layout = QFormLayout(self.advanced_ssh_tab)
        self.connect_timeout_sb = QDoubleSpinBox()
        self.connect_timeout_sb.setRange(1.0, 120.0)
        self.connect_timeout_sb.setDecimals(1)
        self.connect_timeout_sb.setSingleStep(1.0)
        self.connect_timeout_sb.setValue(15.0)
        self.advanced_ssh_layout.addRow("Connect timeout (s):", self.connect_timeout_sb)

        self.agent_forwarding_cb = QCheckBox("Forward SSH agent")
        self.advanced_ssh_layout.addRow(self.agent_forwarding_cb)

        self.keepalive_sb = QSpinBox()
        self.keepalive_sb.setRange(0, 600)
        self.keepalive_sb.setSpecialValueText("Use global")
        self.keepalive_sb.setSuffix(" s")
        self.keepalive_sb.setValue(30)
        self.advanced_ssh_layout.addRow("Keepalive interval:", self.keepalive_sb)

        self.tcp_keepalive_cb = QCheckBox("Enable TCP keepalive")
        self.tcp_keepalive_cb.setChecked(True)
        self.advanced_ssh_layout.addRow(self.tcp_keepalive_cb)

        self.known_hosts_input = QLineEdit()
        self.known_hosts_input.setPlaceholderText("Use global known_hosts file")
        known_browse = QPushButton("Browse...")
        known_browse.clicked.connect(self._pick_known_hosts)
        known_row = QHBoxLayout()
        known_row.addWidget(self.known_hosts_input)
        known_row.addWidget(known_browse)
        self.advanced_ssh_layout.addRow("Known hosts file:", known_row)

        self.proxy_jump_input = QLineEdit()
        self.proxy_jump_input.setPlaceholderText("bastion.example.com or user@bastion.example.com:22")
        self.advanced_ssh_layout.addRow("ProxyJump:", self.proxy_jump_input)

        self.proxy_command_input = QLineEdit()
        self.proxy_command_input.setPlaceholderText("ssh -W %h:%p bastion.example.com")
        self.advanced_ssh_layout.addRow("ProxyCommand:", self.proxy_command_input)

        self.tunnels_input = QTextEdit()
        self.tunnels_input.setPlaceholderText(
            "One tunnel per line, e.g.\n"
            "L 127.0.0.1:5432 db.internal:5432\n"
            "R 0.0.0.0:8080 127.0.0.1:8080\n"
            "D 127.0.0.1:1080"
        )
        self.tunnels_input.setFixedHeight(90)
        self.advanced_ssh_layout.addRow("SSH tunnels:", self.tunnels_input)
        self.tabs.addTab(self.advanced_ssh_tab, "Advanced SSH Settings")

        # Network settings tab
        self.network_tab = QWidget()
        self.network_layout = QFormLayout(self.network_tab)
        self.mac_input = QLineEdit()
        self.mac_input.setPlaceholderText("AA:BB:CC:11:22:33  (optional, enables Wake on LAN)")
        self.network_layout.addRow("MAC address:", self.mac_input)
        self.broadcast_input = QLineEdit()
        self.broadcast_input.setPlaceholderText("255.255.255.255")
        self.network_layout.addRow("WoL broadcast:", self.broadcast_input)
        self.tabs.addTab(self.network_tab, "Network Settings")

        # Telnet sub-tab
        self.telnet_tab = QWidget()
        self.telnet_layout = QFormLayout(self.telnet_tab)
        self.telnet_host_input = QLineEdit("127.0.0.1")
        self.telnet_port_input = QLineEdit("23")
        self.telnet_layout.addRow("Host:", self.telnet_host_input)
        self.telnet_layout.addRow("Port:", self.telnet_port_input)
        self.proto_tabs.addTab(self.telnet_tab, "Telnet")

        # Serial sub-tab
        self.serial_tab = QWidget()
        self.serial_layout = QFormLayout(self.serial_tab)
        self.serial_device_input = QLineEdit()
        self.serial_device_input.setPlaceholderText("/dev/ttyUSB0 or COM3")
        self.serial_baud_combo = QComboBox()
        self.serial_baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
        self.serial_baud_combo.setCurrentText("115200")
        self.serial_layout.addRow("Device:", self.serial_device_input)
        self.serial_layout.addRow("Baud rate:", self.serial_baud_combo)
        self.serial_note = QLabel("Requires pyserial (`pip install pyserial`).")
        self.serial_note.setStyleSheet("color: #888; font-size: 10px;")
        self.serial_layout.addRow(self.serial_note)
        self.proto_tabs.addTab(self.serial_tab, "Serial")

        # VNC sub-tab
        self.vnc_tab = QWidget()
        self.vnc_layout = QFormLayout(self.vnc_tab)
        self.vnc_host_input = QLineEdit("127.0.0.1")
        self.vnc_port_input = QLineEdit("5900")
        self.vnc_layout.addRow("Host:", self.vnc_host_input)
        self.vnc_layout.addRow("Port:", self.vnc_port_input)
        self.vnc_note = QLabel("Password (if any) is prompted at connect time and never stored.")
        self.vnc_note.setStyleSheet("color: #888; font-size: 10px;")
        self.vnc_layout.addRow(self.vnc_note)
        self.proto_tabs.addTab(self.vnc_tab, "VNC")

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
        self.color_scheme.addItems(scheme_names())
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

        if session is not None:
            self._load_session(session)
        self._on_auth_changed(self.auth_method.currentText())

    def _pick_key_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", "", "All Files (*)")
        if path:
            self.key_path_input.setText(path)

    def _pick_known_hosts(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select known_hosts file", self.known_hosts_input.text(), "All Files (*)"
        )
        if path:
            self.known_hosts_input.setText(path)

    def _pick_cert_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SSH certificate", "", "Public Certificates (*.pub);;All Files (*)"
        )
        if path:
            self.cert_path_input.setText(path)

    def set_current_section(self, section: str) -> None:
        section_map = {
            "connection": self.conn_tab,
            "advanced_ssh": self.advanced_ssh_tab,
            "terminal": self.term_tab,
            "network": self.network_tab,
        }
        page = section_map.get(section, self.conn_tab)
        idx = self.tabs.indexOf(page)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    def _on_auth_changed(self, label: str):
        is_key = label == "Private key"
        is_pwd = label == "Password"
        self.key_row.setEnabled(is_key)
        self.cert_row.setEnabled(is_key)
        self.passphrase_note.setVisible(is_key)
        self.password_note.setVisible(is_pwd)

    def _auth_value(self) -> str:
        return {
            "SSH agent": "agent",
            "Private key": "key",
            "Password": "password",
        }.get(self.auth_method.currentText(), "agent")

    def _set_auth_value(self, value: str) -> None:
        labels = {
            "agent": "SSH agent",
            "key": "Private key",
            "password": "Password",
        }
        self.auth_method.setCurrentText(labels.get(value, "SSH agent"))

    def _load_session(self, session: dict) -> None:
        self.name_input.setText(session.get("name", ""))
        proto = session.get("type", "SSH")
        tab = {
            "SSH": self.ssh_tab,
            "Telnet": self.telnet_tab,
            "Serial": self.serial_tab,
            "VNC": self.vnc_tab,
            "RDP": self.rdp_tab,
            "WSL": self.wsl_tab,
        }.get(proto, self.ssh_tab)
        idx = self.proto_tabs.indexOf(tab)
        if idx >= 0:
            self.proto_tabs.setCurrentIndex(idx)
        self.host_input.setText(session.get("host", "127.0.0.1"))
        self.user_input.setText(session.get("user", "root"))
        self.port_input.setText(str(session.get("port", "22") or "22"))
        self._set_auth_value(session.get("auth", "agent"))
        self.key_path_input.setText(session.get("key_path") or "")
        self.cert_path_input.setText(session.get("certificate_path") or "")
        self.command_input.setText(session.get("command") or "")
        self.mac_input.setText(session.get("mac") or "")
        self.broadcast_input.setText(session.get("wol_broadcast") or "")
        if "connect_timeout" in session:
            self.connect_timeout_sb.setValue(float(session.get("connect_timeout") or 15))
        self.agent_forwarding_cb.setChecked(bool(session.get("agent_forwarding", False)))
        self.keepalive_sb.setValue(int(session.get("keepalive_interval", 30) or 0))
        self.tcp_keepalive_cb.setChecked(bool(session.get("tcp_keepalive", True)))
        self.known_hosts_input.setText(session.get("known_hosts_file") or "")
        self.tunnels_input.setPlainText("\n".join(session.get("tunnels") or []))
        self.proxy_jump_input.setText(session.get("proxy_jump") or "")
        self.proxy_command_input.setText(session.get("proxy_command") or "")
        if proto == "Telnet":
            self.telnet_host_input.setText(session.get("host", "127.0.0.1"))
            self.telnet_port_input.setText(str(session.get("port", "23") or "23"))
        if proto == "Serial":
            self.serial_device_input.setText(session.get("device") or "")
            self.serial_baud_combo.setCurrentText(str(session.get("baudrate", "115200") or "115200"))
        if proto == "VNC":
            self.vnc_host_input.setText(session.get("host", "127.0.0.1"))
            self.vnc_port_input.setText(str(session.get("port", "5900") or "5900"))
        if proto == "WSL":
            distro = session.get("distro") or "(default)"
            idx = self.wsl_distro.findText(distro)
            if idx >= 0:
                self.wsl_distro.setCurrentIndex(idx)
        overrides = session.get("overrides") or {}
        if overrides.get("font"):
            self.font_override_cb.setChecked(True)
            self.font_input.setText(overrides["font"])
        if overrides.get("scheme"):
            self.color_scheme.setCurrentText(overrides["scheme"])

    def get_data(self):
        proto = self.proto_tabs.tabText(self.proto_tabs.currentIndex())
        overrides = {
            "font": self.font_input.text() if self.font_override_cb.isChecked() else None,
            "scheme": self.color_scheme.currentText(),
        }
        if proto == "WSL":
            distro = self.wsl_distro.currentText()
            distro_label = "" if distro == "(default)" else distro
            name = self.name_input.text().strip() or f"WSL: {distro_label or 'default'}"
            return {
                "name": name,
                "type": "WSL",
                "distro": distro_label,
                "overrides": overrides,
            }
        if proto == "Telnet":
            host = self.telnet_host_input.text().strip() or "127.0.0.1"
            port = self.telnet_port_input.text().strip() or "23"
            name = self.name_input.text().strip() or f"telnet {host}:{port}"
            return {
                "name": name,
                "type": "Telnet",
                "host": host,
                "port": port,
                "overrides": overrides,
            }
        if proto == "VNC":
            host = self.vnc_host_input.text().strip() or "127.0.0.1"
            port = self.vnc_port_input.text().strip() or "5900"
            name = self.name_input.text().strip() or f"vnc {host}:{port}"
            return {
                "name": name,
                "type": "VNC",
                "host": host,
                "port": port,
                "overrides": overrides,
            }
        if proto == "Serial":
            device = self.serial_device_input.text().strip()
            baud = self.serial_baud_combo.currentText()
            name = self.name_input.text().strip() or f"{device or 'serial'} @{baud}"
            return {
                "name": name,
                "type": "Serial",
                "device": device,
                "baudrate": baud,
                "overrides": overrides,
            }
        if proto == "SSH":
            generated_name = f"{self.user_input.text()}@{self.host_input.text()}"
            name = self.name_input.text().strip() or generated_name
            return {
                "name": name,
                "type": "SSH",
                "host": self.host_input.text(),
                "user": self.user_input.text(),
                "port": self.port_input.text(),
                "auth": self._auth_value(),
                "key_path": self.key_path_input.text().strip() or None,
                "certificate_path": self.cert_path_input.text().strip() or None,
                "command": self.command_input.text().strip() or None,
                "connect_timeout": self.connect_timeout_sb.value(),
                "agent_forwarding": self.agent_forwarding_cb.isChecked(),
                "keepalive_interval": self.keepalive_sb.value(),
                "tcp_keepalive": self.tcp_keepalive_cb.isChecked(),
                "known_hosts_file": self.known_hosts_input.text().strip() or None,
                "proxy_jump": self.proxy_jump_input.text().strip() or None,
                "proxy_command": self.proxy_command_input.text().strip() or None,
                "tunnels": [
                    line.strip()
                    for line in self.tunnels_input.toPlainText().splitlines()
                    if line.strip()
                ],
                "mac": self.mac_input.text().strip() or None,
                "wol_broadcast": self.broadcast_input.text().strip() or None,
                "overrides": overrides,
            }
        name = self.name_input.text().strip() or f"{self.host_input.text()} ({self.user_input.text()})"
        return {
            "name": name,
            "type": proto,
            "host": self.host_input.text(),
            "user": self.user_input.text(),
            "port": self.port_input.text(),
            "overrides": overrides,
        }

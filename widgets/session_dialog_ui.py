from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDialogButtonBox, QDoubleSpinBox, QFormLayout,
    QHBoxLayout, QLabel, QLineEdit, QPushButton, QSpinBox, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget,
)

from core import wsl
from core.color_schemes import scheme_names
from widgets.tmux_commands import TMUX_PRESETS


def build_session_dialog_ui(dialog) -> None:
    dialog.layout = QVBoxLayout(dialog)
    dialog.tabs = QTabWidget()
    dialog.layout.addWidget(dialog.tabs)

    build_connection_tab(dialog)
    build_advanced_ssh_tab(dialog)
    build_network_tab(dialog)
    build_protocol_tabs(dialog)
    build_terminal_tab(dialog)
    build_buttons(dialog)


def build_connection_tab(dialog) -> None:
    dialog.conn_tab = QWidget()
    dialog.conn_layout = QVBoxLayout(dialog.conn_tab)
    dialog.name_input = QLineEdit()
    dialog.name_input.setPlaceholderText("Leave blank to generate from connection details")
    dialog.conn_layout.addWidget(QLabel("Session name"))
    dialog.conn_layout.addWidget(dialog.name_input)
    dialog.proto_tabs = QTabWidget()
    dialog.conn_layout.addWidget(dialog.proto_tabs)

    dialog.ssh_tab = QWidget()
    dialog.ssh_layout = QFormLayout(dialog.ssh_tab)
    dialog.host_input = QLineEdit("127.0.0.1")
    dialog.user_input = QLineEdit("root")
    dialog.port_input = QLineEdit("22")
    dialog.ssh_layout.addRow("Remote Host:", dialog.host_input)
    dialog.ssh_layout.addRow("Username:", dialog.user_input)
    dialog.ssh_layout.addRow("Port:", dialog.port_input)

    dialog.command_input = QLineEdit()
    dialog.command_input.setPlaceholderText("Optional command sent after SSH shell opens")
    command_row = QHBoxLayout()
    command_row.addWidget(dialog.command_input, 1)
    dialog.tmux_preset = QComboBox()
    dialog.tmux_preset.addItem("tmux preset...", "")
    for label, preset in TMUX_PRESETS.items():
        dialog.tmux_preset.addItem(label, preset)
    dialog.tmux_preset.currentIndexChanged.connect(dialog._apply_tmux_preset)
    command_row.addWidget(dialog.tmux_preset)
    dialog.ssh_layout.addRow("Startup command:", command_row)

    dialog.auth_method = QComboBox()
    dialog.auth_method.addItems(["SSH agent", "Private key", "Password"])
    dialog.auth_method.currentTextChanged.connect(dialog._on_auth_changed)
    dialog.ssh_layout.addRow("Authentication:", dialog.auth_method)

    dialog.key_row = QWidget()
    key_row_layout = QHBoxLayout(dialog.key_row)
    key_row_layout.setContentsMargins(0, 0, 0, 0)
    dialog.key_path_input = QLineEdit()
    dialog.key_path_input.setPlaceholderText("~/.ssh/id_ed25519")
    dialog.key_browse_btn = QPushButton("Browse...")
    dialog.key_browse_btn.clicked.connect(dialog._pick_key_file)
    key_row_layout.addWidget(dialog.key_path_input)
    key_row_layout.addWidget(dialog.key_browse_btn)
    dialog.ssh_layout.addRow("Private key:", dialog.key_row)

    dialog.cert_row = QWidget()
    cert_row_layout = QHBoxLayout(dialog.cert_row)
    cert_row_layout.setContentsMargins(0, 0, 0, 0)
    dialog.cert_path_input = QLineEdit()
    dialog.cert_path_input.setPlaceholderText("~/.ssh/id_ed25519-cert.pub")
    dialog.cert_browse_btn = QPushButton("Browse...")
    dialog.cert_browse_btn.clicked.connect(dialog._pick_cert_file)
    cert_row_layout.addWidget(dialog.cert_path_input)
    cert_row_layout.addWidget(dialog.cert_browse_btn)
    dialog.ssh_layout.addRow("Certificate:", dialog.cert_row)

    dialog.passphrase_note = QLabel(
        "Passphrase (if any) is prompted at connect time and never stored."
    )
    dialog.passphrase_note.setStyleSheet("font-size: 10px;")
    dialog.ssh_layout.addRow(dialog.passphrase_note)

    dialog.password_note = QLabel(
        "Password is prompted at connect time and never stored on disk."
    )
    dialog.password_note.setStyleSheet("font-size: 10px;")
    dialog.ssh_layout.addRow(dialog.password_note)
    dialog.proto_tabs.addTab(dialog.ssh_tab, "SSH")


def build_advanced_ssh_tab(dialog) -> None:
    dialog.advanced_ssh_tab = QWidget()
    dialog.advanced_ssh_layout = QFormLayout(dialog.advanced_ssh_tab)
    dialog.connect_timeout_sb = QDoubleSpinBox()
    dialog.connect_timeout_sb.setRange(1.0, 120.0)
    dialog.connect_timeout_sb.setDecimals(1)
    dialog.connect_timeout_sb.setSingleStep(1.0)
    dialog.connect_timeout_sb.setValue(15.0)
    dialog.advanced_ssh_layout.addRow("Connect timeout (s):", dialog.connect_timeout_sb)

    dialog.agent_forwarding_cb = QCheckBox("Forward SSH agent")
    dialog.advanced_ssh_layout.addRow(dialog.agent_forwarding_cb)

    dialog.keepalive_sb = QSpinBox()
    dialog.keepalive_sb.setRange(0, 600)
    dialog.keepalive_sb.setSpecialValueText("Use global")
    dialog.keepalive_sb.setSuffix(" s")
    dialog.keepalive_sb.setValue(30)
    dialog.advanced_ssh_layout.addRow("Keepalive interval:", dialog.keepalive_sb)

    dialog.tcp_keepalive_cb = QCheckBox("Enable TCP keepalive")
    dialog.tcp_keepalive_cb.setChecked(True)
    dialog.advanced_ssh_layout.addRow(dialog.tcp_keepalive_cb)

    dialog.known_hosts_input = QLineEdit()
    dialog.known_hosts_input.setPlaceholderText("Use global known_hosts file")
    known_browse = QPushButton("Browse...")
    known_browse.clicked.connect(dialog._pick_known_hosts)
    known_row = QHBoxLayout()
    known_row.addWidget(dialog.known_hosts_input)
    known_row.addWidget(known_browse)
    dialog.advanced_ssh_layout.addRow("Known hosts file:", known_row)

    dialog.proxy_jump_input = QLineEdit()
    dialog.proxy_jump_input.setPlaceholderText("bastion.example.com or user@bastion.example.com:22")
    dialog.advanced_ssh_layout.addRow("ProxyJump:", dialog.proxy_jump_input)

    dialog.proxy_command_input = QLineEdit()
    dialog.proxy_command_input.setPlaceholderText("ssh -W %h:%p bastion.example.com")
    dialog.advanced_ssh_layout.addRow("ProxyCommand:", dialog.proxy_command_input)

    dialog.tunnels_input = QTextEdit()
    dialog.tunnels_input.setPlaceholderText(
        "One tunnel per line, e.g.\n"
        "L 127.0.0.1:5432 db.internal:5432\n"
        "R 0.0.0.0:8080 127.0.0.1:8080\n"
        "D 127.0.0.1:1080"
    )
    dialog.tunnels_input.setFixedHeight(90)
    dialog.advanced_ssh_layout.addRow("SSH tunnels:", dialog.tunnels_input)
    dialog.tabs.addTab(dialog.advanced_ssh_tab, "Advanced SSH Settings")


def build_network_tab(dialog) -> None:
    dialog.network_tab = QWidget()
    dialog.network_layout = QFormLayout(dialog.network_tab)
    dialog.mac_input = QLineEdit()
    dialog.mac_input.setPlaceholderText("AA:BB:CC:11:22:33  (optional, enables Wake on LAN)")
    dialog.network_layout.addRow("MAC address:", dialog.mac_input)
    dialog.broadcast_input = QLineEdit()
    dialog.broadcast_input.setPlaceholderText("255.255.255.255")
    dialog.network_layout.addRow("WoL broadcast:", dialog.broadcast_input)
    dialog.tabs.addTab(dialog.network_tab, "Network Settings")


def build_protocol_tabs(dialog) -> None:
    build_telnet_tab(dialog)
    build_serial_tab(dialog)
    build_vnc_tab(dialog)
    build_rdp_tab(dialog)
    build_wsl_tab(dialog)
    dialog.tabs.addTab(dialog.conn_tab, "Connection")


def build_telnet_tab(dialog) -> None:
    dialog.telnet_tab = QWidget()
    dialog.telnet_layout = QFormLayout(dialog.telnet_tab)
    dialog.telnet_host_input = QLineEdit("127.0.0.1")
    dialog.telnet_port_input = QLineEdit("23")
    dialog.telnet_layout.addRow("Host:", dialog.telnet_host_input)
    dialog.telnet_layout.addRow("Port:", dialog.telnet_port_input)
    dialog.proto_tabs.addTab(dialog.telnet_tab, "Telnet")


def build_serial_tab(dialog) -> None:
    dialog.serial_tab = QWidget()
    dialog.serial_layout = QFormLayout(dialog.serial_tab)
    dialog.serial_device_input = QLineEdit()
    dialog.serial_device_input.setPlaceholderText("/dev/ttyUSB0 or COM3")
    dialog.serial_baud_combo = QComboBox()
    dialog.serial_baud_combo.addItems(["9600", "19200", "38400", "57600", "115200"])
    dialog.serial_baud_combo.setCurrentText("115200")
    dialog.serial_layout.addRow("Device:", dialog.serial_device_input)
    dialog.serial_layout.addRow("Baud rate:", dialog.serial_baud_combo)
    dialog.serial_note = QLabel("Requires pyserial (`pip install pyserial`).")
    dialog.serial_note.setStyleSheet("font-size: 10px;")
    dialog.serial_layout.addRow(dialog.serial_note)
    dialog.proto_tabs.addTab(dialog.serial_tab, "Serial")


def build_vnc_tab(dialog) -> None:
    dialog.vnc_tab = QWidget()
    dialog.vnc_layout = QFormLayout(dialog.vnc_tab)
    dialog.vnc_host_input = QLineEdit("127.0.0.1")
    dialog.vnc_port_input = QLineEdit("5900")
    dialog.vnc_layout.addRow("Host:", dialog.vnc_host_input)
    dialog.vnc_layout.addRow("Port:", dialog.vnc_port_input)
    dialog.vnc_note = QLabel("Password (if any) is prompted at connect time and never stored.")
    dialog.vnc_note.setStyleSheet("font-size: 10px;")
    dialog.vnc_layout.addRow(dialog.vnc_note)
    dialog.proto_tabs.addTab(dialog.vnc_tab, "VNC")


def build_rdp_tab(dialog) -> None:
    dialog.rdp_tab = QWidget()
    dialog.rdp_layout = QFormLayout(dialog.rdp_tab)
    dialog.rdp_host_input = QLineEdit("127.0.0.1")
    dialog.rdp_port_input = QLineEdit("3389")
    dialog.rdp_layout.addRow("Host:", dialog.rdp_host_input)
    dialog.rdp_layout.addRow("Port:", dialog.rdp_port_input)
    dialog.proto_tabs.addTab(dialog.rdp_tab, "RDP")


def build_wsl_tab(dialog) -> None:
    dialog.wsl_tab = QWidget()
    dialog.wsl_layout = QFormLayout(dialog.wsl_tab)
    dialog.wsl_distro = QComboBox()
    distros = wsl.list_distros()
    if distros:
        dialog.wsl_distro.addItems(distros)
    else:
        dialog.wsl_distro.addItem("(default)")
        if not wsl.is_wsl_available():
            dialog.wsl_distro.setEnabled(False)
            dialog.wsl_layout.addRow(QLabel("WSL is only available on Windows."))
    dialog.wsl_layout.addRow("Distro:", dialog.wsl_distro)
    dialog.proto_tabs.addTab(dialog.wsl_tab, "WSL")


def build_terminal_tab(dialog) -> None:
    dialog.term_tab = QWidget()
    dialog.term_layout = QFormLayout(dialog.term_tab)
    dialog.font_override_cb = QCheckBox("Override global font")
    dialog.font_input = QLineEdit("DejaVu Sans Mono, 10")
    dialog.term_layout.addRow(dialog.font_override_cb)
    dialog.term_layout.addRow("Font:", dialog.font_input)

    dialog.color_scheme = QComboBox()
    dialog.color_scheme.addItems(scheme_names())
    dialog.term_layout.addRow("Color Scheme:", dialog.color_scheme)
    dialog.tabs.addTab(dialog.term_tab, "Terminal Settings")


def build_buttons(dialog) -> None:
    dialog.buttons = QDialogButtonBox(
        QDialogButtonBox.StandardButton.Ok |
        QDialogButtonBox.StandardButton.Cancel
    )
    dialog.buttons.accepted.connect(dialog.accept)
    dialog.buttons.rejected.connect(dialog.reject)
    dialog.layout.addWidget(dialog.buttons)

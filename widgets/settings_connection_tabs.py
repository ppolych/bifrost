from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QPushButton, QSpinBox, QWidget,
)


SSH_AUTH_MODES = [("SSH agent", "agent"), ("Private key", "key"), ("Password", "password")]
CREDENTIAL_POLICIES = [("Ask each time", "ask"), ("Never save", "never")]
CREDENTIAL_PROVIDERS = [
    ("System keyring", "system"),
    ("1Password CLI", "1password"),
    ("KeePassXC / Secret Service", "keepassxc"),
]


class SettingsConnectionTabsMixin:
    def _build_ssh_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)

        self.ssh_user_input = QLineEdit(self.settings.get("ssh_default_user", "") or "")
        self.ssh_user_input.setPlaceholderText("Used when quick-connect omits the user")
        layout.addRow("Default username:", self.ssh_user_input)

        self.ssh_port_sb = QSpinBox()
        self.ssh_port_sb.setRange(1, 65535)
        self.ssh_port_sb.setValue(int(self.settings.get("ssh_default_port", 22) or 22))
        layout.addRow("Default port:", self.ssh_port_sb)

        self.ssh_auth_combo = QComboBox()
        for label, value in SSH_AUTH_MODES:
            self.ssh_auth_combo.addItem(label, value)
        current_auth = self.settings.get("ssh_default_auth", "agent")
        idx = self.ssh_auth_combo.findData(current_auth)
        self.ssh_auth_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addRow("Default authentication:", self.ssh_auth_combo)

        self.ssh_key_path_input = QLineEdit(self.settings.get("ssh_default_key_path") or "")
        self.ssh_key_path_input.setPlaceholderText("~/.ssh/id_ed25519")
        key_browse = QPushButton("Browse...")
        key_browse.clicked.connect(self._pick_default_key)
        key_row = QHBoxLayout()
        key_row.addWidget(self.ssh_key_path_input)
        key_row.addWidget(key_browse)
        layout.addRow("Default private key:", key_row)

        self.ssh_startup_command_input = QLineEdit(self.settings.get("ssh_startup_command") or "")
        self.ssh_startup_command_input.setPlaceholderText("Optional command sent after SSH shell opens")
        layout.addRow("Startup command:", self.ssh_startup_command_input)

        self.ssh_timeout_sb = QDoubleSpinBox()
        self.ssh_timeout_sb.setRange(1.0, 120.0)
        self.ssh_timeout_sb.setDecimals(1)
        self.ssh_timeout_sb.setSingleStep(1.0)
        self.ssh_timeout_sb.setValue(float(self.settings.get("ssh_connect_timeout", 15) or 15))
        layout.addRow("Connect timeout (s):", self.ssh_timeout_sb)

        self.agent_fwd_cb = QCheckBox("Forward SSH agent to remote (use with caution)")
        self.agent_fwd_cb.setChecked(bool(self.settings.get("ssh_agent_forwarding", False)))
        layout.addRow(self.agent_fwd_cb)

        self.keepalive_sb = QSpinBox()
        self.keepalive_sb.setRange(0, 600)
        self.keepalive_sb.setSpecialValueText("Off")
        self.keepalive_sb.setSuffix(" s")
        self.keepalive_sb.setValue(int(self.settings.get("ssh_keepalive_interval", 30) or 0))
        layout.addRow("Keepalive interval:", self.keepalive_sb)

        self.tcp_keepalive_cb = QCheckBox(
            "Enable TCP keepalive on the socket (helps NAT/firewall paths stay open)"
        )
        self.tcp_keepalive_cb.setChecked(bool(self.settings.get("ssh_tcp_keepalive", True)))
        layout.addRow(self.tcp_keepalive_cb)

        known = self.settings.get("known_hosts_file") or "~/.ssh/known_hosts"
        self.known_hosts_input = QLineEdit(known)
        known_browse = QPushButton("Browse…")
        known_browse.clicked.connect(self._pick_known_hosts)
        known_row = QHBoxLayout()
        known_row.addWidget(self.known_hosts_input)
        known_row.addWidget(known_browse)
        layout.addRow("Known hosts file:", known_row)

        note = QLabel(
            "Passwords and key passphrases are stored in the system keyring "
            "(opt-in at connect time), never in sessions.json."
        )
        note.setStyleSheet("font-size: 10px;")
        note.setWordWrap(True)
        layout.addRow(note)

        return page

    def _build_security_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)

        self.credential_policy_combo = QComboBox()
        for label, value in CREDENTIAL_POLICIES:
            self.credential_policy_combo.addItem(label, value)
        current = self.settings.get("credential_save_policy", "ask")
        idx = self.credential_policy_combo.findData(current)
        self.credential_policy_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addRow("Credential saving:", self.credential_policy_combo)

        self.credential_provider_combo = QComboBox()
        for label, value in CREDENTIAL_PROVIDERS:
            self.credential_provider_combo.addItem(label, value)
        current_provider = self.settings.get("credential_provider", "system")
        idx = self.credential_provider_combo.findData(current_provider)
        self.credential_provider_combo.setCurrentIndex(idx if idx >= 0 else 0)
        layout.addRow("Credential provider:", self.credential_provider_combo)

        note = QLabel(
            "Passwords and key passphrases are never stored in sessions.json. "
            "The selected provider handles secret storage outside session files."
        )
        note.setStyleSheet("font-size: 10px;")
        note.setWordWrap(True)
        layout.addRow(note)

        return page

    def _build_logging_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)

        self.auto_log_cb = QCheckBox("Automatically log session output to file")
        self.auto_log_cb.setChecked(bool(self.settings.get("auto_log", False)))
        layout.addRow(self.auto_log_cb)

        log_dir = self.settings.get("log_directory") or "logs"
        self.log_dir_input = QLineEdit(log_dir)
        log_browse = QPushButton("Browse…")
        log_browse.clicked.connect(self._pick_log_dir)
        log_row = QHBoxLayout()
        log_row.addWidget(self.log_dir_input)
        log_row.addWidget(log_browse)
        layout.addRow("Log directory:", log_row)

        self.editor_cmd_input = QLineEdit(self.settings.get("default_editor_command") or "")
        self.editor_cmd_input.setPlaceholderText("e.g. code -n  or  gvim --remote-tab-silent")
        layout.addRow("External editor for SFTP files:", self.editor_cmd_input)

        self.text_editor_cmd_input = QLineEdit(self.settings.get("default_text_editor_command") or "")
        self.text_editor_cmd_input.setPlaceholderText("e.g. notepad  or  code -w")
        layout.addRow("Default text editor:", self.text_editor_cmd_input)

        note = QLabel(
            "Relative paths are resolved against the working directory; "
            "use ~ for the home directory."
        )
        note.setStyleSheet("font-size: 10px;")
        note.setWordWrap(True)
        layout.addRow(note)

        return page

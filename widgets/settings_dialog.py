"""Settings dialog organized into General / Terminal / Appearance / SSH / Logging.

Every option here is wired to actual behavior — see `BifrostApp.open_settings_dialog`,
`TerminalWidget.apply_settings`, and `core.color_schemes.apply_scheme`.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFontDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from core.color_schemes import apply_scheme, scheme_for, scheme_names
from core.platform_utils import default_monospace_font
from core.styles import THEME_NAMES


CURSOR_SHAPES = [("Block", "block"), ("Underline", "underline"), ("Bar", "bar")]
BELL_MODES = [("Off", "off"), ("Beep", "beep"), ("Visual flash", "visual")]
TAB_POSITIONS = ["Top", "Bottom", "Left", "Right"]
ENCODINGS = ["UTF-8", "ISO-8859-1", "ASCII", "UTF-16"]
THEMES = THEME_NAMES
SSH_AUTH_MODES = [("SSH agent", "agent"), ("Private key", "key"), ("Password", "password")]
CREDENTIAL_POLICIES = [("Ask each time", "ask"), ("Never save", "never")]
CREDENTIAL_PROVIDERS = [
    ("System keyring", "system"),
    ("1Password CLI", "1password"),
    ("KeePassXC / Secret Service", "keepassxc"),
]


class SettingsDialog(QDialog):
    import_mobaxterm_requested = pyqtSignal()

    def __init__(self, parent=None, current_settings=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.resize(700, 620)

        self.settings = dict(current_settings or {})
        self.current_font: QFont = self.settings.get("font") or default_monospace_font(10)

        outer = QVBoxLayout(self)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs)

        self.tabs.addTab(self._build_general_tab(), "General")
        self.tabs.addTab(self._build_terminal_tab(), "Terminal")
        self.tabs.addTab(self._build_appearance_tab(), "Appearance")
        self.tabs.addTab(self._build_ssh_tab(), "SSH")
        self.tabs.addTab(self._build_security_tab(), "Security")
        self.tabs.addTab(self._build_logging_tab(), "Logging")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

    # ----- General tab -----
    def _build_general_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)

        self.show_dashboard_cb = QCheckBox("Show Home Dashboard on startup")
        self.show_dashboard_cb.setChecked(self.settings.get("show_dashboard", True))
        layout.addRow(self.show_dashboard_cb)

        self.auto_sftp_cb = QCheckBox("Automatically open SFTP for SSH sessions")
        self.auto_sftp_cb.setChecked(self.settings.get("auto_sftp", True))
        layout.addRow(self.auto_sftp_cb)

        self.sftp_show_hidden_cb = QCheckBox("Show hidden files and folders in the SFTP browser")
        self.sftp_show_hidden_cb.setChecked(self.settings.get("sftp_show_hidden", False))
        layout.addRow(self.sftp_show_hidden_cb)

        self.confirm_close_tab_cb = QCheckBox("Confirm before closing a tab with an active session")
        self.confirm_close_tab_cb.setChecked(self.settings.get("confirm_close_tab", True))
        layout.addRow(self.confirm_close_tab_cb)

        self.confirm_quit_cb = QCheckBox("Confirm on quit when sessions are still active")
        self.confirm_quit_cb.setChecked(self.settings.get("confirm_quit_with_sessions", True))
        layout.addRow(self.confirm_quit_cb)

        self.confirm_workspace_reconnect_cb = QCheckBox("Confirm before opening saved workspace sessions")
        self.confirm_workspace_reconnect_cb.setChecked(self.settings.get("confirm_workspace_reconnect", True))
        layout.addRow(self.confirm_workspace_reconnect_cb)

        import_moba_btn = QPushButton("Import MobaXterm sessions...")
        import_moba_btn.clicked.connect(self.import_mobaxterm_requested.emit)
        layout.addRow("Connections:", import_moba_btn)

        return page

    # ----- Terminal tab -----
    def _build_terminal_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)

        # Font
        self.font_label = QLabel(f"{self.current_font.family()}, {self.current_font.pointSize()}pt")
        font_btn = QPushButton("Choose…")
        font_btn.clicked.connect(self._select_font)
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_label)
        font_row.addWidget(font_btn)
        layout.addRow("Font:", font_row)

        # Color scheme + manual color buttons
        self.scheme_combo = QComboBox()
        self.scheme_combo.addItems(scheme_names())
        current_scheme = self.settings.get("color_scheme") or scheme_for(
            self.settings.get("term_bg", ""), self.settings.get("term_fg", "")
        ) or "Default"
        self.scheme_combo.setCurrentText(current_scheme)
        self.scheme_combo.currentTextChanged.connect(self._on_scheme_changed)
        layout.addRow("Color scheme:", self.scheme_combo)

        self.bg_button = QPushButton(self.settings.get("term_bg", "#000000"))
        self.bg_button.clicked.connect(lambda: self._pick_color("term_bg", self.bg_button))
        self.fg_button = QPushButton(self.settings.get("term_fg", "#d3d7cf"))
        self.fg_button.clicked.connect(lambda: self._pick_color("term_fg", self.fg_button))
        color_row = QHBoxLayout()
        color_row.addWidget(QLabel("Bg:"))
        color_row.addWidget(self.bg_button)
        color_row.addSpacing(8)
        color_row.addWidget(QLabel("Fg:"))
        color_row.addWidget(self.fg_button)
        layout.addRow("Custom colors:", color_row)

        self.cursor_color_btn = QPushButton(self.settings.get("cursor_color", "#d3d7cf"))
        self.cursor_color_btn.clicked.connect(
            lambda: self._pick_color("cursor_color", self.cursor_color_btn)
        )
        layout.addRow("Cursor color:", self.cursor_color_btn)

        self.sel_bg_btn = QPushButton(self.settings.get("selection_bg", "#3465a4"))
        self.sel_bg_btn.clicked.connect(
            lambda: self._pick_color("selection_bg", self.sel_bg_btn)
        )
        self.sel_fg_btn = QPushButton(self.settings.get("selection_fg", "#ffffff"))
        self.sel_fg_btn.clicked.connect(
            lambda: self._pick_color("selection_fg", self.sel_fg_btn)
        )
        sel_row = QHBoxLayout()
        sel_row.addWidget(QLabel("Bg:"))
        sel_row.addWidget(self.sel_bg_btn)
        sel_row.addSpacing(8)
        sel_row.addWidget(QLabel("Fg:"))
        sel_row.addWidget(self.sel_fg_btn)
        layout.addRow("Selection colors:", sel_row)

        self.bold_bright_cb = QCheckBox("Bold text uses the bright ANSI palette")
        self.bold_bright_cb.setChecked(self.settings.get("bold_is_bright", True))
        layout.addRow(self.bold_bright_cb)

        # Cursor shape + blink
        self.cursor_group = QButtonGroup(self)
        cursor_row = QHBoxLayout()
        current_shape = self.settings.get("cursor_shape", "block")
        for display, key in CURSOR_SHAPES:
            rb = QRadioButton(display)
            rb.setProperty("value", key)
            if key == current_shape:
                rb.setChecked(True)
            self.cursor_group.addButton(rb)
            cursor_row.addWidget(rb)
        layout.addRow("Cursor shape:", cursor_row)

        self.blink_cb = QCheckBox("Blinking cursor")
        self.blink_cb.setChecked(self.settings.get("cursor_blink", True))
        layout.addRow(self.blink_cb)

        # Behavior
        self.rc_paste_cb = QCheckBox("Show terminal context menu on right-click")
        self.rc_paste_cb.setChecked(self.settings.get("right_click_paste", True))
        layout.addRow(self.rc_paste_cb)

        self.copy_on_select_cb = QCheckBox("Copy to clipboard when a drag-selection ends")
        self.copy_on_select_cb.setChecked(self.settings.get("copy_on_select", False))
        layout.addRow(self.copy_on_select_cb)

        self.strip_newlines_cb = QCheckBox("Strip CRLF/CR newlines when pasting")
        self.strip_newlines_cb.setChecked(self.settings.get("strip_newlines_on_paste", False))
        layout.addRow(self.strip_newlines_cb)

        self.confirm_multiline_paste_cb = QCheckBox("Confirm before pasting multiple lines")
        self.confirm_multiline_paste_cb.setChecked(self.settings.get("confirm_multiline_paste", True))
        layout.addRow(self.confirm_multiline_paste_cb)

        self.confirm_large_paste_cb = QCheckBox("Confirm before large pastes")
        self.confirm_large_paste_cb.setChecked(self.settings.get("confirm_large_paste", True))
        layout.addRow(self.confirm_large_paste_cb)

        self.large_paste_threshold_sb = QSpinBox()
        self.large_paste_threshold_sb.setRange(100, 100_000)
        self.large_paste_threshold_sb.setSingleStep(500)
        self.large_paste_threshold_sb.setValue(int(self.settings.get("large_paste_threshold", 2000) or 2000))
        layout.addRow("Large paste threshold:", self.large_paste_threshold_sb)

        self.scrollback_sb = QSpinBox()
        self.scrollback_sb.setRange(100, 1_000_000)
        self.scrollback_sb.setSingleStep(500)
        self.scrollback_sb.setValue(int(self.settings.get("scrollback", 5000)))
        layout.addRow("Scrollback lines:", self.scrollback_sb)

        self.wheel_sb = QSpinBox()
        self.wheel_sb.setRange(1, 20)
        self.wheel_sb.setValue(int(self.settings.get("wheel_lines", 3)))
        layout.addRow("Lines per wheel notch:", self.wheel_sb)

        # Bell mode
        self.bell_group = QButtonGroup(self)
        bell_row = QHBoxLayout()
        current_bell = self.settings.get("bell_mode", "beep")
        for display, key in BELL_MODES:
            rb = QRadioButton(display)
            rb.setProperty("value", key)
            if key == current_bell:
                rb.setChecked(True)
            self.bell_group.addButton(rb)
            bell_row.addWidget(rb)
        layout.addRow("Bell:", bell_row)

        # Encoding
        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(ENCODINGS)
        self.encoding_combo.setCurrentText(self.settings.get("encoding", "UTF-8"))
        layout.addRow("Character set:", self.encoding_combo)

        return page

    # ----- Appearance tab -----
    def _build_appearance_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES)
        if self.settings.get("theme") in THEMES:
            self.theme_combo.setCurrentText(self.settings["theme"])
        layout.addRow("Application theme:", self.theme_combo)

        # Opacity slider with live percentage label
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.settings.get("opacity", 100)))
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(
            lambda v: self.opacity_label.setText(f"{v}%")
        )
        op_row = QHBoxLayout()
        op_row.addWidget(self.opacity_slider, 1)
        op_row.addWidget(self.opacity_label)
        layout.addRow("Window opacity:", op_row)

        self.tab_pos_combo = QComboBox()
        self.tab_pos_combo.addItems(TAB_POSITIONS)
        self.tab_pos_combo.setCurrentText(self.settings.get("tab_position", "Top"))
        layout.addRow("Tab position:", self.tab_pos_combo)

        self.restore_geom_cb = QCheckBox("Restore window size and position on startup")
        self.restore_geom_cb.setChecked(self.settings.get("restore_window_geometry", True))
        layout.addRow(self.restore_geom_cb)

        return page

    # ----- SSH tab -----
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

    # ----- Security tab -----
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

    # ----- Logging tab -----
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

    # ----- helpers -----

    def _select_font(self):
        font, ok = QFontDialog.getFont(self.current_font, self)
        if ok:
            self.current_font = font
            self.font_label.setText(f"{font.family()}, {font.pointSize()}pt")

    def _pick_color(self, key: str, button: QPushButton):
        current = QColor(self.settings.get(key) or "#000000")
        color = QColorDialog.getColor(current, self, "Select color")
        if color.isValid():
            self.settings[key] = color.name()
            button.setText(color.name())
            # Custom colors override the scheme; reflect that in the dropdown.
            existing = scheme_for(self.settings.get("term_bg", ""), self.settings.get("term_fg", ""))
            if existing:
                self.scheme_combo.blockSignals(True)
                self.scheme_combo.setCurrentText(existing)
                self.scheme_combo.blockSignals(False)

    def _on_scheme_changed(self, name: str):
        apply_scheme(self.settings, name)
        self.bg_button.setText(self.settings["term_bg"])
        self.fg_button.setText(self.settings["term_fg"])

    def _pick_known_hosts(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select known_hosts file", self.known_hosts_input.text(),
        )
        if path:
            self.known_hosts_input.setText(path)

    def _pick_default_key(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select default private key", self.ssh_key_path_input.text(),
            "All files (*)",
        )
        if path:
            self.ssh_key_path_input.setText(path)

    def _pick_log_dir(self):
        path = QFileDialog.getExistingDirectory(
            self, "Select log directory", self.log_dir_input.text(),
        )
        if path:
            self.log_dir_input.setText(path)

    def _radio_value(self, group: QButtonGroup, default: str) -> str:
        for btn in group.buttons():
            if btn.isChecked():
                return btn.property("value") or default
        return default

    # ----- output -----

    def get_settings(self) -> dict:
        out = dict(self.settings)  # carry forward unrecognized keys
        out.update({
            "show_dashboard": self.show_dashboard_cb.isChecked(),
            "auto_sftp": self.auto_sftp_cb.isChecked(),
            "sftp_show_hidden": self.sftp_show_hidden_cb.isChecked(),
            "confirm_close_tab": self.confirm_close_tab_cb.isChecked(),
            "confirm_quit_with_sessions": self.confirm_quit_cb.isChecked(),
            "confirm_workspace_reconnect": self.confirm_workspace_reconnect_cb.isChecked(),

            "font": self.current_font,
            "color_scheme": self.scheme_combo.currentText(),
            # term_bg/term_fg already mutated by scheme/picker callbacks
            "cursor_shape": self._radio_value(self.cursor_group, "block"),
            "cursor_blink": self.blink_cb.isChecked(),
            "right_click_paste": self.rc_paste_cb.isChecked(),
            "copy_on_select": self.copy_on_select_cb.isChecked(),
            "strip_newlines_on_paste": self.strip_newlines_cb.isChecked(),
            "confirm_multiline_paste": self.confirm_multiline_paste_cb.isChecked(),
            "confirm_large_paste": self.confirm_large_paste_cb.isChecked(),
            "large_paste_threshold": self.large_paste_threshold_sb.value(),
            "bold_is_bright": self.bold_bright_cb.isChecked(),
            "scrollback": self.scrollback_sb.value(),
            "wheel_lines": self.wheel_sb.value(),
            "bell_mode": self._radio_value(self.bell_group, "beep"),
            "encoding": self.encoding_combo.currentText(),

            "theme": self.theme_combo.currentText(),
            "opacity": self.opacity_slider.value(),
            "tab_position": self.tab_pos_combo.currentText(),
            "restore_window_geometry": self.restore_geom_cb.isChecked(),

            "ssh_default_user": self.ssh_user_input.text().strip(),
            "ssh_default_port": self.ssh_port_sb.value(),
            "ssh_default_auth": self.ssh_auth_combo.currentData() or "agent",
            "ssh_default_key_path": self.ssh_key_path_input.text().strip(),
            "ssh_startup_command": self.ssh_startup_command_input.text().strip(),
            "ssh_connect_timeout": self.ssh_timeout_sb.value(),
            "ssh_agent_forwarding": self.agent_fwd_cb.isChecked(),
            "ssh_keepalive_interval": self.keepalive_sb.value(),
            "ssh_tcp_keepalive": self.tcp_keepalive_cb.isChecked(),
            "known_hosts_file": self.known_hosts_input.text().strip() or "~/.ssh/known_hosts",

            "credential_save_policy": self.credential_policy_combo.currentData() or "ask",
            "credential_provider": self.credential_provider_combo.currentData() or "system",

            "auto_log": self.auto_log_cb.isChecked(),
            "log_directory": self.log_dir_input.text().strip() or "logs",
            "default_editor_command": self.editor_cmd_input.text().strip(),
            "default_text_editor_command": self.text_editor_cmd_input.text().strip(),
        })
        # cursor_color / selection_bg / selection_fg are already in self.settings
        # because the color pickers mutate it; surface them explicitly so they
        # don't get dropped if the caller passed in a sparse dict.
        for key, default in (
            ("cursor_color", "#d3d7cf"),
            ("selection_bg", "#3465a4"),
            ("selection_fg", "#ffffff"),
        ):
            out[key] = self.settings.get(key, default)
        # term_bg/term_fg might not be in self.settings if defaults were used at
        # construction; ensure they're present in the output.
        out.setdefault("term_bg", "#000000")
        out.setdefault("term_fg", "#d3d7cf")
        # Mirror the values back from self.settings since callbacks mutate it.
        out["term_bg"] = self.settings.get("term_bg", out["term_bg"])
        out["term_fg"] = self.settings.get("term_fg", out["term_fg"])
        return out

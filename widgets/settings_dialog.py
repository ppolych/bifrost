"""Settings dialog organized into General / Terminal / Appearance / SSH / Logging.

Every option here is wired to actual behavior — see `BifrostApp.open_settings_dialog`,
`TerminalWidget.apply_settings`, and `core.color_schemes.apply_scheme`.
"""

from __future__ import annotations

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtGui import QColor, QFont
from PyQt6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFontDialog,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
)

from core.color_schemes import apply_scheme, scheme_for
from core.platform_utils import default_monospace_font
from widgets.settings_connection_tabs import SettingsConnectionTabsMixin
from widgets.settings_general_tabs import SettingsGeneralTabsMixin


class SettingsDialog(QDialog, SettingsGeneralTabsMixin, SettingsConnectionTabsMixin):
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
            "bracketed_paste": self.bracketed_paste_cb.isChecked(),
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

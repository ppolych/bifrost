from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup, QCheckBox, QComboBox, QFormLayout, QHBoxLayout, QLabel,
    QPushButton, QRadioButton, QSlider, QSpinBox, QWidget,
)

from core.color_schemes import scheme_for, scheme_names
from core.styles import THEME_NAMES


CURSOR_SHAPES = [("Block", "block"), ("Underline", "underline"), ("Bar", "bar")]
BELL_MODES = [("Off", "off"), ("Beep", "beep"), ("Visual flash", "visual")]
TAB_POSITIONS = ["Top", "Bottom", "Left", "Right"]
ENCODINGS = ["UTF-8", "ISO-8859-1", "ASCII", "UTF-16"]
THEMES = THEME_NAMES


class SettingsGeneralTabsMixin:
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

    def _build_terminal_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)

        self.font_label = QLabel(f"{self.current_font.family()}, {self.current_font.pointSize()}pt")
        font_btn = QPushButton("Choose…")
        font_btn.clicked.connect(self._select_font)
        font_row = QHBoxLayout()
        font_row.addWidget(self.font_label)
        font_row.addWidget(font_btn)
        layout.addRow("Font:", font_row)

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
        self.sel_bg_btn.clicked.connect(lambda: self._pick_color("selection_bg", self.sel_bg_btn))
        self.sel_fg_btn = QPushButton(self.settings.get("selection_fg", "#ffffff"))
        self.sel_fg_btn.clicked.connect(lambda: self._pick_color("selection_fg", self.sel_fg_btn))
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

        self.rc_paste_cb = QCheckBox("Show terminal context menu on right-click")
        self.rc_paste_cb.setChecked(self.settings.get("right_click_paste", True))
        layout.addRow(self.rc_paste_cb)

        self.copy_on_select_cb = QCheckBox("Copy to clipboard when a drag-selection ends")
        self.copy_on_select_cb.setChecked(self.settings.get("copy_on_select", False))
        layout.addRow(self.copy_on_select_cb)

        self.strip_newlines_cb = QCheckBox("Strip CRLF/CR newlines when pasting")
        self.strip_newlines_cb.setChecked(self.settings.get("strip_newlines_on_paste", False))
        layout.addRow(self.strip_newlines_cb)

        self.bracketed_paste_cb = QCheckBox("Use bracketed paste mode")
        self.bracketed_paste_cb.setChecked(self.settings.get("bracketed_paste", True))
        layout.addRow(self.bracketed_paste_cb)

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

        self.encoding_combo = QComboBox()
        self.encoding_combo.addItems(ENCODINGS)
        self.encoding_combo.setCurrentText(self.settings.get("encoding", "UTF-8"))
        layout.addRow("Character set:", self.encoding_combo)

        return page

    def _build_appearance_tab(self) -> QWidget:
        page = QWidget()
        layout = QFormLayout(page)

        self.theme_combo = QComboBox()
        self.theme_combo.addItems(THEMES)
        if self.settings.get("theme") in THEMES:
            self.theme_combo.setCurrentText(self.settings["theme"])
        layout.addRow("Application theme:", self.theme_combo)

        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(20, 100)
        self.opacity_slider.setValue(int(self.settings.get("opacity", 100)))
        self.opacity_label = QLabel(f"{self.opacity_slider.value()}%")
        self.opacity_slider.valueChanged.connect(lambda v: self.opacity_label.setText(f"{v}%"))
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

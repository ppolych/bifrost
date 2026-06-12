from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AppTheme:
    window: str
    panel: str
    panel_alt: str
    surface: str
    surface_alt: str
    text: str
    muted: str
    border: str
    accent: str
    accent_text: str
    selection: str
    danger: str


THEMES: dict[str, AppTheme] = {
    "Dark (MobaXterm style)": AppTheme(
        window="#242629",
        panel="#2f3337",
        panel_alt="#3a3f44",
        surface="#1d1f22",
        surface_alt="#2a2d31",
        text="#e6e6e6",
        muted="#a8adb3",
        border="#4a4f55",
        accent="#4f8cc9",
        accent_text="#ffffff",
        selection="#315f8f",
        danger="#e05f5f",
    ),
    "Light": AppTheme(
        window="#f5f6f8",
        panel="#ffffff",
        panel_alt="#eef1f4",
        surface="#ffffff",
        surface_alt="#e7ebef",
        text="#20242a",
        muted="#5e6670",
        border="#c9d0d8",
        accent="#2468a8",
        accent_text="#ffffff",
        selection="#cfe3f7",
        danger="#b3261e",
    ),
    "Solarized": AppTheme(
        window="#eee8d5",
        panel="#fdf6e3",
        panel_alt="#eee8d5",
        surface="#fdf6e3",
        surface_alt="#e7dfc8",
        text="#073642",
        muted="#586e75",
        border="#93a1a1",
        accent="#268bd2",
        accent_text="#fdf6e3",
        selection="#d7e8e8",
        danger="#dc322f",
    ),
    "Nord": AppTheme(
        window="#2e3440",
        panel="#3b4252",
        panel_alt="#434c5e",
        surface="#242933",
        surface_alt="#363d4c",
        text="#eceff4",
        muted="#d8dee9",
        border="#4c566a",
        accent="#88c0d0",
        accent_text="#1f252f",
        selection="#5e81ac",
        danger="#bf616a",
    ),
    "Dracula": AppTheme(
        window="#282a36",
        panel="#343746",
        panel_alt="#44475a",
        surface="#21222c",
        surface_alt="#383a4a",
        text="#f8f8f2",
        muted="#c4c8d4",
        border="#55596f",
        accent="#bd93f9",
        accent_text="#1f1f29",
        selection="#6272a4",
        danger="#ff5555",
    ),
    "Gruvbox Dark": AppTheme(
        window="#282828",
        panel="#3c3836",
        panel_alt="#504945",
        surface="#1d2021",
        surface_alt="#32302f",
        text="#ebdbb2",
        muted="#d5c4a1",
        border="#665c54",
        accent="#fabd2f",
        accent_text="#282828",
        selection="#7c6f64",
        danger="#fb4934",
    ),
    "One Dark": AppTheme(
        window="#282c34",
        panel="#323842",
        panel_alt="#3b4250",
        surface="#21252b",
        surface_alt="#2c313a",
        text="#abb2bf",
        muted="#8b94a5",
        border="#4b5263",
        accent="#61afef",
        accent_text="#1b2027",
        selection="#3e5c7f",
        danger="#e06c75",
    ),
    "Tokyo Night": AppTheme(
        window="#1a1b26",
        panel="#24283b",
        panel_alt="#2f3549",
        surface="#16161e",
        surface_alt="#202437",
        text="#c0caf5",
        muted="#9aa5ce",
        border="#414868",
        accent="#7aa2f7",
        accent_text="#10131d",
        selection="#364a82",
        danger="#f7768e",
    ),
    "Graphite": AppTheme(
        window="#202124",
        panel="#2b2d31",
        panel_alt="#36393f",
        surface="#18191c",
        surface_alt="#25272b",
        text="#f1f3f4",
        muted="#bdc1c6",
        border="#5f6368",
        accent="#8ab4f8",
        accent_text="#111418",
        selection="#3c5f8f",
        danger="#f28b82",
    ),
    "High Contrast": AppTheme(
        window="#000000",
        panel="#000000",
        panel_alt="#101010",
        surface="#000000",
        surface_alt="#181818",
        text="#ffffff",
        muted="#ffffff",
        border="#ffffff",
        accent="#ffff00",
        accent_text="#000000",
        selection="#ffff00",
        danger="#ff4d4d",
    ),
}

THEME_NAMES = list(THEMES.keys())
DEFAULT_THEME = "Dark (MobaXterm style)"


def get_theme_stylesheet(name: str | None) -> str:
    return _theme_stylesheet(THEMES.get(name or "", THEMES[DEFAULT_THEME]))


def get_dark_theme() -> str:
    return get_theme_stylesheet(DEFAULT_THEME)


def get_light_theme() -> str:
    return get_theme_stylesheet("Light")


def get_solarized_theme() -> str:
    return get_theme_stylesheet("Solarized")


def get_high_contrast_theme() -> str:
    return get_theme_stylesheet("High Contrast")


def _theme_stylesheet(t: AppTheme) -> str:
    return f"""
        QMainWindow, QDialog {{
            background-color: {t.window};
            color: {t.text};
        }}
        QWidget {{
            color: {t.text};
            selection-background-color: {t.selection};
            selection-color: {t.accent_text};
        }}
        QToolBar {{
            background-color: {t.panel};
            border-bottom: 1px solid {t.border};
            spacing: 8px;
            padding: 5px;
        }}
        QToolButton {{
            color: {t.text};
            font-weight: bold;
            padding: 5px 8px;
            border: 1px solid transparent;
            border-radius: 3px;
        }}
        QPushButton[compact="true"] {{
            background-color: {t.panel};
            color: {t.text};
            border: 1px solid {t.border};
            padding: 3px 6px;
            font-size: 10px;
        }}
        QPushButton[compact="true"]:hover {{
            background-color: {t.panel_alt};
            border-color: {t.accent};
        }}
        QPushButton[compact="true"]:disabled {{
            background-color: {t.surface_alt};
            color: {t.muted};
            border-color: {t.border};
        }}
        QToolButton:hover {{
            background-color: {t.panel_alt};
            border-color: {t.border};
        }}
        QToolButton:checked {{
            background-color: {t.accent};
            color: {t.accent_text};
            border-color: {t.accent};
        }}
        QMenuBar {{
            background-color: {t.panel};
            color: {t.text};
            border-bottom: 1px solid {t.border};
        }}
        QMenuBar::item {{
            padding: 4px 8px;
            background: transparent;
        }}
        QMenuBar::item:selected {{
            background-color: {t.panel_alt};
        }}
        QMenu {{
            background-color: {t.surface};
            color: {t.text};
            border: 1px solid {t.border};
        }}
        QMenu::item {{
            padding: 5px 24px 5px 20px;
        }}
        QMenu::item:selected {{
            background-color: {t.selection};
            color: {t.text};
        }}
        QSplitter::handle {{
            background-color: {t.border};
        }}
        QStatusBar {{
            background-color: {t.panel};
            color: {t.muted};
            border-top: 1px solid {t.border};
        }}
        QTabWidget::pane {{
            border: 1px solid {t.border};
            background-color: {t.surface};
        }}
        QTabBar::tab {{
            background: {t.panel};
            color: {t.muted};
            padding: 8px 15px;
            border: 1px solid {t.border};
            border-bottom: none;
        }}
        QTabBar::tab:hover {{
            background: {t.panel_alt};
            color: {t.text};
        }}
        QTabBar::tab:selected {{
            background: {t.surface};
            color: {t.text};
        }}
        QGroupBox {{
            border: 1px solid {t.border};
            border-radius: 4px;
            margin-top: 10px;
            padding-top: 10px;
        }}
        QFrame {{
            background-color: transparent;
            border: none;
        }}
        QGroupBox::title {{
            subcontrol-origin: margin;
            left: 8px;
            padding: 0 4px;
            color: {t.muted};
        }}
        QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox,
        QComboBox, QListView, QTreeView, QTableView, QListWidget, QTreeWidget {{
            background-color: {t.surface};
            color: {t.text};
            border: 1px solid {t.border};
            border-radius: 3px;
            padding: 3px;
        }}
        QTreeWidget::item, QListWidget::item {{
            padding: 2px;
        }}
        QTreeWidget::item:selected, QListWidget::item:selected {{
            background-color: {t.selection};
            color: {t.text};
        }}
        QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QSpinBox:focus,
        QDoubleSpinBox:focus, QComboBox:focus, QListView:focus, QTreeView:focus,
        QTableView:focus {{
            border-color: {t.accent};
        }}
        QComboBox::drop-down {{
            border-left: 1px solid {t.border};
            background-color: {t.panel_alt};
            width: 22px;
        }}
        QComboBox QAbstractItemView {{
            background-color: {t.surface};
            color: {t.text};
            selection-background-color: {t.selection};
        }}
        QPushButton {{
            background-color: {t.panel_alt};
            color: {t.text};
            border: 1px solid {t.border};
            border-radius: 4px;
            padding: 5px 10px;
        }}
        QPushButton:hover {{
            background-color: {t.accent};
            color: {t.accent_text};
            border-color: {t.accent};
        }}
        QPushButton:pressed {{
            background-color: {t.selection};
        }}
        QPushButton:disabled, QToolButton:disabled {{
            color: {t.muted};
            background-color: {t.panel};
        }}
        QCheckBox, QRadioButton, QLabel {{
            color: {t.text};
        }}
        QSlider::groove:horizontal {{
            height: 5px;
            background: {t.surface_alt};
            border: 1px solid {t.border};
            border-radius: 3px;
        }}
        QSlider::handle:horizontal {{
            width: 14px;
            margin: -5px 0;
            background: {t.accent};
            border: 1px solid {t.border};
            border-radius: 7px;
        }}
        QScrollBar:vertical, QScrollBar:horizontal {{
            background: {t.surface};
            border: 1px solid {t.border};
        }}
        QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
            background: {t.panel_alt};
            border-radius: 3px;
            min-height: 24px;
            min-width: 24px;
        }}
        QScrollBar::handle:vertical:hover, QScrollBar::handle:horizontal:hover {{
            background: {t.accent};
        }}
        QProgressBar {{
            background-color: {t.surface};
            color: {t.text};
            border: 1px solid {t.border};
            border-radius: 3px;
            text-align: center;
        }}
        QProgressBar::chunk {{
            background-color: {t.accent};
        }}
    """

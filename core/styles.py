from __future__ import annotations

from core.app_themes import AppTheme, DEFAULT_THEME, THEMES, THEME_NAMES



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

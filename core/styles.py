THEME_NAMES = ["Dark (MobaXterm style)", "Light", "Solarized", "High Contrast"]
DEFAULT_THEME = "Dark (MobaXterm style)"


def get_theme_stylesheet(name: str | None) -> str:
    if name == "Light":
        return get_light_theme()
    if name == "Solarized":
        return get_solarized_theme()
    if name == "High Contrast":
        return get_high_contrast_theme()
    return get_dark_theme()


def get_dark_theme():
    return """
        QMainWindow {
            background-color: #2b2b2b;
        }
        QToolBar {
            background-color: #3c3f41;
            border-bottom: 1px solid #555;
            spacing: 10px;
            padding: 5px;
        }
        QToolButton {
            color: #bbbbbb;
            font-weight: bold;
            padding: 5px;
        }
        QToolButton:hover {
            background-color: #4b4b4b;
        }
        QSplitter::handle {
            background-color: #444;
        }
        QTabWidget::pane {
            border: 1px solid #444;
            background-color: #1e1e1e;
        }
        QTabBar::tab {
            background: #3c3f41;
            color: #bbbbbb;
            padding: 8px 15px;
            border: 1px solid #444;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background: #4e5254;
            color: #ffffff;
        }
        QStatusBar {
            background-color: #3c3f41;
            color: #888;
        }
    """


def get_light_theme():
    return """
        QMainWindow {
            background-color: #f4f4f4;
        }
        QToolBar {
            background-color: #eeeeee;
            border-bottom: 1px solid #c8c8c8;
            spacing: 10px;
            padding: 5px;
        }
        QToolButton {
            color: #202020;
            font-weight: bold;
            padding: 5px;
        }
        QToolButton:hover {
            background-color: #dddddd;
        }
        QSplitter::handle {
            background-color: #d0d0d0;
        }
        QTabWidget::pane {
            border: 1px solid #c8c8c8;
            background-color: #ffffff;
        }
        QTabBar::tab {
            background: #e8e8e8;
            color: #202020;
            padding: 8px 15px;
            border: 1px solid #c8c8c8;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background: #ffffff;
            color: #000000;
        }
        QStatusBar {
            background-color: #eeeeee;
            color: #333333;
        }
    """


def get_solarized_theme():
    return """
        QMainWindow {
            background-color: #eee8d5;
        }
        QToolBar {
            background-color: #fdf6e3;
            border-bottom: 1px solid #93a1a1;
            spacing: 10px;
            padding: 5px;
        }
        QToolButton {
            color: #586e75;
            font-weight: bold;
            padding: 5px;
        }
        QToolButton:hover {
            background-color: #eee8d5;
        }
        QSplitter::handle {
            background-color: #93a1a1;
        }
        QTabWidget::pane {
            border: 1px solid #93a1a1;
            background-color: #fdf6e3;
        }
        QTabBar::tab {
            background: #eee8d5;
            color: #586e75;
            padding: 8px 15px;
            border: 1px solid #93a1a1;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background: #fdf6e3;
            color: #073642;
        }
        QStatusBar {
            background-color: #fdf6e3;
            color: #586e75;
        }
    """


def get_high_contrast_theme():
    return """
        QMainWindow {
            background-color: #000000;
        }
        QToolBar {
            background-color: #000000;
            border-bottom: 2px solid #ffffff;
            spacing: 10px;
            padding: 5px;
        }
        QToolButton {
            color: #ffffff;
            font-weight: bold;
            padding: 5px;
            border: 1px solid #ffffff;
        }
        QToolButton:hover {
            background-color: #1a1a1a;
        }
        QSplitter::handle {
            background-color: #ffffff;
        }
        QTabWidget::pane {
            border: 2px solid #ffffff;
            background-color: #000000;
        }
        QTabBar::tab {
            background: #000000;
            color: #ffffff;
            padding: 8px 15px;
            border: 2px solid #ffffff;
            border-bottom: none;
        }
        QTabBar::tab:selected {
            background: #ffffff;
            color: #000000;
        }
        QStatusBar {
            background-color: #000000;
            color: #ffffff;
            border-top: 2px solid #ffffff;
        }
    """

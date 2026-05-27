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

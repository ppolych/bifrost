from PyQt6.QtWidgets import QApplication, QDialog, QMenu, QTextEdit, QVBoxLayout


def show_details(parent, details: str) -> None:
    dialog = QDialog(parent)
    dialog.setWindowTitle("Remote monitor details")
    dialog.resize(520, 360)
    layout = QVBoxLayout(dialog)
    text = QTextEdit()
    text.setReadOnly(True)
    text.setPlainText(details)
    layout.addWidget(text)
    dialog.exec()


def copy_details(details: str) -> None:
    QApplication.clipboard().setText(details)


def build_monitor_menu(widget) -> QMenu:
    menu = QMenu(widget)
    refresh = menu.addAction("Refresh now")
    refresh.triggered.connect(widget.refresh_now)
    pause = menu.addAction("Resume monitor" if widget.paused else "Pause monitor")
    pause.triggered.connect(widget.toggle_pause)
    copy = menu.addAction("Copy details")
    copy.triggered.connect(widget.copy_details)
    menu.addSeparator()
    ops = menu.addAction("Open Remote Ops")
    ops.triggered.connect(widget.remote_ops_requested.emit)
    for label, interval in (("5 seconds", 5000), ("10 seconds", 10000), ("30 seconds", 30000)):
        action = menu.addAction(f"Poll every {label}")
        action.triggered.connect(lambda _checked=False, value=interval: widget.set_poll_interval(value))
    return menu

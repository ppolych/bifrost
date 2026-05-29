from PyQt6.QtWidgets import QWidget, QVBoxLayout, QSplitter
from PyQt6.QtCore import Qt, pyqtSignal

from widgets.terminal import TerminalWidget
from widgets.search_bar import SearchBar


class TerminalContainer(QWidget):
    detach_requested = pyqtSignal(object)

    def __init__(
        self,
        name,
        command=None,
        key_callback=None,
        settings=None,
        backend=None,
        ssh_session=None,
    ):
        super().__init__()
        self.name = name
        self.settings = settings
        self.command = command
        self.ssh_session = dict(ssh_session) if isinstance(ssh_session, dict) else None
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.setSpacing(0)

        self.main_splitter = QSplitter(Qt.Orientation.Vertical)
        self.layout.addWidget(self.main_splitter)

        self.search_bar = SearchBar()
        self.search_bar.hide()
        self.search_bar.search_requested.connect(self.perform_search)
        self.search_bar.closed.connect(self.search_bar.hide)
        self.layout.addWidget(self.search_bar)

        self.key_callback = key_callback
        self.primary_terminal = self.add_terminal(self.main_splitter, command, backend=backend)

    def add_terminal(self, parent_splitter, command=None, backend=None):
        term = TerminalWidget(command=command, settings=self.settings, backend=backend)
        if self.key_callback:
            term.key_pressed.connect(self.key_callback)
        term.detach_requested.connect(lambda: self.detach_requested.emit(self))
        term.search_requested.connect(self.toggle_search)
        parent_splitter.addWidget(term)
        return term

    def split(self, orientation):
        if orientation == "quad":
            self.main_splitter.setOrientation(Qt.Orientation.Vertical)
            h_splitter_top = QSplitter(Qt.Orientation.Horizontal)
            h_splitter_bottom = QSplitter(Qt.Orientation.Horizontal)
            self.add_terminal(h_splitter_top)
            self.add_terminal(h_splitter_top)
            self.add_terminal(h_splitter_bottom)
            self.add_terminal(h_splitter_bottom)
            while self.main_splitter.count():
                self.main_splitter.widget(0).deleteLater()
            self.main_splitter.addWidget(h_splitter_top)
            self.main_splitter.addWidget(h_splitter_bottom)
        else:
            self.main_splitter.setOrientation(
                Qt.Orientation.Vertical if orientation == "vert" else Qt.Orientation.Horizontal
            )
            self.add_terminal(self.main_splitter)

    def toggle_search(self):
        if self.search_bar.isVisible():
            self.search_bar.hide()
        else:
            self.search_bar.show()
            self.search_bar.input.setFocus()

    def perform_search(self, text, forward):
        count = self.primary_terminal.search(text, forward)
        if text:
            if count > 0:
                self.search_bar.set_status(f"{count} match{'es' if count != 1 else ''}")
            else:
                self.search_bar.set_status("No matches")
        else:
            self.search_bar.set_status("")

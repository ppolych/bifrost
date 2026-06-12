from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QLabel, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal

class SearchBar(QFrame):
    search_requested = pyqtSignal(str, bool) # text, forward
    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Find in terminal...")
        self.input.returnPressed.connect(lambda: self.search_requested.emit(self.input.text(), True))
        layout.addWidget(self.input)

        self.next_btn = QPushButton("Next")
        self.next_btn.clicked.connect(lambda: self.search_requested.emit(self.input.text(), True))
        layout.addWidget(self.next_btn)

        self.prev_btn = QPushButton("Prev")
        self.prev_btn.clicked.connect(lambda: self.search_requested.emit(self.input.text(), False))
        layout.addWidget(self.prev_btn)

        self.close_btn = QPushButton("X")
        self.close_btn.setFixedWidth(30)
        self.close_btn.clicked.connect(self.closed.emit)
        layout.addWidget(self.close_btn)

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 10px; margin-left: 10px;")
        layout.addWidget(self.status_label)

    def set_status(self, text):
        self.status_label.setText(text)

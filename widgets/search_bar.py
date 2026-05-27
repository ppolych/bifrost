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
        self.setStyleSheet("background-color: #3c3f41; border-top: 1px solid #555;")
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 0, 10, 0)

        self.input = QLineEdit()
        self.input.setPlaceholderText("Find in terminal...")
        self.input.setStyleSheet("background: #2b2b2b; color: #ccc; border: 1px solid #555;")
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

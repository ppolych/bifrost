from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QFrame, QListWidget, QListWidgetItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont

class Dashboard(QWidget):
    session_requested = pyqtSignal(str)
    
    def __init__(self, recent_sessions=None, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(40, 40, 40, 40)
        self.layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.setStyleSheet("background-color: #2b2b2b;")

        # Header
        header_layout = QHBoxLayout()
        title_layout = QVBoxLayout()
        
        title = QLabel("Bifrost")
        title.setFont(QFont("Arial", 36, QFont.Weight.Bold))
        title.setStyleSheet("color: #569cd6;")
        title_layout.addWidget(title)

        subtitle = QLabel("The professional toolkit for remote computing")
        subtitle.setFont(QFont("Arial", 12))
        subtitle.setStyleSheet("color: #888;")
        title_layout.addWidget(subtitle)
        
        header_layout.addLayout(title_layout)
        header_layout.addStretch()
        
        logo_placeholder = QLabel("PRO")
        logo_placeholder.setStyleSheet("background: #569cd6; color: white; padding: 10px; border-radius: 5px; font-weight: bold;")
        header_layout.addWidget(logo_placeholder)
        
        self.layout.addLayout(header_layout)
        self.layout.addSpacing(30)

        # Main Area: Quick Actions + Recents
        main_layout = QHBoxLayout()
        
        # Left: Quick Actions
        actions_frame = QFrame()
        actions_vbox = QVBoxLayout(actions_frame)
        actions_vbox.setSpacing(10)
        
        btn_style = "text-align: left; padding: 15px; background-color: #3c3f41; color: white; border: 1px solid #555; font-size: 14px;"
        
        self.btn_ssh = QPushButton("  Start local terminal")
        self.btn_ssh.setStyleSheet(btn_style)
        
        self.btn_session = QPushButton("  Create new session")
        self.btn_session.setStyleSheet(btn_style)
        
        self.btn_tools = QPushButton("  Open network tools")
        self.btn_tools.setStyleSheet(btn_style)
        
        actions_vbox.addWidget(self.btn_ssh)
        actions_vbox.addWidget(self.btn_session)
        actions_vbox.addWidget(self.btn_tools)
        actions_vbox.addStretch()
        
        main_layout.addWidget(actions_frame, 1)
        
        # Right: Recent Sessions (MobaXterm style)
        recents_frame = QFrame()
        recents_vbox = QVBoxLayout(recents_frame)
        
        recents_label = QLabel("Recent sessions")
        recents_label.setStyleSheet("color: #aaa; font-weight: bold; margin-bottom: 5px;")
        recents_vbox.addWidget(recents_label)
        
        self.recents_list = QListWidget()
        self.recents_list.setStyleSheet("background: #1e1e1e; color: #ccc; border: 1px solid #444;")
        self.recents_list.itemDoubleClicked.connect(self.on_recent_click)
        
        if recent_sessions:
            for s in recent_sessions:
                self.recents_list.addItem(s)
        else:
            self.recents_list.addItem("No recent sessions")
            
        recents_vbox.addWidget(self.recents_list)
        main_layout.addWidget(recents_frame, 2)
        
        self.layout.addLayout(main_layout)

    def on_recent_click(self, item):
        self.session_requested.emit(item.text())

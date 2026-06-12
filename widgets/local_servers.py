from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, 
    QLabel, QPushButton, QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QThread
import http.server
import socketserver
import socket

class ServerThread(QThread):
    def __init__(self, port):
        super().__init__()
        self.port = port
        self.httpd = None

    def run(self):
        handler = http.server.SimpleHTTPRequestHandler
        try:
            with socketserver.TCPServer(("", self.port), handler) as self.httpd:
                self.httpd.serve_forever()
        except Exception as e:
            print(f"Server error: {e}")

    def stop(self):
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

class LocalServersManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)
        self.threads = {} # port -> thread
        
        self.label = QLabel("Local Servers (HTTP/FTP)")
        self.label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.label)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Server Type", "Port", "Status"])
        
        # Sample Servers
        self.items = {
            "HTTP": QTreeWidgetItem(self.tree, ["HTTP Server", "8080", "Stopped"]),
            "TFTP": QTreeWidgetItem(self.tree, ["TFTP Server", "69", "Stopped"]),
            "FTP":  QTreeWidgetItem(self.tree, ["FTP Server", "21", "Stopped"])
        }
        
        self.layout.addWidget(self.tree)

        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("Start Selected")
        self.start_btn.clicked.connect(self.start_server)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_server)
        
        btn_layout.addWidget(self.start_btn)
        btn_layout.addWidget(self.stop_btn)
        self.layout.addLayout(btn_layout)

    def start_server(self):
        item = self.tree.currentItem()
        if not item: return
        
        type_ = item.text(0).split()[0]
        port = int(item.text(1))
        
        if port in self.threads:
            QMessageBox.warning(self, "Error", "Server already running on this port.")
            return

        if type_ == "HTTP":
            thread = ServerThread(port)
            thread.start()
            self.threads[port] = thread
            item.setText(2, "Running")
            item.setForeground(2, Qt.GlobalColor.green)
        else:
            QMessageBox.information(self, "Info", f"{type_} server implementation placeholder.")

    def stop_server(self):
        item = self.tree.currentItem()
        if not item: return
        port = int(item.text(1))
        
        if port in self.threads:
            self.threads[port].stop()
            self.threads[port].wait()
            del self.threads[port]
            item.setText(2, "Stopped")
            item.setForeground(2, Qt.GlobalColor.red)

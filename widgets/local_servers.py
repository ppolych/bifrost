from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTreeWidget, QTreeWidgetItem, 
    QLabel, QPushButton, QHBoxLayout, QMessageBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import http.server
import socketserver


class LocalTcpServer(socketserver.TCPServer):
    allow_reuse_address = True


class ServerThread(QThread):
    failed = pyqtSignal(int, str)

    def __init__(self, port):
        super().__init__()
        self.port = port
        self.httpd = None

    def run(self):
        handler = http.server.SimpleHTTPRequestHandler
        try:
            with LocalTcpServer(("127.0.0.1", self.port), handler) as self.httpd:
                self.httpd.serve_forever()
        except Exception as e:
            self.failed.emit(self.port, str(e) or e.__class__.__name__)

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
            thread.failed.connect(self._server_failed)
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

    def _server_failed(self, port: int, error: str):
        thread = self.threads.pop(port, None)
        if thread is not None:
            thread.wait(1000)
        for item in self.items.values():
            if item.text(1) == str(port):
                item.setText(2, "Failed")
                item.setForeground(2, Qt.GlobalColor.red)
                break
        QMessageBox.warning(self, "Local server", f"Failed to start server on 127.0.0.1:{port}\n\n{error}")

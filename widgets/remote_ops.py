from __future__ import annotations

import threading

from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QLabel, QPushButton, QTextEdit, QVBoxLayout, QWidget

from core.remote_ops import REMOTE_ACTIONS, RemoteAction


class RemoteOpsWidget(QWidget):
    result_ready = pyqtSignal(object, object, int, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backend = None
        self._busy = False
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(2, 2, 2, 2)
        self.layout.setSpacing(2)
        self.status = QLabel("Remote Ops: idle")
        self.layout.addWidget(self.status)
        self.buttons: list[QPushButton] = []
        for action in REMOTE_ACTIONS:
            button = QPushButton(action.label)
            button.setProperty("compact", True)
            button.setStyleSheet("text-align: left;")
            button.clicked.connect(lambda _checked=False, a=action: self.run_action(a))
            self.layout.addWidget(button)
            self.buttons.append(button)
        self.output = QTextEdit()
        self.output.setReadOnly(True)
        self.layout.addWidget(self.output, 1)
        self.result_ready.connect(self._apply_result)
        self.set_backend(None)

    def set_backend(self, backend) -> None:
        self._backend = backend
        self._set_enabled(backend is not None and not self._busy)
        self.status.setText("Remote Ops: connected" if backend is not None else "Remote Ops: idle")

    def run_action(self, action: RemoteAction) -> None:
        backend = self._backend
        if backend is None or self._busy:
            return
        self._busy = True
        self._set_enabled(False)
        self.status.setText(f"Running: {action.label}")
        self.output.setPlainText(f"$ {action.command}\n")
        threading.Thread(target=self._worker, args=(backend, action), daemon=True).start()

    def _worker(self, backend, action: RemoteAction) -> None:
        try:
            code, out, err = backend.exec_command_text(action.command, timeout=action.timeout)
        except Exception as e:
            code, out, err = 255, "", str(e)
        self.result_ready.emit(backend, action, code, out, err)

    def _apply_result(self, backend, action: RemoteAction, code: int, out: str, err: str) -> None:
        if backend is not self._backend:
            return
        self._busy = False
        self._set_enabled(True)
        self.status.setText(f"{action.label}: exit {code}")
        parts = [f"$ {action.command}", out.rstrip()]
        if err.strip():
            parts.extend(["", "stderr:", err.rstrip()])
        self.output.setPlainText("\n".join(part for part in parts if part))

    def _set_enabled(self, enabled: bool) -> None:
        for button in self.buttons:
            button.setEnabled(enabled)

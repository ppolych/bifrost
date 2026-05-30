from __future__ import annotations

import threading
import time

from PyQt6.QtCore import QTimer, pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QWidget

from core.remote_monitor import (
    REMOTE_MONITOR_COMMAND,
    format_bytes,
    format_rate,
    format_remote_monitor_details,
    parse_remote_monitor_output,
)


class RemoteMonitorWidget(QWidget):
    metrics_ready = pyqtSignal(object, dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._backend = None
        self._polling = False
        self._last_net: tuple[int, int, float] | None = None
        self._last_metrics: dict[str, object] | None = None
        self._last_down_rate: float | None = None
        self._last_up_rate: float | None = None

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 0, 4, 0)
        layout.setSpacing(3)

        self.host_label = self._make_cell("Remote: idle", "#cccccc")
        self.cpu_label = self._make_cell("CPU: --", "#8bd17c")
        self.mem_label = self._make_cell("RAM: --", "#7ee6a8")
        self.up_label = self._make_cell("UP: --", "#22c55e")
        self.down_label = self._make_cell("DN: --", "#60a5fa")
        self.uptime_label = self._make_cell("Uptime: --", "#d9e2ec")
        self.disk_label = self._make_cell("Disk: --", "#f59e0b")
        for label in (
            self.host_label,
            self.cpu_label,
            self.mem_label,
            self.up_label,
            self.down_label,
            self.uptime_label,
            self.disk_label,
        ):
            layout.addWidget(label)
        layout.addStretch()

        self._timer = QTimer(self)
        self._timer.setInterval(5000)
        self._timer.timeout.connect(self._poll)
        self.metrics_ready.connect(self._apply_metrics)
        self._set_tooltip(status="idle")

    def set_backend(self, backend) -> None:
        if backend is self._backend:
            return
        self._backend = backend
        self._last_net = None
        if backend is None:
            self._timer.stop()
            self._set_idle()
            return
        self.host_label.setText("Remote: connecting")
        self._set_tooltip(status="connecting")
        self._timer.start()
        self._poll()

    def _make_cell(self, text: str, color: str) -> QLabel:
        label = QLabel(text)
        label.setStyleSheet(
            "QLabel { background: #171717; border: 1px solid #555; "
            f"color: {color}; padding: 1px 7px; font-size: 10px; }}"
        )
        return label

    def _set_idle(self) -> None:
        self._last_metrics = None
        self._last_down_rate = None
        self._last_up_rate = None
        self.host_label.setText("Remote: idle")
        self.cpu_label.setText("CPU: --")
        self.mem_label.setText("RAM: --")
        self.up_label.setText("UP: --")
        self.down_label.setText("DN: --")
        self.uptime_label.setText("Uptime: --")
        self.disk_label.setText("Disk: --")
        self._set_tooltip(status="idle")

    def _set_tooltip(self, status: str | None = None) -> None:
        tooltip = format_remote_monitor_details(
            self._last_metrics,
            down_rate=self._last_down_rate,
            up_rate=self._last_up_rate,
            status=status,
        )
        self.setToolTip(tooltip)
        self.host_label.setToolTip(tooltip)
        if status or not self._last_metrics or self._last_metrics.get("error"):
            for label in (
                self.cpu_label,
                self.mem_label,
                self.up_label,
                self.down_label,
                self.uptime_label,
                self.disk_label,
            ):
                label.setToolTip(tooltip)
            return

        metrics = self._last_metrics
        self.cpu_label.setToolTip(
            "\n".join(
                [
                    "CPU",
                    f"Usage: {metrics.get('cpu') or '--'}",
                    f"Host: {metrics.get('host') or 'Remote'}",
                ]
            )
        )
        self.mem_label.setToolTip(
            "\n".join(
                [
                    "Memory",
                    f"Used / total: {metrics.get('mem') or '--'}",
                    f"Host: {metrics.get('host') or 'Remote'}",
                ]
            )
        )
        self.up_label.setToolTip(
            "\n".join(
                [
                    "Network upload",
                    f"Current rate: {format_rate(self._last_up_rate or 0)}",
                    f"Total sent: {self._format_net_total(1)}",
                ]
            )
        )
        self.down_label.setToolTip(
            "\n".join(
                [
                    "Network download",
                    f"Current rate: {format_rate(self._last_down_rate or 0)}",
                    f"Total received: {self._format_net_total(0)}",
                ]
            )
        )
        uptime = str(metrics.get("uptime") or "--").replace("up ", "")
        self.uptime_label.setToolTip("\n".join(["Uptime", f"Remote uptime: {uptime}"]))
        disks = metrics.get("disk") or []
        disk_lines = ["Disk usage", *(str(disk) for disk in disks)] if disks else ["Disk usage", "--"]
        self.disk_label.setToolTip("\n".join(disk_lines))

    def _format_net_total(self, index: int) -> str:
        net = self._last_metrics.get("net") if self._last_metrics else None
        if not isinstance(net, tuple) or len(net) <= index:
            return "--"
        return format_bytes(net[index])

    def _poll(self) -> None:
        backend = self._backend
        if backend is None or self._polling:
            return
        if getattr(backend, "_closed", False) or not backend.wait_ready(timeout=0):
            return
        if backend.connect_error is not None or backend.client is None:
            self.host_label.setText("Remote: unavailable")
            self._set_tooltip(status="unavailable")
            return
        self._polling = True
        threading.Thread(target=self._poll_worker, args=(backend,), daemon=True).start()

    def _poll_worker(self, backend) -> None:
        metrics: dict[str, object] = {}
        try:
            _stdin, stdout, _stderr = backend.client.exec_command(
                REMOTE_MONITOR_COMMAND,
                timeout=4,
            )
            output = stdout.read().decode(errors="replace")
            metrics = parse_remote_monitor_output(output)
        except Exception as e:
            metrics = {"error": str(e)}
        finally:
            self.metrics_ready.emit(backend, metrics)

    def _apply_metrics(self, backend, metrics: dict) -> None:
        self._polling = False
        if backend is not self._backend:
            return
        if metrics.get("error"):
            self._last_metrics = metrics
            self.host_label.setText("Remote: monitor error")
            self._set_tooltip()
            return

        self._last_metrics = metrics
        self.host_label.setText(str(metrics.get("host") or "Remote"))
        self.cpu_label.setText(f"CPU: {metrics.get('cpu', '--')}")
        self.mem_label.setText(f"RAM: {metrics.get('mem', '--')}")
        self.uptime_label.setText(str(metrics.get("uptime") or "Uptime: --").replace("up ", ""))
        disks = metrics.get("disk") or []
        self.disk_label.setText("Disk: " + " ".join(disks[:3]) if disks else "Disk: --")

        net = metrics.get("net")
        if isinstance(net, tuple):
            now = time.monotonic()
            rx, tx = net
            if self._last_net is None:
                down_rate = 0.0
                up_rate = 0.0
            else:
                last_rx, last_tx, last_time = self._last_net
                elapsed = max(now - last_time, 0.001)
                down_rate = max(rx - last_rx, 0) / elapsed
                up_rate = max(tx - last_tx, 0) / elapsed
            self._last_net = (rx, tx, now)
            self._last_down_rate = down_rate
            self._last_up_rate = up_rate
            self.down_label.setText(f"DN: {format_rate(down_rate)}")
            self.up_label.setText(f"UP: {format_rate(up_rate)}")
        self._set_tooltip()

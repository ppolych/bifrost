from PyQt6.QtCore import Qt

from core.remote_monitor import format_remote_monitor_details
from core.remote_monitor_health import freshness_text
from widgets.remote_monitor_menu import build_monitor_menu, copy_details, show_details


class RemoteMonitorActionsMixin:
    def details_text(self) -> str:
        details = format_remote_monitor_details(
            self._last_metrics,
            down_rate=self._last_down_rate,
            up_rate=self._last_up_rate,
            status="paused" if self.paused and not self._last_metrics else None,
        )
        return f"{details}\nFreshness: {freshness_text(self._last_updated_at)}"

    def refresh_now(self) -> None:
        was_paused = self.paused
        self.paused = False
        self._poll()
        self.paused = was_paused
        self._update_freshness()

    def toggle_pause(self) -> None:
        self.paused = not self.paused
        if self.paused:
            self._timer.stop()
        elif self._backend is not None:
            self._timer.start()
            self._poll()
        self._update_freshness()

    def set_poll_interval(self, interval_ms: int) -> None:
        self._timer.setInterval(max(1000, int(interval_ms)))
        if self._backend is not None and not self.paused:
            self._timer.start()

    def copy_details(self) -> None:
        copy_details(self.details_text())

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            show_details(self, self.details_text())
            return
        super().mouseDoubleClickEvent(event)

    def _show_context_menu(self, pos) -> None:
        build_monitor_menu(self).exec(self.mapToGlobal(pos))

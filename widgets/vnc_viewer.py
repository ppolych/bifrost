"""VNC viewer widget.

Hosts a `core.vnc_client.VncClient` and paints its framebuffer, scaled to the
widget while preserving aspect ratio. Client callbacks arrive on the worker
thread and are bridged to the GUI thread via queued signals. Mouse and
keyboard input is translated to RFB pointer/key events (Qt keys → X11
keysyms).
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter
from PyQt6.QtWidgets import QWidget

from core.vnc_client import VncClient

log = logging.getLogger(__name__)


# Qt key → X11 keysym for non-printable keys.
_KEYSYMS = {
    Qt.Key.Key_Return: 0xFF0D,
    Qt.Key.Key_Enter: 0xFF8D,
    Qt.Key.Key_Backspace: 0xFF08,
    Qt.Key.Key_Tab: 0xFF09,
    Qt.Key.Key_Backtab: 0xFF09,  # Qt reports Shift+Tab as Backtab; Shift goes separately
    Qt.Key.Key_Escape: 0xFF1B,
    Qt.Key.Key_Insert: 0xFF63,
    Qt.Key.Key_Delete: 0xFFFF,
    Qt.Key.Key_Home: 0xFF50,
    Qt.Key.Key_End: 0xFF57,
    Qt.Key.Key_PageUp: 0xFF55,
    Qt.Key.Key_PageDown: 0xFF56,
    Qt.Key.Key_Left: 0xFF51,
    Qt.Key.Key_Up: 0xFF52,
    Qt.Key.Key_Right: 0xFF53,
    Qt.Key.Key_Down: 0xFF54,
    Qt.Key.Key_Shift: 0xFFE1,
    Qt.Key.Key_Control: 0xFFE3,
    Qt.Key.Key_Alt: 0xFFE9,
    Qt.Key.Key_AltGr: 0xFFEA,
    Qt.Key.Key_Meta: 0xFFEB,
    Qt.Key.Key_CapsLock: 0xFFE5,
    Qt.Key.Key_F1: 0xFFBE, Qt.Key.Key_F2: 0xFFBF, Qt.Key.Key_F3: 0xFFC0,
    Qt.Key.Key_F4: 0xFFC1, Qt.Key.Key_F5: 0xFFC2, Qt.Key.Key_F6: 0xFFC3,
    Qt.Key.Key_F7: 0xFFC4, Qt.Key.Key_F8: 0xFFC5, Qt.Key.Key_F9: 0xFFC6,
    Qt.Key.Key_F10: 0xFFC7, Qt.Key.Key_F11: 0xFFC8, Qt.Key.Key_F12: 0xFFC9,
}


def qt_event_to_keysym(event) -> int | None:
    """Map a Qt key event to an X11 keysym, or None if unmappable."""
    keysym = _KEYSYMS.get(event.key())
    if keysym is not None:
        return keysym
    text = event.text()
    if len(text) == 1:
        code = ord(text)
        if 0x20 <= code <= 0xFF:
            return code
        if code > 0xFF:  # X11 rule for general unicode
            return 0x01000000 + code
    # Control-modified printables: Qt reports the control character ("\x01"
    # for Ctrl+A), but the server wants the plain key keysym alongside the
    # Control press it already received. Qt printable key codes are ASCII
    # (letters uppercase), so map back to the character.
    key = event.key()
    if 0x20 <= key <= 0x7E:
        if ord("A") <= key <= ord("Z") and not (
            event.modifiers() & Qt.KeyboardModifier.ShiftModifier
        ):
            return key + 0x20  # unshifted → lowercase keysym
        return key
    return None


class VncViewer(QWidget):
    _frame_arrived = pyqtSignal()
    _client_resized = pyqtSignal(int, int)
    _client_connected = pyqtSignal(str)
    _client_errored = pyqtSignal(str)
    _client_closed = pyqtSignal()

    def __init__(self, host: str, port: int = 5900, password: str | None = None, settings=None):
        super().__init__()
        self.settings = settings
        self._status: str | None = f"Connecting to {host}:{port}..."
        self._button_mask = 0
        # Cached framebuffer copy for painting; refreshed only when the client
        # reports a new frame, not on every repaint (status text, resize, ...).
        self._paint_buf = b""
        self._paint_size = (0, 0)
        self._frame_dirty = True

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        self._frame_arrived.connect(self._on_frame)
        self._client_resized.connect(self._on_resized)
        self._client_connected.connect(self._on_connected)
        self._client_errored.connect(self._on_errored)
        self._client_closed.connect(self._on_closed)

        self.client = VncClient(
            host,
            port,
            password,
            on_connected=self._client_connected.emit,
            on_resize=self._client_resized.emit,
            on_frame=self._frame_arrived.emit,
            on_error=self._client_errored.emit,
            on_closed=self._client_closed.emit,
        )
        self.client.start()

    # ----- client state (GUI thread) -----

    def _on_connected(self, name: str):
        self._status = None
        self.setToolTip(name)
        self.update()

    def _on_frame(self):
        self._frame_dirty = True
        self.update()

    def _on_resized(self, _w: int, _h: int):
        self._frame_dirty = True
        self.updateGeometry()
        self.update()

    def _on_errored(self, message: str):
        self._status = f"VNC connection failed: {message}"
        self.update()

    def _on_closed(self):
        if self._status is None:
            self._status = "Disconnected."
        self.update()

    def shutdown(self) -> None:
        self.client.close()
        # Don't return while the worker can still fire callbacks: the caller
        # may delete this widget right after, and a late signal emit on a
        # destroyed QObject segfaults.
        self.client.join(timeout=3.0)

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

    # ----- painting -----

    def sizeHint(self) -> QSize:
        w, h = self.client.size()
        return QSize(w or 800, h or 600)

    def _target_rect(self, fb_w: int, fb_h: int) -> QRect:
        """Largest aspect-preserving rect for the framebuffer, centered."""
        if fb_w <= 0 or fb_h <= 0:
            return QRect()
        scale = min(self.width() / fb_w, self.height() / fb_h)
        w = max(1, int(fb_w * scale))
        h = max(1, int(fb_h * scale))
        return QRect((self.width() - w) // 2, (self.height() - h) // 2, w, h)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#000000"))
        if self._frame_dirty:
            # snapshot() copies under the client's lock, so the frame can't be
            # torn by a concurrent blit on the worker thread.
            self._paint_buf, w, h = self.client.snapshot()
            self._paint_size = (w, h)
            self._frame_dirty = False
        fb_w, fb_h = self._paint_size
        if fb_w > 0 and fb_h > 0 and len(self._paint_buf) >= fb_w * fb_h * 4:
            # QImage does not copy the buffer; it must stay referenced on self
            # so it outlives the paint (dropping it mid-paint segfaults).
            image = QImage(self._paint_buf, fb_w, fb_h, fb_w * 4, QImage.Format.Format_RGBX8888)
            painter.drawImage(self._target_rect(fb_w, fb_h), image)
        if self._status:
            painter.setPen(QColor("#cccccc"))
            painter.drawText(
                self.rect(), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, self._status
            )
        painter.end()

    # ----- input -----

    def _pos_to_fb(self, pos) -> tuple[int, int] | None:
        fb_w, fb_h = self.client.size()
        target = self._target_rect(fb_w, fb_h)
        if target.isEmpty():
            return None
        x = (pos.x() - target.x()) * fb_w / target.width()
        y = (pos.y() - target.y()) * fb_h / target.height()
        return (
            max(0, min(fb_w - 1, int(x))),
            max(0, min(fb_h - 1, int(y))),
        )

    _BUTTON_BITS = {
        Qt.MouseButton.LeftButton: 1,
        Qt.MouseButton.MiddleButton: 2,
        Qt.MouseButton.RightButton: 4,
    }

    def _send_pointer(self, pos):
        fb_pos = self._pos_to_fb(pos)
        if fb_pos is not None:
            self.client.send_pointer(fb_pos[0], fb_pos[1], self._button_mask)

    def mousePressEvent(self, event):
        self.setFocus()
        self._button_mask |= self._BUTTON_BITS.get(event.button(), 0)
        self._send_pointer(event.position().toPoint())

    def mouseReleaseEvent(self, event):
        self._button_mask &= ~self._BUTTON_BITS.get(event.button(), 0)
        self._send_pointer(event.position().toPoint())

    def mouseMoveEvent(self, event):
        self._send_pointer(event.position().toPoint())

    def wheelEvent(self, event):
        fb_pos = self._pos_to_fb(event.position().toPoint())
        if fb_pos is None:
            return
        bit = 8 if event.angleDelta().y() > 0 else 16  # buttons 4/5
        self.client.send_pointer(fb_pos[0], fb_pos[1], self._button_mask | bit)
        self.client.send_pointer(fb_pos[0], fb_pos[1], self._button_mask)

    def focusNextPrevChild(self, _next: bool) -> bool:
        # Keep Tab/Shift+Tab as input to the remote desktop instead of letting
        # Qt move focus (same contract as TerminalWidget).
        return False

    def keyPressEvent(self, event):
        keysym = qt_event_to_keysym(event)
        if keysym is not None:
            self.client.send_key(keysym, True)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        keysym = qt_event_to_keysym(event)
        if keysym is not None:
            self.client.send_key(keysym, False)
            return
        super().keyReleaseEvent(event)

"""pyte-backed VT100/xterm terminal widget.

Renders pyte's screen buffer to a QAbstractScrollArea viewport with custom
QPainter drawing — replaces the old QPlainTextEdit + regex highlighter approach
which couldn't handle ANSI escape sequences and so broke vim/htop/less.

External signal API (`key_pressed`, `detach_requested`) and `write_to_backend`
are preserved so multi-exec broadcast and macro replay continue to work.
"""

from __future__ import annotations

import datetime
import logging
import os

import pyte
from PyQt6.QtCore import Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QFontMetricsF
from PyQt6.QtWidgets import QAbstractScrollArea, QApplication

from core.platform_utils import default_monospace_font
from core.terminal_backend import TerminalBackend, TerminalReader
from widgets.sftp_utils import safe_local_name
from widgets.terminal_clipboard import TerminalClipboardMixin, detect_paste_risks
from widgets.terminal_keyboard import TerminalKeyboardMixin
from widgets.terminal_paint import TerminalPaintMixin
from widgets.terminal_palette import (
    DEFAULT_BG, DEFAULT_FG, BRACKETED_PASTE_DISABLE, BRACKETED_PASTE_ENABLE,
)
from widgets.terminal_selection import TerminalSelectionMixin

log = logging.getLogger(__name__)




class TerminalWidget(
    TerminalKeyboardMixin,
    TerminalSelectionMixin,
    TerminalPaintMixin,
    TerminalClipboardMixin,
    QAbstractScrollArea,
):
    """Real VT terminal. Public API mirrors the old QPlainTextEdit-based widget."""

    key_pressed = pyqtSignal(str)
    detach_requested = pyqtSignal()
    search_requested = pyqtSignal()

    DEFAULT_COLS = 80
    DEFAULT_ROWS = 24

    def __init__(self, command=None, settings=None, log_name: str = "session", backend=None):
        """Construct a terminal.

        Pass `backend=` to use a pre-built backend (e.g. ParamikoBackend for SSH).
        Otherwise a default TerminalBackend(command) is created.
        """
        super().__init__()
        self.settings = settings or {
            "right_click_paste": True,
            "font": default_monospace_font(10),
            "term_bg": DEFAULT_BG,
            "term_fg": DEFAULT_FG,
            "auto_log": False,
            "scrollback": 5000,
            "cursor_blink": True,
        }

        self.log_file = None
        if self.settings.get("auto_log"):
            log_dir = os.path.expanduser(self.settings.get("log_directory") or "logs")
            try:
                os.makedirs(log_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                safe_name = safe_local_name(log_name, default="session")
                log_path = os.path.join(log_dir, f"{safe_name}_{timestamp}.log")
                self.log_file = open(log_path, "a", encoding="utf-8")
            except OSError:
                log.exception("Failed to open session log file")
                self.log_file = None

        # Visual-bell flash state
        self._visual_bell_active = False
        self._visual_bell_timer = QTimer(self)
        self._visual_bell_timer.setSingleShot(True)
        self._visual_bell_timer.timeout.connect(self._end_visual_bell)

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

        self._char_w = 8.0
        self._char_h = 16.0
        self._baseline = 12.0
        self._cols = self.DEFAULT_COLS
        self._rows = self.DEFAULT_ROWS

        # pyte state
        self.screen = pyte.HistoryScreen(
            columns=self._cols,
            lines=self._rows,
            history=int(self.settings.get("scrollback", 5000)),
            ratio=0.5,
        )
        # Route pyte's bell() through our handler so we can honor bell_mode.
        # bell() is called from `\a` (0x07) in the input stream.
        self.screen.bell = self._on_bell  # type: ignore[method-assign]
        self.stream = pyte.ByteStream(self.screen)

        # cursor blink
        self._cursor_visible = True
        self._blink_timer = QTimer(self)
        self._blink_timer.timeout.connect(self._toggle_cursor)

        # Selection — (row1, col1, row2, col2) in *absolute* line coords, or
        # None. Absolute row = len(history.top) + visible row, so a selection
        # is anchored to content: it survives scrolling and new output, and can
        # span scrollback. Normalized via _normalized_selection() at use sites
        # so backwards drags work transparently.
        self._selection: tuple[int, int, int, int] | None = None
        self._dragging = False

        self._last_search_text = ""
        self._search_index = -1
        self._bracketed_paste = bool(self.settings.get("bracketed_paste", True))

        self._apply_font_metrics()
        self.apply_settings()

        # Backend + reader thread
        self.backend = backend if backend is not None else TerminalBackend(command)
        try:
            self.backend.start()
        except Exception:
            log.exception("Failed to start terminal backend")
            self._append_error_text("[failed to start backend — see bifrost.log]\r\n")
            self.backend = None
            self.reader = None
            return

        self.reader = TerminalReader(self.backend, parent=self)
        self.reader.data_received.connect(self._on_data)
        self.reader.closed.connect(self._on_backend_closed)
        self.reader.start()

    # ----- size / metrics -----

    def _apply_font_metrics(self):
        font = self.settings["font"]
        self.setFont(font)
        fm = QFontMetricsF(font)
        self._char_w = max(1.0, fm.horizontalAdvance("M"))
        self._char_h = max(1.0, fm.height())
        self._baseline = fm.ascent()

    def apply_settings(self):
        self._apply_font_metrics()
        bg = self.settings.get("term_bg", DEFAULT_BG)
        if getattr(self, "_broadcast_mode", False):
            bg = "#1a0000"
        self.viewport().setStyleSheet(f"background-color: {bg};")
        if self.settings.get("cursor_blink", True):
            if not self._blink_timer.isActive():
                self._blink_timer.start(500)
        else:
            self._blink_timer.stop()
            self._cursor_visible = True
        self._resize_screen_to_widget()
        self.viewport().update()

    def sizeHint(self) -> QSize:
        return QSize(int(self._char_w * 80) + 20, int(self._char_h * 24) + 4)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._resize_screen_to_widget()

    def _resize_screen_to_widget(self):
        w = self.viewport().width()
        h = self.viewport().height()
        cols = max(1, int(w / self._char_w))
        rows = max(1, int(h / self._char_h))
        if cols == self._cols and rows == self._rows:
            return
        self._cols = cols
        self._rows = rows
        try:
            self.screen.resize(rows, cols)
        except Exception:
            log.exception("pyte screen resize failed (%dx%d)", cols, rows)
        if hasattr(self, "backend") and self.backend is not None:
            try:
                self.backend.set_winsize(rows, cols)
            except OSError:
                log.exception("set_winsize failed")
        self._update_scrollbar()

    # ----- data in / out -----

    def _on_data(self, data: bytes):
        self._track_terminal_modes(data)
        try:
            self.stream.feed(data)
        except Exception:
            log.exception("pyte feed failed")
            return
        if self.log_file is not None:
            try:
                self.log_file.write(data.decode(errors="replace"))
                self.log_file.flush()
            except OSError:
                log.exception("session log write failed")
        self._update_scrollbar()
        self.viewport().update()

    def _track_terminal_modes(self, data: bytes) -> None:
        if BRACKETED_PASTE_ENABLE in data:
            self._bracketed_paste = True
        if BRACKETED_PASTE_DISABLE in data:
            self._bracketed_paste = False

    def _on_backend_closed(self):
        self._append_error_text("\r\n[session closed]\r\n")
        self.viewport().update()

    def _append_error_text(self, text: str):
        try:
            self.stream.feed(text.encode())
        except Exception:
            log.exception("error text feed failed")

    def set_broadcast_mode(self, enabled: bool):
        """Visual indicator for MultiExec mode — red-tinted viewport."""
        self._broadcast_mode = bool(enabled)
        self.apply_settings()

    def write_to_backend(self, text):
        if not hasattr(self, "backend") or self.backend is None:
            return
        try:
            self.backend.write(text.encode() if isinstance(text, str) else text)
        except Exception:
            log.exception("backend write failed")

    def shutdown(self) -> None:
        reader = getattr(self, "reader", None)
        if reader is not None:
            try:
                reader.stop()
            except Exception:
                log.exception("reader stop failed")
            self.reader = None
        backend = getattr(self, "backend", None)
        if backend is not None:
            try:
                backend.close()
            except Exception:
                log.exception("backend close failed")
        if self.log_file is not None:
            try:
                self.log_file.close()
            except OSError:
                pass
            self.log_file = None

    def _toggle_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.viewport().update()

    def _on_bell(self):
        mode = self.settings.get("bell_mode", "beep")
        if mode == "off":
            return
        if mode == "visual":
            self._visual_bell_active = True
            self._visual_bell_timer.start(120)
            self.viewport().update()
        else:
            QApplication.beep()

    def _end_visual_bell(self):
        self._visual_bell_active = False
        self.viewport().update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.viewport().update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.viewport().update()

    # ----- shutdown -----

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)

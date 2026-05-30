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
from PyQt6.QtGui import (
    QAction,
    QColor,
    QFontMetricsF,
    QGuiApplication,
    QPainter,
)
from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QApplication,
    QMenu,
    QMessageBox,
)

from core.platform_utils import default_monospace_font
from core.terminal_backend import TerminalBackend, TerminalReader

log = logging.getLogger(__name__)


# xterm 16-color palette (named colors from pyte map here).
ANSI_COLORS = {
    "black":   "#000000",
    "red":     "#cc0000",
    "green":   "#4e9a06",
    "brown":   "#c4a000",
    "yellow":  "#c4a000",
    "blue":    "#3465a4",
    "magenta": "#75507b",
    "cyan":    "#06989a",
    "white":   "#d3d7cf",
    # bright variants used when the cell is bold
    "brightblack":   "#555753",
    "brightred":     "#ef2929",
    "brightgreen":   "#8ae234",
    "brightbrown":   "#fce94f",
    "brightyellow":  "#fce94f",
    "brightblue":    "#729fcf",
    "brightmagenta": "#ad7fa8",
    "brightcyan":    "#34e2e2",
    "brightwhite":   "#eeeeec",
}

DEFAULT_FG = "#d3d7cf"
DEFAULT_BG = "#000000"


def _resolve_color(value: str, default: str, bold: bool = False) -> QColor:
    """Map a pyte color spec to a QColor.

    pyte gives us: 'default', named colors ('red'), or 6-char hex without '#'.
    """
    if not value or value == "default":
        return QColor(default)
    if bold and value in ANSI_COLORS and not value.startswith("bright"):
        bright = "bright" + value
        if bright in ANSI_COLORS:
            return QColor(ANSI_COLORS[bright])
    if value in ANSI_COLORS:
        return QColor(ANSI_COLORS[value])
    if len(value) == 6 and all(c in "0123456789abcdefABCDEF" for c in value):
        return QColor("#" + value)
    return QColor(default)


class TerminalWidget(QAbstractScrollArea):
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
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                log_path = os.path.join(log_dir, f"{log_name}_{timestamp}.log")
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

        # Selection — (row1, col1, row2, col2) in visible-buffer coords, or None.
        # Normalized via _normalized_selection() at use sites so backwards drags
        # work transparently.
        self._selection: tuple[int, int, int, int] | None = None
        self._dragging = False

        self._last_search_text = ""
        self._search_index = -1

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

    # ----- keyboard -----

    _SPECIAL_KEYS = {
        Qt.Key.Key_Return: b"\r",
        Qt.Key.Key_Enter: b"\r",
        Qt.Key.Key_Backspace: b"\x7f",
        Qt.Key.Key_Tab: b"\t",
        # Qt emits Key_Backtab (not Key_Tab + Shift) when Shift+Tab is pressed.
        # \x1b[Z is the standard back-tab CSI sequence shells and full-screen
        # apps recognize.
        Qt.Key.Key_Backtab: b"\x1b[Z",
        Qt.Key.Key_Escape: b"\x1b",
        Qt.Key.Key_Up: b"\x1b[A",
        Qt.Key.Key_Down: b"\x1b[B",
        Qt.Key.Key_Right: b"\x1b[C",
        Qt.Key.Key_Left: b"\x1b[D",
        Qt.Key.Key_Home: b"\x1b[H",
        Qt.Key.Key_End: b"\x1b[F",
        Qt.Key.Key_PageUp: b"\x1b[5~",
        Qt.Key.Key_PageDown: b"\x1b[6~",
        Qt.Key.Key_Delete: b"\x1b[3~",
        Qt.Key.Key_Insert: b"\x1b[2~",
        Qt.Key.Key_F1: b"\x1bOP",
        Qt.Key.Key_F2: b"\x1bOQ",
        Qt.Key.Key_F3: b"\x1bOR",
        Qt.Key.Key_F4: b"\x1bOS",
        Qt.Key.Key_F5: b"\x1b[15~",
        Qt.Key.Key_F6: b"\x1b[17~",
        Qt.Key.Key_F7: b"\x1b[18~",
        Qt.Key.Key_F8: b"\x1b[19~",
        Qt.Key.Key_F9: b"\x1b[20~",
        Qt.Key.Key_F10: b"\x1b[21~",
        Qt.Key.Key_F11: b"\x1b[23~",
        Qt.Key.Key_F12: b"\x1b[24~",
    }

    def focusNextPrevChild(self, _next):
        # Qt's default would consume Tab and Shift+Tab to move focus between
        # widgets, never delivering them to keyPressEvent. Returning False
        # disables that focus-traversal so the terminal sees Tab as input.
        return False

    def keyPressEvent(self, event):
        mods = event.modifiers()
        key = event.key()

        # Ctrl+Shift+C / V: copy selection / paste from clipboard.
        if mods == Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier:
            if key == Qt.Key.Key_C:
                if not self._copy_selection():
                    # No selection — fall back to copying the visible viewport,
                    # which matches the old behaviour and is occasionally useful.
                    self._copy_visible()
                return
            if key == Qt.Key.Key_V:
                self._paste_from_clipboard()
                return

        # Ctrl + letter → control character
        if mods & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            byte = bytes([key - Qt.Key.Key_A + 1])
            self._emit_and_send(byte)
            return

        if key in self._SPECIAL_KEYS:
            self._emit_and_send(self._SPECIAL_KEYS[key])
            return

        text = event.text()
        if text:
            self._emit_and_send(text.encode())
            return

        super().keyPressEvent(event)

    def _emit_and_send(self, data: bytes):
        # Emit as str for the key_pressed signal (macro engine + multi-exec).
        # Multi-exec rebroadcasts via write_to_backend, which encodes back to bytes.
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        self.key_pressed.emit(text)
        # Note: do NOT also call self.backend.write here — BifrostApp.on_terminal_key
        # routes back via sender().write_to_backend, preserving multi-exec semantics.

    # ----- mouse / scroll -----

    def wheelEvent(self, event):
        # angleDelta() is in 1/8 degree units; 120 = one notch.
        delta = event.angleDelta().y()
        if delta == 0:
            return
        notches = max(1, abs(delta) // 120)
        per_notch = max(1, int(self.settings.get("wheel_lines", 3)))
        steps = notches * per_notch
        try:
            for _ in range(steps):
                if delta > 0:
                    self.screen.prev_page()
                else:
                    self.screen.next_page()
        except Exception:
            log.exception("scrollback paging failed")
        self.viewport().update()

    # ----- mouse selection -----

    # Characters treated as part of a "word" for double-click selection.
    # The set is deliberately wide so things like file paths, URLs, IPs, and
    # `user@host:port` get grabbed in one double-click.
    _WORD_EXTRA = set("_-./:~@+=%?#&")

    def _is_word_char(self, ch: str) -> bool:
        return bool(ch) and (ch.isalnum() or ch in self._WORD_EXTRA)

    def _pos_to_cell(self, pos) -> tuple[int, int]:
        col = max(0, min(self._cols - 1, int(pos.x() / self._char_w)))
        row = max(0, min(self._rows - 1, int(pos.y() / self._char_h)))
        return row, col

    def _normalized_selection(self) -> tuple[int, int, int, int] | None:
        """Return selection with (r1,c1) <= (r2,c2) in reading order, or None.

        The end position is *exclusive* — `c2` is one past the last selected
        column, which matches how text extraction wants to slice.
        """
        if self._selection is None:
            return None
        r1, c1, r2, c2 = self._selection
        if (r1, c1) > (r2, c2):
            r1, c1, r2, c2 = r2, c2, r1, c1
        # Make c2 exclusive: when the drag ends mid-cell we still want that
        # cell included.
        c2 = c2 + 1
        return r1, c1, r2, c2

    def _in_selection(self, row: int, col: int) -> bool:
        sel = self._normalized_selection()
        if sel is None:
            return False
        r1, c1, r2, c2 = sel
        if row < r1 or row > r2:
            return False
        if r1 == r2:
            return c1 <= col < c2
        if row == r1:
            return col >= c1
        if row == r2:
            return col < c2
        return True

    def has_selection(self) -> bool:
        return self._selection is not None

    def clear_selection(self) -> None:
        if self._selection is not None:
            self._selection = None
            self.viewport().update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            row, col = self._pos_to_cell(event.position().toPoint())
            self._selection = (row, col, row, col)
            self._dragging = True
            self.viewport().update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._selection is not None:
            row, col = self._pos_to_cell(event.position().toPoint())
            r1, c1, _, _ = self._selection
            self._selection = (r1, c1, row, col)
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            # Treat a click-without-drag as "clear selection".
            if self._selection is not None and self._selection[:2] == self._selection[2:]:
                self._selection = None
                self.viewport().update()
            elif self.settings.get("copy_on_select"):
                self._copy_selection()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            row, col = self._pos_to_cell(event.position().toPoint())
            self._select_word_at(row, col)
            return
        super().mouseDoubleClickEvent(event)

    def _select_word_at(self, row: int, col: int) -> None:
        line = self.screen.buffer[row]
        if not self._is_word_char(line[col].data or ""):
            return  # clicked on whitespace; ignore
        left = col
        while left > 0 and self._is_word_char(line[left - 1].data or ""):
            left -= 1
        right = col
        while right < self._cols - 1 and self._is_word_char(line[right + 1].data or ""):
            right += 1
        self._selection = (row, left, row, right)
        self.viewport().update()

    def selected_text(self) -> str:
        """Extract selected text. Each line is rstripped of trailing spaces."""
        sel = self._normalized_selection()
        if sel is None:
            return ""
        r1, c1, r2, c2 = sel
        lines: list[str] = []
        for row in range(r1, r2 + 1):
            line = self.screen.buffer[row]
            start = c1 if row == r1 else 0
            end = c2 if row == r2 else self._cols
            text = "".join(line[c].data or " " for c in range(start, end))
            lines.append(text.rstrip())
        return "\n".join(lines)

    def _copy_selection(self) -> bool:
        text = self.selected_text()
        if not text:
            return False
        QGuiApplication.clipboard().setText(text)
        return True

    def _select_visible(self) -> None:
        self._selection = (0, 0, self._rows - 1, self._cols - 1)
        self.viewport().update()

    def _update_scrollbar(self):
        # HistoryScreen exposes history.top/bottom as deques of lines.
        # We expose a coarse scrollbar so the user sees that scrollback exists.
        history_top = len(self.screen.history.top)
        history_bottom = len(self.screen.history.bottom)
        total = history_top + history_bottom
        bar = self.verticalScrollBar()
        bar.blockSignals(True)
        bar.setRange(0, total)
        bar.setPageStep(max(1, self._rows))
        bar.setSingleStep(1)
        bar.setValue(history_top)
        bar.blockSignals(False)

    # ----- paint -----

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setFont(self.settings["font"])
        painter.fillRect(self.viewport().rect(),
                         QColor(self.settings.get("term_bg", DEFAULT_BG)))

        fg_default = self.settings.get("term_fg", DEFAULT_FG)
        bg_default = self.settings.get("term_bg", DEFAULT_BG)

        # Snapshot the buffer once so we don't mutate during paint.
        buffer = self.screen.buffer
        cursor = self.screen.cursor

        cw, ch = self._char_w, self._char_h

        bold_is_bright = bool(self.settings.get("bold_is_bright", True))
        sel_bg_color = QColor(self.settings.get("selection_bg") or "#3465a4")
        sel_fg_color = QColor(self.settings.get("selection_fg") or "#ffffff")

        for row in range(self._rows):
            line = buffer[row]
            x = 0.0
            y = row * ch
            col = 0
            while col < self._cols:
                cell = line[col]
                ch_text = cell.data or " "
                fg = _resolve_color(cell.fg, fg_default, bold=cell.bold and bold_is_bright)
                bg = _resolve_color(cell.bg, bg_default)
                # Selection uses an explicit selection palette (rather than
                # reverse-video) so the user sees consistent highlight colors
                # over already-reversed text too.
                selected = self._in_selection(row, col)
                if cell.reverse:
                    fg, bg = bg, fg
                if selected:
                    fg, bg = sel_fg_color, sel_bg_color

                # Coalesce contiguous run of cells with the same attrs to reduce draw calls.
                run_text = [ch_text]
                run_end = col + 1
                while run_end < self._cols:
                    nxt = line[run_end]
                    nxt_selected = self._in_selection(row, run_end)
                    if (
                        nxt.fg == cell.fg
                        and nxt.bg == cell.bg
                        and nxt.bold == cell.bold
                        and nxt.reverse == cell.reverse
                        and nxt.underscore == cell.underscore
                        and nxt_selected == selected
                    ):
                        run_text.append(nxt.data or " ")
                        run_end += 1
                    else:
                        break
                run_str = "".join(run_text)
                run_width = cw * (run_end - col)

                if bg.name() != QColor(bg_default).name():
                    painter.fillRect(
                        int(x), int(y),
                        int(run_width) + 1, int(ch) + 1,
                        bg,
                    )
                painter.setPen(fg)
                font = self.settings["font"]
                if cell.bold or cell.italics or cell.underscore:
                    f = painter.font()
                    f.setBold(bool(cell.bold))
                    f.setItalic(bool(cell.italics))
                    f.setUnderline(bool(cell.underscore))
                    painter.setFont(f)
                painter.drawText(int(x), int(y + self._baseline), run_str)
                if cell.bold or cell.italics or cell.underscore:
                    painter.setFont(font)

                x += run_width
                col = run_end

        # Cursor — shape and color from settings.
        cx = cursor.x * cw
        cy = cursor.y * ch
        cursor_color = QColor(self.settings.get("cursor_color") or fg_default)
        shape = (self.settings.get("cursor_shape") or "block").lower()
        if self._cursor_visible and self.hasFocus():
            if shape == "underline":
                painter.fillRect(
                    int(cx), int(cy + ch - 2),
                    max(1, int(cw)), 2, cursor_color,
                )
            elif shape == "bar":
                painter.fillRect(
                    int(cx), int(cy),
                    2, max(1, int(ch)), cursor_color,
                )
            else:  # "block"
                painter.fillRect(
                    int(cx), int(cy),
                    max(1, int(cw)), max(1, int(ch)),
                    cursor_color,
                )
                try:
                    cell = buffer[cursor.y][cursor.x]
                    painter.setPen(QColor(bg_default))
                    painter.drawText(int(cx), int(cy + self._baseline), cell.data or " ")
                except (IndexError, KeyError):
                    pass
        elif not self.hasFocus():
            painter.setPen(cursor_color)
            painter.drawRect(int(cx), int(cy), max(1, int(cw) - 1), max(1, int(ch) - 1))

        # Visual-bell flash — overlay a translucent rect over the whole viewport.
        if self._visual_bell_active:
            overlay = QColor(fg_default)
            overlay.setAlpha(60)
            painter.fillRect(self.viewport().rect(), overlay)

        painter.end()

    def _toggle_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.viewport().update()

    def _on_bell(self):
        """Called by pyte when the stream contains 0x07."""
        mode = self.settings.get("bell_mode", "beep")
        if mode == "off":
            return
        if mode == "visual":
            self._visual_bell_active = True
            self._visual_bell_timer.start(120)
            self.viewport().update()
        else:  # "beep" — system beep via Qt
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

    # ----- context menu / clipboard -----

    def _show_context_menu(self, position):
        menu = QMenu(self)
        has_selection = self.has_selection()
        has_clipboard = bool(QApplication.clipboard().text())

        copy_sel = QAction("Copy", self, triggered=self._copy_selection)
        copy_sel.setShortcut("Ctrl+Shift+C")
        copy_sel.setEnabled(has_selection)
        menu.addAction(copy_sel)

        paste = QAction("Paste", self, triggered=self._paste_from_clipboard)
        paste.setShortcut("Ctrl+Shift+V")
        paste.setEnabled(has_clipboard)
        menu.addAction(paste)

        menu.addSeparator()
        menu.addAction(QAction("Copy visible terminal", self, triggered=self._copy_visible))
        menu.addAction(QAction("Copy visible + scrollback", self, triggered=self._copy_scrollback))
        menu.addAction(QAction("Select visible terminal", self, triggered=self._select_visible))
        clear_sel = QAction("Clear selection", self, triggered=self.clear_selection)
        clear_sel.setEnabled(has_selection)
        menu.addAction(clear_sel)

        menu.addSeparator()
        menu.addAction(QAction("Find...", self, triggered=self.search_requested.emit))
        menu.addAction(QAction("Send Ctrl+C", self, triggered=lambda: self.write_to_backend("\x03")))

        menu.addSeparator()
        menu.addAction(QAction("Detach terminal", self, triggered=self.detach_requested.emit))
        menu.addAction(QAction("Clear scrollback", self, triggered=self._clear_scrollback))
        menu.exec(self.viewport().mapToGlobal(position))

    def search(self, text: str, forward: bool = True) -> int:
        """Search for text in the visible buffer and highlight the result.
        
        Returns the number of matches found.
        """
        if not text:
            self.clear_selection()
            self._last_search_text = ""
            return 0
        
        lines = self._screen_lines()
        matches = []
        for r, line in enumerate(lines):
            start = 0
            while True:
                idx = line.find(text, start)
                if idx == -1:
                    break
                matches.append((r, idx, idx + len(text)))
                start = idx + 1
        
        if not matches:
            self.clear_selection()
            return 0
            
        if text != self._last_search_text:
            self._last_search_text = text
            # Start from the first match if searching forward, last if backward
            self._search_index = 0 if forward else len(matches) - 1
        else:
            if forward:
                self._search_index = (self._search_index + 1) % len(matches)
            else:
                self._search_index = (self._search_index - 1) % len(matches)
        
        r, c1, c2 = matches[self._search_index]
        self._selection = (r, c1, r, c2 - 1)
        self.viewport().update()
        return len(matches)

    def _line_text(self, line) -> str:
        chars = []
        for c in range(self._cols):
            try:
                cell = line[c]
            except (KeyError, IndexError, TypeError):
                chars.append(" ")
                continue
            chars.append(getattr(cell, "data", None) or " ")
        return "".join(chars).rstrip()

    def _screen_lines(self) -> list[str]:
        lines: list[str] = []
        for row in range(self._rows):
            lines.append(self._line_text(self.screen.buffer[row]))
        return lines

    def _copy_visible(self):
        QGuiApplication.clipboard().setText("\n".join(self._screen_lines()).rstrip())

    def _copy_scrollback(self):
        lines: list[str] = []
        for line in list(self.screen.history.top):
            lines.append(self._line_text(line))
        lines.extend(self._screen_lines())
        for line in list(self.screen.history.bottom):
            lines.append(self._line_text(line))
        QGuiApplication.clipboard().setText("\n".join(lines).rstrip())

    def _paste_from_clipboard(self):
        text = QApplication.clipboard().text()
        if not text:
            return
        if self.settings.get("strip_newlines_on_paste"):
            # Collapse CRLF/CR to a single LF; useful when pasting from Windows
            # apps into a unix shell that would otherwise see two newlines.
            text = text.replace("\r\n", "\n").replace("\r", "\n")
        if self._confirm_paste_required(text):
            lines = text.count("\n") + 1
            reply = QMessageBox.question(
                self,
                "Paste into terminal",
                f"Paste {len(text)} characters across {lines} line{'s' if lines != 1 else ''}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self.write_to_backend(text)

    def _confirm_paste_required(self, text: str) -> bool:
        if self.settings.get("confirm_multiline_paste", True) and "\n" in text:
            return True
        if self.settings.get("confirm_large_paste", True):
            try:
                threshold = int(self.settings.get("large_paste_threshold", 2000) or 0)
            except (TypeError, ValueError):
                threshold = 2000
            if threshold > 0 and len(text) >= threshold:
                return True
        return False

    def _clear_scrollback(self):
        try:
            self.screen.reset()
        except Exception:
            log.exception("screen reset failed")
        self._update_scrollbar()
        self.viewport().update()

    # ----- shutdown -----

    def closeEvent(self, event):
        if getattr(self, "reader", None) is not None:
            try:
                self.reader.stop()
            except Exception:
                log.exception("reader stop failed")
        if self.log_file is not None:
            try:
                self.log_file.close()
            except OSError:
                pass
            self.log_file = None
        super().closeEvent(event)

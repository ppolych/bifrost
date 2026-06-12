import logging
from itertools import islice

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QGuiApplication

log = logging.getLogger(__name__)


class TerminalSelectionMixin:
    _WORD_EXTRA = set("_-./:~@+=%?#&")

    def wheelEvent(self, event):
        delta = event.angleDelta().y()
        if delta == 0:
            return
        steps = max(1, abs(delta) // 120) * max(1, int(self.settings.get("wheel_lines", 3)))
        try:
            for _ in range(steps):
                if delta > 0:
                    self.screen.prev_page()
                else:
                    self.screen.next_page()
        except Exception:
            log.exception("scrollback paging failed")
        self.viewport().update()

    def _is_word_char(self, ch: str) -> bool:
        return bool(ch) and (ch.isalnum() or ch in self._WORD_EXTRA)

    def _pos_to_cell(self, pos) -> tuple[int, int]:
        col = max(0, min(self._cols - 1, int(pos.x() / self._char_w)))
        row = max(0, min(self._rows - 1, int(pos.y() / self._char_h)))
        return row, col

    def _history_top_len(self) -> int:
        return len(self.screen.history.top)

    def _iter_abs_lines(self):
        yield from self.screen.history.top
        for row in range(self._rows):
            yield self.screen.buffer[row]
        yield from self.screen.history.bottom

    def _abs_line(self, abs_row: int):
        top = self.screen.history.top
        n_top = len(top)
        if abs_row < 0:
            return None
        if abs_row < n_top:
            return top[abs_row]
        if abs_row < n_top + self._rows:
            return self.screen.buffer[abs_row - n_top]
        idx = abs_row - n_top - self._rows
        if idx < len(self.screen.history.bottom):
            return self.screen.history.bottom[idx]
        return None

    def _normalized_selection(self) -> tuple[int, int, int, int] | None:
        if self._selection is None:
            return None
        r1, c1, r2, c2 = self._selection
        if (r1, c1) > (r2, c2):
            r1, c1, r2, c2 = r2, c2, r1, c1
        return r1, c1, r2, c2 + 1

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
            abs_row = row + self._history_top_len()
            self._selection = (abs_row, col, abs_row, col)
            self._dragging = True
            self.viewport().update()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging and self._selection is not None:
            pos = event.position().toPoint()
            self._autoscroll_during_drag(pos)
            row, col = self._pos_to_cell(pos)
            r1, c1, _, _ = self._selection
            self._selection = (r1, c1, row + self._history_top_len(), col)
            self.viewport().update()
            return
        super().mouseMoveEvent(event)

    def _autoscroll_during_drag(self, pos) -> None:
        try:
            if pos.y() < 0:
                self.screen.prev_page()
            elif pos.y() > self.viewport().height():
                self.screen.next_page()
            else:
                return
        except Exception:
            log.exception("drag autoscroll paging failed")
            return
        self._update_scrollbar()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
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
            return
        left = col
        while left > 0 and self._is_word_char(line[left - 1].data or ""):
            left -= 1
        right = col
        while right < self._cols - 1 and self._is_word_char(line[right + 1].data or ""):
            right += 1
        abs_row = row + self._history_top_len()
        self._selection = (abs_row, left, abs_row, right)
        self.viewport().update()

    def selected_text(self) -> str:
        sel = self._normalized_selection()
        if sel is None:
            return ""
        r1, c1, r2, c2 = sel
        lines: list[str] = []
        for offset, line in enumerate(islice(self._iter_abs_lines(), r1, r2 + 1)):
            row = r1 + offset
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
        top = self._history_top_len()
        self._selection = (top, 0, top + self._rows - 1, self._cols - 1)
        self.viewport().update()

    def _update_scrollbar(self):
        history_top = len(self.screen.history.top)
        total = history_top + len(self.screen.history.bottom)
        bar = self.verticalScrollBar()
        bar.blockSignals(True)
        bar.setRange(0, total)
        bar.setPageStep(max(1, self._rows))
        bar.setSingleStep(1)
        bar.setValue(history_top)
        bar.blockSignals(False)

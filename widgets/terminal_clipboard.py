import logging

from PyQt6.QtGui import QAction, QGuiApplication
from PyQt6.QtWidgets import QApplication, QMenu, QMessageBox

log = logging.getLogger(__name__)


class TerminalClipboardMixin:
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
        if not text:
            self.clear_selection()
            self._last_search_text = ""
            return 0

        matches = []
        for row, line_obj in enumerate(self._iter_abs_lines()):
            line = self._line_text(line_obj)
            start = 0
            while True:
                idx = line.find(text, start)
                if idx == -1:
                    break
                matches.append((row, idx, idx + len(text)))
                start = idx + 1

        if not matches:
            self.clear_selection()
            return 0

        if text != self._last_search_text:
            self._last_search_text = text
            self._search_index = 0 if forward else len(matches) - 1
        elif forward:
            self._search_index = (self._search_index + 1) % len(matches)
        else:
            self._search_index = (self._search_index - 1) % len(matches)

        row, c1, c2 = matches[self._search_index]
        self._selection = (row, c1, row, c2 - 1)
        self._scroll_to_abs_row(row)
        self._update_scrollbar()
        self.viewport().update()
        return len(matches)

    def _scroll_to_abs_row(self, abs_row: int) -> None:
        while True:
            top = self._history_top_len()
            if top <= abs_row < top + self._rows:
                return
            try:
                if abs_row < top:
                    self.screen.prev_page()
                else:
                    self.screen.next_page()
            except Exception:
                log.exception("scroll-to-row paging failed")
                return
            if self._history_top_len() == top:
                return

    def _line_text(self, line) -> str:
        chars = []
        for col in range(self._cols):
            try:
                cell = line[col]
            except (KeyError, IndexError, TypeError):
                chars.append(" ")
                continue
            chars.append(getattr(cell, "data", None) or " ")
        return "".join(chars).rstrip()

    def _screen_lines(self) -> list[str]:
        return [self._line_text(self.screen.buffer[row]) for row in range(self._rows)]

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
        self.write_to_backend(self._format_paste(text))

    def _format_paste(self, text: str) -> str:
        if self._bracketed_paste:
            return f"\x1b[200~{text}\x1b[201~"
        return text

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
        self._selection = None
        self._update_scrollbar()
        self.viewport().update()

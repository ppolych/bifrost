from PyQt6.QtGui import QColor, QPainter

from widgets.terminal_palette import DEFAULT_BG, DEFAULT_FG, resolve_color


class TerminalPaintMixin:
    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setFont(self.settings["font"])
        painter.fillRect(self.viewport().rect(), QColor(self.settings.get("term_bg", DEFAULT_BG)))

        fg_default = self.settings.get("term_fg", DEFAULT_FG)
        bg_default = self.settings.get("term_bg", DEFAULT_BG)
        buffer = self.screen.buffer
        cursor = self.screen.cursor
        cw, ch = self._char_w, self._char_h
        bold_is_bright = bool(self.settings.get("bold_is_bright", True))
        sel_bg_color = QColor(self.settings.get("selection_bg") or "#3465a4")
        sel_fg_color = QColor(self.settings.get("selection_fg") or "#ffffff")
        sel_offset = self._history_top_len()

        for row in range(self._rows):
            line = buffer[row]
            x = 0.0
            y = row * ch
            col = 0
            while col < self._cols:
                cell = line[col]
                fg = resolve_color(cell.fg, fg_default, bold=cell.bold and bold_is_bright)
                bg = resolve_color(cell.bg, bg_default)
                selected = self._in_selection(row + sel_offset, col)
                if cell.reverse:
                    fg, bg = bg, fg
                if selected:
                    fg, bg = sel_fg_color, sel_bg_color

                run_text = [cell.data or " "]
                run_end = col + 1
                while run_end < self._cols:
                    nxt = line[run_end]
                    nxt_selected = self._in_selection(row + sel_offset, run_end)
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
                    painter.fillRect(int(x), int(y), int(run_width) + 1, int(ch) + 1, bg)
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

        self._paint_cursor(painter, buffer, cursor, cw, ch, fg_default, bg_default)
        if self._visual_bell_active:
            overlay = QColor(fg_default)
            overlay.setAlpha(60)
            painter.fillRect(self.viewport().rect(), overlay)
        painter.end()

    def _paint_cursor(self, painter, buffer, cursor, cw, ch, fg_default, bg_default):
        cx = cursor.x * cw
        cy = cursor.y * ch
        cursor_color = QColor(self.settings.get("cursor_color") or fg_default)
        shape = (self.settings.get("cursor_shape") or "block").lower()
        if self._cursor_visible and self.hasFocus():
            if shape == "underline":
                painter.fillRect(int(cx), int(cy + ch - 2), max(1, int(cw)), 2, cursor_color)
            elif shape == "bar":
                painter.fillRect(int(cx), int(cy), 2, max(1, int(ch)), cursor_color)
            else:
                painter.fillRect(int(cx), int(cy), max(1, int(cw)), max(1, int(ch)), cursor_color)
                try:
                    cell = buffer[cursor.y][cursor.x]
                    painter.setPen(QColor(bg_default))
                    painter.drawText(int(cx), int(cy + self._baseline), cell.data or " ")
                except (IndexError, KeyError):
                    pass
        elif not self.hasFocus():
            painter.setPen(cursor_color)
            painter.drawRect(int(cx), int(cy), max(1, int(cw) - 1), max(1, int(ch) - 1))

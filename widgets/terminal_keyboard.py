from PyQt6.QtCore import Qt


DECCKM_PRIVATE_MODE = 1 << 5


class TerminalKeyboardMixin:
    _SPECIAL_KEYS = {
        Qt.Key.Key_Return: b"\r",
        Qt.Key.Key_Enter: b"\r",
        Qt.Key.Key_Backspace: b"\x7f",
        Qt.Key.Key_Tab: b"\t",
        Qt.Key.Key_Backtab: b"\x1b[Z",
        Qt.Key.Key_Escape: b"\x1b",
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

    _NORMAL_CURSOR_KEYS = {
        Qt.Key.Key_Up: b"\x1b[A",
        Qt.Key.Key_Down: b"\x1b[B",
        Qt.Key.Key_Right: b"\x1b[C",
        Qt.Key.Key_Left: b"\x1b[D",
    }

    _APPLICATION_CURSOR_KEYS = {
        Qt.Key.Key_Up: b"\x1bOA",
        Qt.Key.Key_Down: b"\x1bOB",
        Qt.Key.Key_Right: b"\x1bOC",
        Qt.Key.Key_Left: b"\x1bOD",
    }

    def focusNextPrevChild(self, _next):
        return False

    def keyPressEvent(self, event):
        mods = event.modifiers()
        key = event.key()

        if mods == Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier:
            if key == Qt.Key.Key_C:
                if not self._copy_selection():
                    self._copy_visible()
                return
            if key == Qt.Key.Key_V:
                self._paste_from_clipboard()
                return

        if mods & Qt.KeyboardModifier.ControlModifier and Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
            self._emit_and_send(bytes([key - Qt.Key.Key_A + 1]))
            return

        cursor_keys = (
            self._APPLICATION_CURSOR_KEYS
            if DECCKM_PRIVATE_MODE in getattr(self.screen, "mode", set())
            else self._NORMAL_CURSOR_KEYS
        )
        if key in cursor_keys:
            self._emit_and_send(cursor_keys[key])
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
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        self.key_pressed.emit(text)

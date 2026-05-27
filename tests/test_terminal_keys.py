"""Keyboard delivery: Tab and Shift+Tab must reach the PTY."""

from __future__ import annotations

import pytest


@pytest.fixture
def term(qapp):
    from widgets.terminal import TerminalWidget
    t = TerminalWidget(command=["true"])
    yield t
    t.close()


def test_focus_next_prev_child_disabled(term):
    """Returning False disables Qt's tab-as-focus-traversal so keyPressEvent
    actually sees Tab."""
    assert term.focusNextPrevChild(True) is False
    assert term.focusNextPrevChild(False) is False


def test_tab_emits_horizontal_tab(term):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent

    received: list[str] = []
    term.key_pressed.connect(received.append)
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Tab, Qt.KeyboardModifier.NoModifier)
    term.keyPressEvent(event)
    assert received == ["\t"]


def test_shift_tab_emits_csi_back_tab(term):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent

    received: list[str] = []
    term.key_pressed.connect(received.append)
    # Qt translates Shift+Tab to Key_Backtab, not Key_Tab + Shift modifier.
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Backtab,
                      Qt.KeyboardModifier.ShiftModifier)
    term.keyPressEvent(event)
    assert received == ["\x1b[Z"]

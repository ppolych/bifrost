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


def test_arrows_use_normal_cursor_sequences_by_default(term):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent

    received: list[str] = []
    term.key_pressed.connect(received.append)
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)

    term.keyPressEvent(event)

    assert received == ["\x1b[A"]


def test_arrows_use_application_cursor_sequences_when_terminal_requests_it(term):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeyEvent

    received: list[str] = []
    term.key_pressed.connect(received.append)
    term.stream.feed(b"\x1b[?1h")
    event = QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Up, Qt.KeyboardModifier.NoModifier)

    term.keyPressEvent(event)

    assert received == ["\x1bOA"]


def test_failed_backend_start_ignores_later_writes(qapp, monkeypatch):
    import widgets.terminal as terminal_module

    def fail_start(self):
        raise FileNotFoundError("missing command")

    monkeypatch.setattr(terminal_module.TerminalBackend, "start", fail_start)
    term = terminal_module.TerminalWidget(command=["missing-command"])
    try:
        assert term.backend is None
        term.write_to_backend("copy attempt")
    finally:
        term.close()


def test_terminal_backend_posix_string_command_is_not_split_into_chars(monkeypatch):
    import core.terminal_backend as terminal_backend

    monkeypatch.setattr(terminal_backend, "IS_WINDOWS", False)

    backend = terminal_backend.TerminalBackend("/bin/zsh")

    assert backend.command == ["/bin/zsh"]


def test_terminal_backend_posix_default_shell_falls_back_when_env_is_bad(monkeypatch):
    import core.terminal_backend as terminal_backend

    monkeypatch.setattr(terminal_backend, "IS_WINDOWS", False)
    monkeypatch.setenv("SHELL", "/missing/shell")
    monkeypatch.setattr(terminal_backend.shutil, "which", lambda name: "/bin/sh" if name == "sh" else None)

    backend = terminal_backend.TerminalBackend()

    assert backend.command == ["/bin/sh"]


def test_terminal_backend_windows_default_shell_uses_path_lookup(monkeypatch):
    import core.terminal_backend as terminal_backend

    monkeypatch.setattr(terminal_backend, "IS_WINDOWS", True)
    monkeypatch.setattr(terminal_backend.shutil, "which", lambda name: r"C:\Windows\System32\cmd.exe")

    backend = terminal_backend.TerminalBackend()

    assert backend.command == [r"C:\Windows\System32\cmd.exe"]


def test_terminal_backend_windows_cmdline_quotes_paths_with_spaces(monkeypatch):
    import core.terminal_backend as terminal_backend

    monkeypatch.setattr(terminal_backend, "IS_WINDOWS", True)

    backend = terminal_backend.TerminalBackend([
        r"C:\Program Files\Docker\docker.exe",
        "exec",
        "-it",
        "container name",
    ])

    assert backend._windows_cmdline() == (
        r'"C:\Program Files\Docker\docker.exe" exec -it "container name"'
    )


def test_terminal_backend_windows_string_command_is_preserved(monkeypatch):
    import core.terminal_backend as terminal_backend

    monkeypatch.setattr(terminal_backend, "IS_WINDOWS", True)

    backend = terminal_backend.TerminalBackend(r"cmd.exe /C echo hi")

    assert backend._windows_cmdline() == r"cmd.exe /C echo hi"

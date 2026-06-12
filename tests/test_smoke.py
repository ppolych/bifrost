"""Smoke tests: every load-bearing module imports, persistence round-trips,
and the pyte VT pipeline parses real escape sequences into the screen buffer."""

import json
import os
import subprocess
import sys

import pyte
import pytest


def test_imports_all_modules(qapp):
    # If any of these blow up, the app won't start. The qapp fixture is required
    # because several modules touch QFontDatabase at import time.
    import core.logging_setup  # noqa: F401
    import core.macro_engine  # noqa: F401
    import core.network_tools  # noqa: F401
    import core.persistence  # noqa: F401
    import core.platform_utils  # noqa: F401
    import core.rdp  # noqa: F401
    import core.settings_store  # noqa: F401
    import core.terminal_backend  # noqa: F401
    import core.wsl  # noqa: F401
    import widgets.terminal  # noqa: F401
    import widgets.terminal_container  # noqa: F401


def test_default_settings_safe_before_qapplication():
    proc = subprocess.run(
        [sys.executable, "-c", "from core.settings_store import default_settings; default_settings()"],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )

    assert proc.returncode == 0, proc.stderr


def test_atomic_write_round_trip(tmp_path):
    from core.platform_utils import atomic_write_json, load_json

    path = tmp_path / "x.json"
    payload = {"a": 1, "nested": [1, 2, {"k": "v"}]}
    atomic_write_json(str(path), payload)
    assert load_json(str(path), None) == payload
    # No temp leftovers
    leftovers = [p for p in os.listdir(tmp_path) if p.startswith(".tmp-")]
    assert leftovers == []


def test_load_json_missing_returns_default(tmp_path):
    from core.platform_utils import load_json

    assert load_json(str(tmp_path / "missing.json"), {"d": True}) == {"d": True}


def test_load_json_corrupt_returns_default(tmp_path):
    from core.platform_utils import load_json

    path = tmp_path / "bad.json"
    path.write_text("not json {{")
    assert load_json(str(path), []) == []


def test_settings_round_trip(qapp, tmp_path, monkeypatch):
    import core.settings_store as ss
    from PyQt6.QtGui import QFont

    monkeypatch.setattr(ss, "config_path", lambda name: str(tmp_path / name))

    settings = ss.default_settings()
    settings["term_bg"] = "#123456"
    settings["scrollback"] = 9999
    settings["font"] = QFont("Courier New", 14)
    ss.save_settings(settings)

    loaded = ss.load_settings()
    assert loaded["term_bg"] == "#123456"
    assert loaded["scrollback"] == 9999
    assert loaded["font"].family() == "Courier New"
    assert loaded["font"].pointSize() == 14


def test_load_settings_ignores_wrong_top_level_type(qapp, tmp_path, monkeypatch):
    import core.settings_store as ss

    monkeypatch.setattr(ss, "config_path", lambda name: str(tmp_path / name))
    (tmp_path / "settings.json").write_text("[]", encoding="utf-8")

    loaded = ss.load_settings()

    assert loaded["show_dashboard"] is True
    assert "font" in loaded


def test_pyte_renders_ansi_color_and_cursor():
    """The single most important invariant: pyte must parse ANSI into structured cells.
    If this regresses, the terminal renders gibberish."""
    screen = pyte.Screen(20, 5)
    stream = pyte.ByteStream(screen)
    stream.feed(b"\x1b[31mHELLO\x1b[0m world")
    line = screen.buffer[0]
    assert "".join(line[i].data for i in range(11)) == "HELLO world"
    # First 5 cells colored red, rest default.
    assert line[0].fg == "red"
    assert line[6].fg == "default"


def test_pyte_handles_cursor_movement():
    screen = pyte.Screen(20, 5)
    stream = pyte.ByteStream(screen)
    stream.feed(b"abc\r\nxyz")
    assert "".join(screen.buffer[0][i].data for i in range(3)) == "abc"
    assert "".join(screen.buffer[1][i].data for i in range(3)) == "xyz"


def test_session_manager_persists_atomically(qapp, tmp_path, monkeypatch):
    import core.persistence as persistence

    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))

    sm = persistence.SessionManager()
    sm.add_session("User sessions", {"name": "test-host", "type": "SSH", "host": "1.2.3.4"})

    raw = json.loads((tmp_path / "sessions.json").read_text())
    assert any(s["name"] == "test-host" for s in raw["User sessions"])


def test_session_manager_uses_defaults_for_wrong_top_level_type(qapp, tmp_path, monkeypatch):
    import core.persistence as persistence

    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))
    (tmp_path / "sessions.json").write_text("[]", encoding="utf-8")

    sm = persistence.SessionManager()

    assert isinstance(sm.sessions, dict)
    assert sm.sessions["Local sessions"][0]["name"] == "Local Shell"


def test_wsl_helpers_are_safe_off_windows():
    from core import wsl

    # On non-Windows this must return [] without raising.
    distros = wsl.list_distros()
    assert isinstance(distros, list)
    assert wsl.spawn_command() == ["wsl.exe"]
    assert wsl.spawn_command("Ubuntu") == ["wsl.exe", "-d", "Ubuntu"]


def test_wsl_list_distros_handles_failed_wsl_exe(monkeypatch):
    import subprocess

    from core import wsl

    monkeypatch.setattr(wsl.sys, "platform", "win32")
    monkeypatch.setattr(
        wsl.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 1, stdout=b"Ubuntu\x00"),
    )

    assert wsl.list_distros() == []


def test_wsl_list_distros_decodes_utf8_output(monkeypatch):
    import subprocess

    from core import wsl

    monkeypatch.setattr(wsl.sys, "platform", "win32")
    monkeypatch.setattr(
        wsl.subprocess,
        "run",
        lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 0, stdout=b"Ubuntu\nDebian\n"),
    )

    assert wsl.list_distros() == ["Ubuntu", "Debian"]


def test_wsl_list_distros_handles_os_error(monkeypatch):
    from core import wsl

    monkeypatch.setattr(wsl.sys, "platform", "win32")

    def fail(*args, **kwargs):
        raise OSError("wsl unavailable")

    monkeypatch.setattr(wsl.subprocess, "run", fail)

    assert wsl.list_distros() == []


def test_ping_command_branches_by_platform(monkeypatch):
    import core.network_tools as nt

    monkeypatch.setattr(nt.sys, "platform", "linux")
    assert nt._ping_command("1.1.1.1") == ["ping", "-c", "1", "-W", "1", "1.1.1.1"]

    monkeypatch.setattr(nt.sys, "platform", "darwin")
    assert nt._ping_command("1.1.1.1") == ["ping", "-c", "1", "-t", "1", "1.1.1.1"]

    monkeypatch.setattr(nt.sys, "platform", "win32")
    assert nt._ping_command("1.1.1.1") == ["ping", "-n", "1", "-w", "1000", "1.1.1.1"]


def test_scan_ports_clamps_range_and_ignores_socket_errors(monkeypatch):
    import core.network_tools as nt

    scanned = []

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_create_connection(target, timeout):
        scanned.append((target, timeout))
        if target[1] != 3:
            raise OSError("network unreachable")
        return Conn()

    monkeypatch.setattr(nt.socket, "create_connection", fake_create_connection)

    assert nt.scan_ports("example.invalid", -10, 3) == [3]
    assert [target[1] for target, _timeout in scanned] == [1, 2, 3]
    assert {timeout for _target, timeout in scanned} == {0.05}
    assert nt.scan_ports("example.invalid", 5, 4) == []
    assert nt.scan_ports("example.invalid", "bad", 4) == []


@pytest.mark.skipif(os.environ.get("SKIP_TERMINAL_TEST") == "1",
                    reason="Terminal widget test needs an X server or offscreen Qt")
def test_terminal_widget_feeds_bytes_into_screen(qapp):
    """End-to-end: build the widget, feed bytes, confirm the screen sees them.
    Bypasses the real PTY backend by spawning `true` then feeding bytes directly."""
    from widgets.terminal import TerminalWidget

    # Use a no-op command so the backend exits quickly; the reader will stop
    # itself, but the widget should remain usable for direct stream feeds.
    term = TerminalWidget(command=["true"])
    term._on_data(b"hello")
    assert "".join(term.screen.buffer[0][i].data for i in range(5)) == "hello"
    term.close()

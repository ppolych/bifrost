"""Regression coverage for tab controls and reconnect appearance."""

from PyQt6.QtWidgets import QStyle, QTabBar

from tests.test_cluster import app


def _close_button(app, index):
    bar = app.tabs.tabBar()
    side = QTabBar.ButtonPosition(
        bar.style().styleHint(QStyle.StyleHint.SH_TabBar_CloseButtonPosition)
    )
    return bar.tabButton(index, side)


def test_unpin_restores_working_close_button(app, monkeypatch):
    app.new_terminal_tab("temporary", command=["true"])
    container = app.tabs.widget(1)
    button = _close_button(app, 1)
    assert button is not None
    app.toggle_tab_pin(1)
    assert button.isHidden()
    app.toggle_tab_pin(1)
    assert _close_button(app, 1) is button
    assert not button.isHidden()
    monkeypatch.setitem(app.settings, "confirm_close_tab", False)
    button.click()
    assert app.tabs.indexOf(container) == -1


def test_reconnect_keeps_session_appearance_and_unpinnable_button(app, monkeypatch):
    from widgets.terminal_container import TerminalContainer

    class Backend:
        def start(self): pass
        def read(self, size): return b""
        def write(self, data): pass
        def set_winsize(self, rows, cols): pass
        def close(self): pass

    session = {
        "name": "remote", "host": "example", "type": "SSH",
        "overrides": {"scheme": "Solarized Dark", "font": "Monospace,19"},
    }
    expected = app._settings_for_session(session)
    # Ensure the test distinguishes session overrides from global settings.
    app.settings["term_bg"] = "#123456"
    container = TerminalContainer(
        "remote", settings=expected, backend=Backend(), ssh_session=session,
    )
    index = app.tabs.addTab(container, "remote")
    app.toggle_tab_pin(index)
    monkeypatch.setattr(app, "_build_ssh_backend", lambda *args: Backend())
    app._reconnect_tab(index)
    replacement = app.tabs.widget(index)
    assert replacement.settings["term_bg"] == expected["term_bg"]
    assert replacement.primary_terminal.settings["font"] == expected["font"]
    button = _close_button(app, index)
    assert button is not None and button.isHidden()
    app.toggle_tab_pin(index)
    assert _close_button(app, index) is button
    assert not button.isHidden()

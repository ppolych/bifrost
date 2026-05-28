"""Mouse selection geometry, word expansion, and text extraction."""

import pytest


@pytest.fixture
def term(qapp):
    from widgets.terminal import TerminalWidget
    # `true` exits immediately; we never rely on the backend for these tests,
    # we feed bytes directly to the pyte stream via _on_data.
    t = TerminalWidget(command=["true"])
    yield t
    t.close()


def _feed(term, text: str):
    term._on_data(text.encode())


def test_normalized_selection_orders_pair(term):
    term._selection = (5, 10, 2, 3)
    r1, c1, r2, c2 = term._normalized_selection()
    assert (r1, c1) == (2, 3)
    # c2 is exclusive
    assert (r2, c2) == (5, 11)


def test_in_selection_single_row(term):
    term._selection = (3, 5, 3, 10)
    assert not term._in_selection(3, 4)
    assert term._in_selection(3, 5)
    assert term._in_selection(3, 10)         # inclusive of endpoint cell
    assert not term._in_selection(3, 11)
    assert not term._in_selection(2, 7)
    assert not term._in_selection(4, 7)


def test_in_selection_multi_row(term):
    term._selection = (2, 5, 4, 3)
    assert not term._in_selection(2, 4)
    assert term._in_selection(2, 5)
    assert term._in_selection(2, 79)
    assert term._in_selection(3, 0)          # middle row fully selected
    assert term._in_selection(3, 50)
    assert term._in_selection(4, 0)
    assert term._in_selection(4, 3)
    assert not term._in_selection(4, 4)


def test_word_expansion_picks_up_path_chars(term):
    _feed(term, "  /usr/local/bin/python3.11  ")
    # Click roughly in the middle of the word.
    term._select_word_at(0, 8)
    r1, c1, r2, c2 = term._selection
    text = term.selected_text()
    assert text == "/usr/local/bin/python3.11"
    assert r1 == r2 == 0
    assert c1 == 2  # cell index where '/' starts


def test_word_expansion_grabs_user_at_host_port(term):
    _feed(term, "ssh alice@10.0.0.5:2222 to login")
    # Click on "alice@..."
    term._select_word_at(0, 4)
    assert term.selected_text() == "alice@10.0.0.5:2222"


def test_word_expansion_skips_pure_whitespace(term):
    _feed(term, "abc   def")
    term._select_word_at(0, 4)  # in the middle of the spaces
    assert term._selection is None


def test_selected_text_multi_line_rstrips(term):
    # Three short lines on rows 0..2 followed by ~24 spaces of padding.
    _feed(term, "first line\r\nsecond line\r\nthird")
    term._selection = (0, 0, 2, 4)  # through "third"
    text = term.selected_text()
    # Each line should be rstripped of the cell padding past actual content.
    assert text == "first line\nsecond line\nthird"


def test_clear_selection(term):
    term._selection = (1, 1, 2, 2)
    assert term.has_selection()
    term.clear_selection()
    assert not term.has_selection()


def test_copy_selection_writes_to_clipboard(term, qapp):
    from PyQt6.QtGui import QGuiApplication

    _feed(term, "hello world")
    term._selection = (0, 0, 0, 4)  # "hello"
    assert term._copy_selection() is True
    assert QGuiApplication.clipboard().text() == "hello"


def test_copy_selection_returns_false_when_empty(term):
    assert term._copy_selection() is False


def test_select_visible_selects_full_viewport(term):
    term._select_visible()
    assert term._selection == (0, 0, term._rows - 1, term._cols - 1)


def test_copy_visible_writes_visible_screen(term, qapp):
    from PyQt6.QtGui import QGuiApplication

    _feed(term, "visible line")
    term._copy_visible()
    assert QGuiApplication.clipboard().text().splitlines()[0] == "visible line"


def test_pos_to_cell_clamps_to_viewport(term):
    from PyQt6.QtCore import QPoint

    # Negative / oversized coordinates should clamp into [0, cols-1] x [0, rows-1].
    assert term._pos_to_cell(QPoint(-100, -100)) == (0, 0)
    r, c = term._pos_to_cell(QPoint(100_000, 100_000))
    assert r == term._rows - 1
    assert c == term._cols - 1


def test_settings_dialog_exposes_copy_on_select(qapp):
    from widgets.settings_dialog import SettingsDialog
    from core.settings_store import default_settings

    base = default_settings()
    base["copy_on_select"] = False
    dlg = SettingsDialog(current_settings=base)
    dlg.copy_on_select_cb.setChecked(True)
    out = dlg.get_settings()
    assert out["copy_on_select"] is True

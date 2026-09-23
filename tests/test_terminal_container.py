"""TerminalContainer split behavior."""


def test_quad_split_reassigns_primary_and_drops_old(qapp):
    from widgets.terminal import TerminalWidget
    from widgets.terminal_container import TerminalContainer

    c = TerminalContainer("t", command=["true"])
    old_primary = c.primary_terminal
    c.split("quad")
    qapp.processEvents()  # let the old pane's deleteLater run

    live = c.findChildren(TerminalWidget)
    assert len(live) == 4
    # The original pane is gone and primary now points at a live pane, not a
    # dangling deleted widget.
    assert old_primary not in live
    assert c.primary_terminal in live
    # Find/search drives primary_terminal — must not raise on a dead reference.
    c.perform_search("x", True)

    c.shutdown()
    c.close()


def test_repeated_quad_split_stops_nested_terminals(qapp, monkeypatch):
    from widgets import terminal
    from widgets.terminal_container import TerminalContainer

    class Backend:
        def __init__(self, command=None):
            self.closed = False

        def start(self): pass
        def read(self, size): return b""
        def set_winsize(self, rows, cols): pass
        def close(self): self.closed = True

    monkeypatch.setattr(terminal, "TerminalBackend", Backend)
    c = TerminalContainer("t")
    try:
        c.split("quad")
        previous = c.findChildren(terminal.TerminalWidget)
        c.split("quad")
        assert all(t.backend.closed for t in previous)
        assert all(t.reader is None for t in previous)
        assert len(c.findChildren(terminal.TerminalWidget)) == 4
    finally:
        c.shutdown()
        c.close()


def test_vertical_split_keeps_primary(qapp):
    from widgets.terminal import TerminalWidget
    from widgets.terminal_container import TerminalContainer

    c = TerminalContainer("t", command=["true"])
    primary = c.primary_terminal
    c.split("vert")
    qapp.processEvents()

    live = c.findChildren(TerminalWidget)
    assert len(live) == 2
    assert c.primary_terminal is primary  # unchanged on non-quad split

    c.shutdown()
    c.close()

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

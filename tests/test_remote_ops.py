def test_remote_ops_buttons_disabled_without_backend(qapp):
    from widgets.remote_ops import RemoteOpsWidget

    widget = RemoteOpsWidget()

    assert all(not button.isEnabled() for button in widget.buttons)
    assert widget.status.text() == "Remote Ops: idle"


def test_remote_ops_result_updates_output(qapp):
    from core.remote_ops import REMOTE_ACTIONS
    from widgets.remote_ops import RemoteOpsWidget

    backend = object()
    widget = RemoteOpsWidget()
    widget.set_backend(backend)
    widget._busy = True

    widget._apply_result(backend, REMOTE_ACTIONS[0], 0, "up 1 day\n", "")

    assert widget.status.text() == "Uptime: exit 0"
    assert "up 1 day" in widget.output.toPlainText()
    assert all(button.isEnabled() for button in widget.buttons)


def test_remote_ops_ignores_stale_results(qapp):
    from core.remote_ops import REMOTE_ACTIONS
    from widgets.remote_ops import RemoteOpsWidget

    widget = RemoteOpsWidget()
    widget.set_backend(object())

    widget._apply_result(object(), REMOTE_ACTIONS[0], 0, "stale", "")

    assert "stale" not in widget.output.toPlainText()

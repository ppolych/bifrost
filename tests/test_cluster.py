"""Cluster mode: MultiExec scoped to a chosen subset of tabs."""

import pytest


@pytest.fixture
def app(qapp, tmp_path, monkeypatch):
    import core.persistence as persistence
    import core.settings_store as settings_store
    import core.snippets as snippets
    import core.workspaces as workspaces

    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(settings_store, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(snippets, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(workspaces, "config_path", lambda name: str(tmp_path / name))

    from bifrost_app import BifrostApp
    from core.settings_store import default_settings

    settings = default_settings()
    settings["show_dashboard"] = False
    a = BifrostApp(settings=settings)
    yield a
    a.metrics_timer.stop()
    a.ssh_state_timer.stop()
    for i in range(a.tabs.count()):
        w = a.tabs.widget(i)
        if hasattr(w, "shutdown"):
            w.shutdown()


def _terminals_of(app):
    """Map container -> recorded writes, monkeypatching write_to_backend."""
    from widgets.terminal import TerminalWidget
    from widgets.terminal_container import TerminalContainer

    recorded = {}
    for i in range(app.tabs.count()):
        container = app.tabs.widget(i)
        if not isinstance(container, TerminalContainer):
            continue
        writes = recorded.setdefault(container, [])
        for term in container.findChildren(TerminalWidget):
            term.write_to_backend = lambda data, _w=writes: _w.append(data)
    return recorded


def test_broadcast_all_reaches_every_tab(app):
    app.new_terminal_tab("t2", command=["true"])
    recorded = _terminals_of(app)
    app.multi_exec_scope.setCurrentIndex(0)  # All terminals
    app.multi_exec_input.setText("uptime")
    app.broadcast_command()
    assert all(writes == ["uptime\r"] for writes in recorded.values())
    assert len(recorded) == 2


def test_broadcast_cluster_only_reaches_members(app):
    app.new_terminal_tab("t2", command=["true"])
    app.new_terminal_tab("t3", command=["true"])
    member_index = 1
    app.toggle_tab_cluster(member_index)
    recorded = _terminals_of(app)

    app.multi_exec_scope.setCurrentIndex(1)  # Cluster only
    app.multi_exec_input.setText("uptime")
    app.broadcast_command()

    member = app.tabs.widget(member_index)
    for container, writes in recorded.items():
        assert writes == (["uptime\r"] if container is member else [])


def test_cluster_label_counts_members(app):
    app.new_terminal_tab("t2", command=["true"])
    app.multi_exec_scope.setCurrentIndex(1)  # Cluster only — triggers refresh
    assert app.multi_exec_label.text() == "CLUSTER (0):"
    app.toggle_tab_cluster(0)
    assert app.multi_exec_label.text() == "CLUSTER (1):"
    app.multi_exec_scope.setCurrentIndex(0)
    assert app.multi_exec_label.text() == "ALL TERMINALS:"


def test_toggle_tab_cluster_round_trip(app):
    container = app.tabs.widget(0)
    app.toggle_tab_cluster(0)
    assert container in app.cluster_tabs
    app.toggle_tab_cluster(0)
    assert container not in app.cluster_tabs


def test_key_outside_cluster_still_drives_own_tab(app):
    """MultiExec on + cluster scope: a non-member tab keeps working locally."""
    from widgets.terminal import TerminalWidget

    app.new_terminal_tab("t2", command=["true"])
    app.toggle_tab_cluster(1)
    recorded = _terminals_of(app)
    app.multi_exec_scope.setCurrentIndex(1)
    app.on_multi_exec_toggled(True)

    outsider = app.tabs.widget(0)
    member = app.tabs.widget(1)
    term = outsider.findChildren(TerminalWidget)[0]
    # Route a key as if it came from the outsider terminal.
    app.sender = lambda: term
    app.on_terminal_key("x")
    assert recorded[outsider] == ["x"]   # local echo path
    assert recorded[member] == ["x"]     # cluster broadcast


def test_closing_tab_drops_cluster_membership(app, monkeypatch):
    app.new_terminal_tab("t2", command=["true"])
    container = app.tabs.widget(1)
    app.toggle_tab_cluster(1)
    assert container in app.cluster_tabs
    monkeypatch.setitem(app.settings, "confirm_close_tab", False)
    app.close_tab(1)
    assert container not in app.cluster_tabs


def test_multi_exec_bar_has_scope_and_auto_cluster(app):
    assert app.multi_exec_scope.itemData(0) == "all"
    assert app.multi_exec_scope.itemData(1) == "cluster"
    assert not app.auto_cluster_cb.isChecked()

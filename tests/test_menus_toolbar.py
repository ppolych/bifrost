from PyQt6.QtCore import Qt


def test_toolbar_is_icon_only(qapp):
    from widgets.toolbar import MainToolBar

    toolbar = MainToolBar()
    assert toolbar.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
    assert toolbar.session_act.text() == ""
    assert toolbar.multi_act.text() == ""
    assert toolbar.split_vert.toolTip()


def test_app_menubar_has_desktop_sections(qapp, tmp_path, monkeypatch):
    import core.persistence as persistence
    import core.settings_store as settings_store
    import core.snippets as snippets
    import core.workspaces as workspaces

    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(settings_store, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(snippets, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(workspaces, "config_path", lambda name: str(tmp_path / name))

    from bifrost_app import BifrostApp

    app = BifrostApp(settings=settings_store.default_settings())
    titles = [action.text() for action in app.menuBar().actions()]

    assert titles == ["Session", "Connections", "View", "Tools", "Workspaces", "Help"]

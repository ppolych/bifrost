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
    help_menu = app.menuBar().actions()[-1].menu()
    help_actions = [action.text() for action in help_menu.actions() if action.text()]
    assert help_actions[-1] == "About Bifrost"


def test_command_palette_filters_entries(qapp):
    from widgets.command_palette import CommandPalette, PaletteEntry

    activated = []
    dlg = CommandPalette([
        PaletteEntry("Session: Start local terminal", lambda: activated.append("local")),
        PaletteEntry("Tools: Settings", lambda: activated.append("settings")),
    ])

    dlg.search.setText("settings")
    dlg.activate_selected()

    assert activated == ["settings"]


def test_command_palette_includes_saved_sessions(qapp, tmp_path, monkeypatch):
    import core.macro_engine as macro_engine
    import core.persistence as persistence
    import core.settings_store as settings_store
    import core.snippets as snippets
    import core.workspaces as workspaces

    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(settings_store, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(snippets, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(workspaces, "config_path", lambda name: str(tmp_path / name))
    monkeypatch.setattr(macro_engine, "config_path", lambda name: str(tmp_path / name))

    from bifrost_app import BifrostApp

    app = BifrostApp(settings=settings_store.default_settings())
    app.session_manager.sessions = {
        "User sessions": [{"name": "prod", "type": "SSH", "host": "prod.example.com"}]
    }

    labels = [entry.label for entry in app._command_palette_entries()]

    assert "Open session: prod (User sessions/prod)" in labels

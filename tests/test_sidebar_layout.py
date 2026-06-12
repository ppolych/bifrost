"""Sidebar layout: SFTP must be a sibling of the tab widget, not a tab.

This guards the MobaXterm-style "sessions + SFTP visible at the same time"
property and pins the new tab indexes so callers like BifrostApp.show_dashboard
and on_tab_changed don't drift.
"""

import pytest


@pytest.fixture
def sidebar(qapp, tmp_path, monkeypatch):
    import core.persistence as persistence
    monkeypatch.setattr(persistence, "config_path", lambda name: str(tmp_path / name))
    import core.macro_engine as macro_engine
    monkeypatch.setattr(macro_engine, "config_path", lambda name: str(tmp_path / name))
    import core.snippets as snippets
    monkeypatch.setattr(snippets, "config_path", lambda name: str(tmp_path / name))

    from widgets.sidebar import Sidebar
    sm = persistence.SessionManager()
    me = macro_engine.MacroEngine()
    sn = snippets.SnippetManager()
    return Sidebar(sm, me, sn)


def test_sftp_is_not_a_tab(sidebar):
    """If SFTP comes back as a tab someone forgot the layout invariant."""
    labels = [sidebar.tabs.tabText(i) for i in range(sidebar.tabs.count())]
    assert not any("SFTP" in t for t in labels), labels


def test_tab_indexes_match_documented_order(sidebar):
    # Tabs are icon-only now; identity lives in the tooltip.
    tooltips = [sidebar.tabs.tabToolTip(i) for i in range(sidebar.tabs.count())]
    # Order matters — BifrostApp.show_dashboard and on_tab_changed reference these.
    assert len(tooltips) == 8
    assert "Sessions" in tooltips[0]
    assert "SSH" in tooltips[1]
    assert "servers" in tooltips[2].lower()
    assert "Tools" in tooltips[3]
    assert "Macros" in tooltips[4]
    assert "Snippets" in tooltips[5]
    assert "Docker" in tooltips[6]
    assert "Remote Ops" in tooltips[7]
    assert not any("credential" in tooltip.lower() or "password" in tooltip.lower() for tooltip in tooltips)


def test_sftp_widget_is_in_the_splitter(sidebar):
    splitter = sidebar.content_splitter
    assert splitter.count() == 2
    # Index 0 = tab widget, index 1 = SFTP browser.
    assert splitter.widget(0) is sidebar.tabs
    assert splitter.widget(1) is sidebar.sftp_widget


def test_sftp_pane_starts_collapsed(sidebar):
    """No active SSH session yet → SFTP pane shouldn't take real estate."""
    sizes = sidebar.content_splitter.sizes()
    assert len(sizes) == 2
    assert sizes[1] == 0


def test_session_tree_starts_collapsed(sidebar):
    for i in range(sidebar.tree.topLevelItemCount()):
        item = sidebar.tree.topLevelItem(i)
        assert not item.isExpanded()


def test_session_filter_shows_matching_group(sidebar):
    sidebar.session_filter.setText("production")

    visible = [
        sidebar.tree.topLevelItem(i).text(0)
        for i in range(sidebar.tree.topLevelItemCount())
        if not sidebar.tree.topLevelItem(i).isHidden()
    ]

    assert visible == ["Work Folders"]


def test_session_filter_matches_tags(sidebar):
    sidebar.session_manager.sessions = {
        "User sessions": [
            {"name": "db01", "type": "SSH", "host": "10.0.0.1", "tags": ["prod"]},
            {"name": "dev01", "type": "SSH", "host": "10.0.0.2", "tags": ["dev"]},
        ],
    }
    sidebar.refresh_sessions()
    sidebar.session_filter.setText("prod")

    group = sidebar.tree.topLevelItem(0)

    assert not group.isHidden()
    assert not group.child(0).isHidden()
    assert group.child(1).isHidden()
    assert "prod" in group.child(0).toolTip(0)


def test_session_items_keep_live_session_object(sidebar):
    sidebar.session_manager.sessions = {
        "User sessions": [
            {"name": "same", "type": "SSH", "host": "one"},
            {"name": "same", "type": "SSH", "host": "two"},
        ],
    }
    sidebar.refresh_sessions()

    group = sidebar.tree.topLevelItem(0)
    first = group.child(0)
    second = group.child(1)

    assert sidebar._session_for_item(first) is sidebar.session_manager.sessions["User sessions"][0]
    assert sidebar._session_for_item(second) is sidebar.session_manager.sessions["User sessions"][1]


def test_show_and_hide_sftp_pane(sidebar):
    sidebar.show_sftp_pane(sizes=(400, 300))
    assert sidebar.content_splitter.sizes()[1] > 0
    sidebar.hide_sftp_pane()
    assert sidebar.content_splitter.sizes()[1] == 0


def test_show_sftp_pane_is_noop_when_already_open(sidebar):
    sidebar.show_sftp_pane(sizes=(500, 500))
    before = sidebar.content_splitter.sizes()
    # Calling again with different sizes shouldn't fight the user's manual resize.
    sidebar.show_sftp_pane(sizes=(100, 200))
    assert sidebar.content_splitter.sizes() == before


def test_collapse_hides_entire_splitter(sidebar):
    """isHidden() reflects the explicit setVisible flag (isVisible() also
    requires a shown parent, which we don't have in a headless test)."""
    sidebar.toggle_collapse()
    assert sidebar.is_collapsed
    assert sidebar.content_splitter.isHidden()
    sidebar.toggle_collapse()
    assert not sidebar.content_splitter.isHidden()

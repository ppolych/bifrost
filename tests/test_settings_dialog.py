"""Tests for the expanded SettingsDialog and the modules it depends on."""

THEMED_WIDGET_FILES = [
    "bifrost_app.py",
    "widgets/credential_manager.py",
    "widgets/dashboard.py",
    "widgets/docker_dashboard.py",
    "widgets/editor.py",
    "widgets/local_servers.py",
    "widgets/search_bar.py",
    "widgets/session_dialog.py",
    "widgets/sftp_browser.py",
    "widgets/sidebar.py",
    "widgets/ssh_browser.py",
    "widgets/toolbar.py",
]


def test_app_widgets_do_not_hardcode_dark_theme_surfaces():
    from pathlib import Path

    repo = Path(__file__).resolve().parents[1]
    banned = [
        "background-color: #1e1e1e",
        "background-color: #2b2b2b",
        "background-color: #3c3f41",
        "background: #1e1e1e",
        "background: #2b2b2b",
        "background: #3c3f41",
        "color: #888",
        "color: #aaa",
        "color: #ccc",
        "border: 1px solid #444",
        "border: 1px solid #555",
    ]

    offenders = []
    for relative in THEMED_WIDGET_FILES:
        text = (repo / relative).read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                offenders.append(f"{relative}: {token}")

    assert offenders == []


def test_color_schemes_have_unique_palettes():
    from core.color_schemes import SCHEMES
    seen = set()
    for name, (bg, fg) in SCHEMES.items():
        assert bg.startswith("#") and fg.startswith("#"), name
        seen.add((bg.lower(), fg.lower()))
    # Distinct visual identity for each preset.
    assert len(seen) == len(SCHEMES)


def test_session_dialog_uses_central_color_scheme_names(qapp):
    from core.color_schemes import scheme_names
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog()

    names = [dlg.color_scheme.itemText(i) for i in range(dlg.color_scheme.count())]
    assert names == scheme_names()


def test_session_dialog_rdp_port_round_trip(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog()
    dlg.proto_tabs.setCurrentWidget(dlg.rdp_tab)
    assert dlg.rdp_port_input.text() == "3389"

    dlg.rdp_host_input.setText("rdp.example.com")
    dlg.rdp_port_input.setText("3390")
    data = dlg.get_data()
    assert data["type"] == "RDP"
    assert data["host"] == "rdp.example.com"
    assert data["port"] == "3390"
    assert data["name"] == "rdp rdp.example.com:3390"

    dlg2 = SessionDialog(session=data)
    assert dlg2.proto_tabs.currentWidget() is dlg2.rdp_tab
    assert dlg2.rdp_host_input.text() == "rdp.example.com"
    assert dlg2.rdp_port_input.text() == "3390"


def test_dashboard_has_no_pro_placeholder(qapp):
    from PyQt6.QtWidgets import QLabel
    from widgets.dashboard import Dashboard

    dashboard = Dashboard()
    labels = [label.text() for label in dashboard.findChildren(QLabel)]

    assert "PRO" not in labels


def test_dashboard_empty_recent_placeholder_is_not_actionable(qapp):
    from widgets.dashboard import Dashboard

    dashboard = Dashboard()
    received = []
    dashboard.session_requested.connect(received.append)

    item = dashboard.recents_list.item(0)
    dashboard.on_recent_click(item)

    assert item.text() == "No recent sessions"
    assert received == []


def test_apply_scheme_mutates_settings():
    from core.color_schemes import apply_scheme

    s = {"term_bg": "#000", "term_fg": "#fff"}
    apply_scheme(s, "Dracula")
    assert s["term_bg"] == "#282a36"
    assert s["term_fg"] == "#f8f8f2"


def test_scheme_for_reverse_lookup():
    from core.color_schemes import scheme_for

    assert scheme_for("#282a36", "#f8f8f2") == "Dracula"
    assert scheme_for("#282A36", "#F8F8F2") == "Dracula"  # case-insensitive
    assert scheme_for("#123456", "#abcdef") is None


def test_default_settings_includes_new_keys():
    from core.settings_store import default_settings

    s = default_settings()
    expected = {
        "color_scheme", "cursor_shape", "bell_mode", "wheel_lines",
        "tab_position", "confirm_close_tab", "confirm_quit_with_sessions",
        "ssh_default_user", "ssh_default_port", "ssh_connect_timeout",
        "ssh_agent_forwarding", "known_hosts_file", "log_directory", "default_text_editor_command",
        "ssh_default_auth", "ssh_startup_command", "credential_save_policy",
        "credential_provider", "ssh_default_key_path",
        "confirm_multiline_paste", "confirm_large_paste", "large_paste_threshold",
        "bracketed_paste",
    }
    assert expected.issubset(s.keys())


def test_settings_dialog_round_trip(qapp):
    from widgets.settings_dialog import SettingsDialog
    from core.settings_store import default_settings

    base = default_settings()
    dlg = SettingsDialog(current_settings=base)

    # Change a representative sample of fields then read back.
    dlg.scheme_combo.setCurrentText("Nord")
    dlg.scrollback_sb.setValue(8000)
    dlg.wheel_sb.setValue(5)
    dlg.ssh_user_input.setText("alice")
    dlg.ssh_port_sb.setValue(2222)
    dlg.ssh_timeout_sb.setValue(30.0)
    dlg.ssh_auth_combo.setCurrentText("Private key")
    dlg.ssh_key_path_input.setText("~/.ssh/id_ed25519")
    dlg.ssh_startup_command_input.setText("uptime")
    dlg.agent_fwd_cb.setChecked(True)
    dlg.credential_policy_combo.setCurrentText("Never save")
    dlg.credential_provider_combo.setCurrentText("KeePassXC / Secret Service")
    dlg.text_editor_cmd_input.setText("code -w")
    dlg.tab_pos_combo.setCurrentText("Bottom")
    # Pick the "Bar" cursor radio
    for btn in dlg.cursor_group.buttons():
        if btn.property("value") == "bar":
            btn.setChecked(True)
    # Pick the "visual" bell radio
    for btn in dlg.bell_group.buttons():
        if btn.property("value") == "visual":
            btn.setChecked(True)

    out = dlg.get_settings()
    assert out["color_scheme"] == "Nord"
    assert out["term_bg"] == "#2e3440"  # applied by scheme callback
    assert out["term_fg"] == "#d8dee9"
    assert out["scrollback"] == 8000
    assert out["wheel_lines"] == 5
    assert out["ssh_default_user"] == "alice"
    assert out["ssh_default_port"] == 2222
    assert out["ssh_connect_timeout"] == 30.0
    assert out["ssh_default_auth"] == "key"
    assert out["ssh_default_key_path"] == "~/.ssh/id_ed25519"
    assert out["ssh_startup_command"] == "uptime"
    assert out["ssh_agent_forwarding"] is True
    assert out["credential_save_policy"] == "never"
    assert out["credential_provider"] == "keepassxc"
    assert out["default_text_editor_command"] == "code -w"
    assert out["tab_position"] == "Bottom"
    assert out["cursor_shape"] == "bar"
    assert out["bell_mode"] == "visual"


def test_load_settings_sanitizes_bad_numeric_and_bool_values(qapp, tmp_path, monkeypatch):
    import json

    import core.settings_store as ss
    from widgets.settings_dialog import SettingsDialog

    monkeypatch.setattr(ss, "config_path", lambda name: str(tmp_path / name))
    (tmp_path / "settings.json").write_text(json.dumps({
        "opacity": "opaque",
        "ssh_default_port": "not-a-port",
        "ssh_connect_timeout": "slow",
        "ssh_keepalive_interval": -1,
        "show_dashboard": "yes",
        "main_splitter_sizes": ["260", "940"],
        "sidebar_splitter_sizes": ["bad"],
    }), encoding="utf-8")

    loaded = ss.load_settings()

    assert loaded["opacity"] == 100
    assert loaded["ssh_default_port"] == 22
    assert loaded["ssh_connect_timeout"] == 15
    assert loaded["ssh_keepalive_interval"] == 30
    assert loaded["show_dashboard"] is True
    assert loaded["main_splitter_sizes"] == [260, 940]
    assert loaded["sidebar_splitter_sizes"] == []
    SettingsDialog(current_settings=loaded)


def test_load_settings_sanitizes_bad_application_theme(qapp, tmp_path, monkeypatch):
    import json

    import core.settings_store as ss

    monkeypatch.setattr(ss, "config_path", lambda name: str(tmp_path / name))
    (tmp_path / "settings.json").write_text(json.dumps({
        "theme": "Missing Theme",
    }), encoding="utf-8")

    loaded = ss.load_settings()

    assert loaded["theme"] == "Dark (MobaXterm style)"

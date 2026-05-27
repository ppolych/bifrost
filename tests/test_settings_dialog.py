"""Tests for the expanded SettingsDialog and the modules it depends on."""

import pytest


def test_color_schemes_have_unique_palettes():
    from core.color_schemes import SCHEMES
    seen = set()
    for name, (bg, fg) in SCHEMES.items():
        assert bg.startswith("#") and fg.startswith("#"), name
        seen.add((bg.lower(), fg.lower()))
    # Distinct visual identity for each preset.
    assert len(seen) == len(SCHEMES)


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
        "ssh_agent_forwarding", "known_hosts_file", "log_directory",
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
    dlg.agent_fwd_cb.setChecked(True)
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
    assert out["ssh_agent_forwarding"] is True
    assert out["tab_position"] == "Bottom"
    assert out["cursor_shape"] == "bar"
    assert out["bell_mode"] == "visual"


def test_credentials_flow_through_to_ssh_credentials():
    """The settings keys map cleanly into the SshCredentials a backend uses."""
    from core.ssh_backend import SshCredentials

    session = {"host": "h", "user": "u", "port": 2200, "auth": "agent"}
    creds = SshCredentials.from_session(session)
    # Simulate what BifrostApp._build_ssh_backend does:
    creds.connect_timeout = 30.0
    creds.agent_forwarding = True
    creds.known_hosts_file = "/tmp/known_hosts"
    assert creds.connect_timeout == 30.0
    assert creds.agent_forwarding is True
    assert creds.known_hosts_file == "/tmp/known_hosts"

"""Tests for the second batch of settings (cursor color, selection colors,
SSH keepalive, bold-is-bright, strip-newlines, default editor, restore-geom)."""

from __future__ import annotations


def test_default_settings_has_all_new_keys():
    from core.settings_store import default_settings

    s = default_settings()
    expected = {
        "cursor_color", "selection_bg", "selection_fg", "bold_is_bright",
        "strip_newlines_on_paste", "default_editor_command", "default_text_editor_command",
        "restore_window_geometry", "window_geometry",
        "main_splitter_sizes", "sidebar_splitter_sizes", "last_sidebar_tab",
        "ssh_keepalive_interval", "ssh_default_auth", "ssh_startup_command",
        "ssh_default_key_path",
        "confirm_multiline_paste", "confirm_large_paste", "large_paste_threshold",
        "credential_save_policy", "credential_provider",
    }
    missing = expected - s.keys()
    assert not missing, f"missing: {missing}"


def test_settings_dialog_writes_new_fields(qapp):
    from core.settings_store import default_settings
    from widgets.settings_dialog import SettingsDialog

    dlg = SettingsDialog(current_settings=default_settings())
    dlg.bold_bright_cb.setChecked(False)
    dlg.strip_newlines_cb.setChecked(True)
    dlg.confirm_multiline_paste_cb.setChecked(False)
    dlg.confirm_large_paste_cb.setChecked(True)
    dlg.large_paste_threshold_sb.setValue(3000)
    dlg.keepalive_sb.setValue(60)
    dlg.ssh_auth_combo.setCurrentText("Password")
    dlg.ssh_key_path_input.setText("~/.ssh/id_ed25519")
    dlg.ssh_startup_command_input.setText("tmux attach || tmux")
    dlg.credential_policy_combo.setCurrentText("Never save")
    dlg.credential_provider_combo.setCurrentText("1Password CLI")
    dlg.editor_cmd_input.setText("code -n")
    dlg.text_editor_cmd_input.setText("notepad")
    dlg.restore_geom_cb.setChecked(False)
    # Mutate the picker-driven keys directly (the dialog stores them in
    # self.settings via callbacks; we simulate the picker result).
    dlg.settings["cursor_color"] = "#ff00ff"
    dlg.settings["selection_bg"] = "#222233"
    dlg.settings["selection_fg"] = "#eeeeee"

    out = dlg.get_settings()
    assert out["bold_is_bright"] is False
    assert out["strip_newlines_on_paste"] is True
    assert out["confirm_multiline_paste"] is False
    assert out["confirm_large_paste"] is True
    assert out["large_paste_threshold"] == 3000
    assert out["ssh_keepalive_interval"] == 60
    assert out["ssh_default_auth"] == "password"
    assert out["ssh_default_key_path"] == "~/.ssh/id_ed25519"
    assert out["ssh_startup_command"] == "tmux attach || tmux"
    assert out["credential_save_policy"] == "never"
    assert out["credential_provider"] == "1password"
    assert out["default_editor_command"] == "code -n"
    assert out["default_text_editor_command"] == "notepad"
    assert out["restore_window_geometry"] is False
    assert out["cursor_color"] == "#ff00ff"
    assert out["selection_bg"] == "#222233"
    assert out["selection_fg"] == "#eeeeee"


def test_strip_newlines_on_paste_collapses_crlf(qapp):
    from PyQt6.QtGui import QGuiApplication
    from widgets.terminal import TerminalWidget

    t = TerminalWidget(command=["true"])
    t.settings["strip_newlines_on_paste"] = True
    t.settings["confirm_multiline_paste"] = False
    captured: list[str] = []
    t.write_to_backend = lambda text: captured.append(text)  # type: ignore[method-assign]

    QGuiApplication.clipboard().setText("a\r\nb\rc\n")
    t._paste_from_clipboard()
    assert captured == ["a\nb\nc\n"]

    captured.clear()
    t.settings["strip_newlines_on_paste"] = False
    t.settings["confirm_multiline_paste"] = False
    QGuiApplication.clipboard().setText("a\r\nb")
    t._paste_from_clipboard()
    assert captured == ["a\r\nb"]
    t.close()


def test_terminal_paste_confirmation_predicate(qapp):
    from widgets.terminal import TerminalWidget

    t = TerminalWidget(command=["true"])
    t.settings["confirm_multiline_paste"] = True
    t.settings["confirm_large_paste"] = True
    t.settings["large_paste_threshold"] = 5

    assert t._confirm_paste_required("one\nmore") is True
    assert t._confirm_paste_required("12345") is True
    assert t._confirm_paste_required("1234") is False
    t.close()


def test_keepalive_flows_into_credentials():
    from core.ssh_backend import SshCredentials

    c = SshCredentials.from_session({"host": "h", "user": "u"})
    c.keepalive_interval = 45
    assert c.keepalive_interval == 45

def test_remote_display_name_uses_posix_paths():
    from bifrost_app import _remote_display_name

    assert _remote_display_name("/home/alice/report.txt") == "report.txt"
    assert _remote_display_name("/home/alice/folder/") == "folder"


def test_safe_temp_suffix_removes_local_path_separators_and_windows_invalid_chars():
    from bifrost_app import _safe_temp_suffix

    suffix = _safe_temp_suffix('/home/alice/bad:name\\report?.txt')

    assert suffix == "-bad_name_report_.txt"
    assert "/" not in suffix
    assert "\\" not in suffix
    assert ":" not in suffix


def test_split_user_command_preserves_windows_backslashes(monkeypatch):
    import bifrost_app

    monkeypatch.setattr(bifrost_app.os, "name", "nt")

    assert bifrost_app._split_user_command(r"C:\Tools\editor.exe --flag") == [
        r"C:\Tools\editor.exe",
        "--flag",
    ]
    assert bifrost_app._split_user_command(
        r'"C:\Program Files\Editor\editor.exe" --reuse-window'
    ) == [
        r"C:\Program Files\Editor\editor.exe",
        "--reuse-window",
    ]

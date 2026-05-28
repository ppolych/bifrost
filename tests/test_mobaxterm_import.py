from core.mobaxterm_import import ROOT_GROUP, parse_mobaxterm_file


def _ssh_line(host, port="22", user="", command="", key_path="", agent_forwarding=False):
    fields = [""] * 39
    fields[0] = "0"
    fields[1] = host
    fields[2] = port
    fields[3] = user
    fields[7] = command
    fields[14] = key_path
    fields[34] = "-1" if agent_forwarding else "0"
    return "#109#" + "%".join(fields) + "#MobaFont%10"


def test_parse_mobaxterm_ssh_sessions(tmp_path, monkeypatch):
    monkeypatch.setenv("SystemDrive", "C:")
    path = tmp_path / "sessions.mxtsessions"
    path.write_text(
        "\r\n".join(
            [
                "[Bookmarks]",
                "SubRep=",
                "ImgNum=42",
                "Root SSH="
                + _ssh_line(
                    "root.example.com",
                    port="2222",
                    user="admin",
                    key_path="_CurrentDrive_\\Users\\me\\.ssh\\id_ed25519",
                ),
                "",
                "[Bookmarks_1]",
                "SubRep=Production\\Routers",
                "ImgNum=41",
                "Core Router=" + _ssh_line("10.0.0.1", user="netops", command="show version__PTVIRG__ exit"),
                "Unsupported=#91#5%rdp.example.com%3389%user#MobaFont%10",
            ]
        ),
        encoding="cp1252",
    )

    result = parse_mobaxterm_file(str(path))

    assert result.imported == 2
    assert result.skipped == 1
    imported = result.tree[ROOT_GROUP]
    assert imported["Sessions"][0] == {
        "name": "Root SSH",
        "type": "SSH",
        "host": "root.example.com",
        "port": "2222",
        "user": "admin",
        "auth": "key",
        "key_path": "C:\\Users\\me\\.ssh\\id_ed25519",
        "overrides": {"font": None, "scheme": "Default"},
    }
    nested = imported["Production"]["Routers"][0]
    assert nested["name"] == "Core Router"
    assert nested["host"] == "10.0.0.1"
    assert nested["command"] == "show version; exit"


def test_parse_mobaxterm_skips_file_without_supported_sessions(tmp_path):
    path = tmp_path / "sessions.mxtsessions"
    path.write_text(
        "[Bookmarks]\nSubRep=\nImgNum=42\nRDP=#91#5%rdp.example.com%3389%user#MobaFont%10\n",
        encoding="cp1252",
    )

    result = parse_mobaxterm_file(str(path))

    assert result.imported == 0
    assert result.skipped == 1
    assert result.tree[ROOT_GROUP] == []

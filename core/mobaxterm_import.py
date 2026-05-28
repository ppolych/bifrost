from __future__ import annotations

import configparser
import os
from dataclasses import dataclass, field


BOOKMARK_PREFIX = "Bookmarks"
ROOT_GROUP = "MobaXterm imports"


@dataclass
class ImportResult:
    tree: dict
    imported: int = 0
    skipped: int = 0


@dataclass
class _Folder:
    children: dict[str, "_Folder"] = field(default_factory=dict)
    sessions: list[dict] = field(default_factory=list)


def parse_mobaxterm_file(path: str) -> ImportResult:
    """Parse MobaXterm .mxtsessions / MobaXterm.ini bookmark sections."""
    parser = configparser.ConfigParser(
        interpolation=None,
        strict=False,
        delimiters=("=",),
    )
    parser.optionxform = str
    with open(path, "r", encoding="cp1252") as fh:
        parser.read_file(fh)

    root = _Folder()
    imported = 0
    skipped = 0

    for section in parser.sections():
        if not section.startswith(BOOKMARK_PREFIX):
            continue
        folder_path = _split_subrep(parser.get(section, "SubRep", fallback=""))
        folder = _folder_at(root, folder_path)
        for name, value in parser.items(section):
            if name in {"SubRep", "ImgNum"}:
                continue
            session = _parse_session(name, value)
            if session is None:
                skipped += 1
                continue
            folder.sessions.append(session)
            imported += 1

    return ImportResult(tree={ROOT_GROUP: _folder_to_bifrost(root)}, imported=imported, skipped=skipped)


def _split_subrep(value: str) -> list[str]:
    return [part.strip() for part in value.split("\\") if part.strip()]


def _folder_at(root: _Folder, path: list[str]) -> _Folder:
    node = root
    for part in path:
        node = node.children.setdefault(part, _Folder())
    return node


def _folder_to_bifrost(folder: _Folder):
    if not folder.children:
        return folder.sessions
    out = {name: _folder_to_bifrost(child) for name, child in folder.children.items()}
    if folder.sessions:
        out["Sessions"] = folder.sessions
    return out


def _parse_session(name: str, value: str) -> dict | None:
    first_group = _first_percent_group(value)
    if not first_group:
        return None
    fields = first_group.split("%")
    if len(fields) < 4 or fields[0] != "0":
        return None

    host = _decode_token(fields[1])
    if not host:
        return None

    port = _decode_token(fields[2]) or "22"
    user = _decode_token(fields[3])
    if user == "<default>":
        user = ""

    key_path = _field(fields, 14)
    command = _field(fields, 7)
    agent_forwarding = _field(fields, 34) == "-1"

    session = {
        "name": name.strip() or host,
        "type": "SSH",
        "host": host,
        "port": port,
        "auth": "key" if key_path else "agent",
        "overrides": {"font": None, "scheme": "Default"},
    }
    if user:
        session["user"] = user
    if key_path:
        session["key_path"] = key_path
    if command:
        session["command"] = command
    if agent_forwarding:
        session["agent_forwarding"] = True
    return session


def _first_percent_group(value: str) -> str | None:
    for part in value.strip().split("#"):
        if "%" in part:
            return part
    return None


def _field(fields: list[str], index: int) -> str:
    if index >= len(fields):
        return ""
    return _decode_token(fields[index])


def _decode_token(value: str) -> str:
    value = (value or "").strip()
    if value in {"", "<none>"}:
        return ""
    current_drive = os.environ.get("SystemDrive", "C:")
    replacements = {
        "__PIPE__": "|",
        "__DBLQUO__": '"',
        "__PTVIRG__": ";",
        "__PERCENT__": "%",
        "_CurrentDrive_": current_drive,
    }
    for old, new in replacements.items():
        value = value.replace(old, new)
    return value

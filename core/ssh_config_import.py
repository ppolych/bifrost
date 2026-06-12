from __future__ import annotations

import os
import shlex
from dataclasses import dataclass


ROOT_GROUP = "SSH config imports"


@dataclass
class SshConfigImportResult:
    tree: dict
    imported: int = 0
    skipped: int = 0


def parse_ssh_config_file(path: str) -> SshConfigImportResult:
    with open(os.path.expanduser(path), "r", encoding="utf-8") as fh:
        return parse_ssh_config(fh.read())


def parse_ssh_config(text: str) -> SshConfigImportResult:
    hosts: list[tuple[list[str], dict[str, list[str]]]] = []
    current_patterns: list[str] = []
    current_options: dict[str, list[str]] = {}

    def flush_current() -> None:
        if current_patterns:
            hosts.append((list(current_patterns), dict(current_options)))

    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue
        parts = shlex.split(line, comments=False, posix=True)
        if len(parts) < 2:
            continue
        key = parts[0].lower()
        values = parts[1:]
        if key == "host":
            flush_current()
            current_patterns = values
            current_options = {}
            continue
        if current_patterns:
            current_options.setdefault(key, []).append(" ".join(values))

    flush_current()

    sessions = []
    skipped = 0
    for patterns, options in hosts:
        for pattern in patterns:
            if _is_concrete_host(pattern):
                sessions.append(_session_from_host(pattern, options))
            else:
                skipped += 1

    return SshConfigImportResult(
        tree={ROOT_GROUP: sessions},
        imported=len(sessions),
        skipped=skipped,
    )


def _strip_comment(line: str) -> str:
    escaped = False
    quote = ""
    for idx, ch in enumerate(line):
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if quote:
            if ch == quote:
                quote = ""
            continue
        if ch in {"'", '"'}:
            quote = ch
            continue
        if ch == "#":
            return line[:idx]
    return line


def _is_concrete_host(pattern: str) -> bool:
    return bool(pattern) and not pattern.startswith("!") and not any(ch in pattern for ch in "*?")


def _first(options: dict[str, list[str]], key: str, default: str = "") -> str:
    values = options.get(key.lower()) or []
    return values[0] if values else default


def _session_from_host(alias: str, options: dict[str, list[str]]) -> dict:
    host = _first(options, "hostname", alias)
    port = _first(options, "port", "22")
    user = _first(options, "user", "")
    identity = _first(options, "identityfile", "")
    cert = _first(options, "certificatefile", "")
    forward_agent = _first(options, "forwardagent", "").lower() in {"yes", "true", "1"}

    session = {
        "name": alias,
        "type": "SSH",
        "host": host,
        "port": port,
        "auth": "key" if identity else "agent",
        "overrides": {"font": None, "scheme": "Default"},
    }
    if user:
        session["user"] = user
    if identity:
        session["key_path"] = identity
    if cert:
        session["certificate_path"] = cert
    if forward_agent:
        session["agent_forwarding"] = True
    proxy_jump = _first(options, "proxyjump")
    if proxy_jump and proxy_jump.lower() != "none":
        session["proxy_jump"] = proxy_jump
    proxy_command = _first(options, "proxycommand")
    if proxy_command and proxy_command.lower() != "none":
        session["proxy_command"] = proxy_command
    tunnels = _tunnels_from_options(options)
    if tunnels:
        session["tunnels"] = tunnels
    return session


def _tunnels_from_options(options: dict[str, list[str]]) -> list[str]:
    tunnels = []
    for value in options.get("localforward", []):
        tunnels.append(f"L {value}")
    for value in options.get("remoteforward", []):
        tunnels.append(f"R {value}")
    for value in options.get("dynamicforward", []):
        tunnels.append(f"D {value}")
    return tunnels

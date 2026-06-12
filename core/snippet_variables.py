import platform


class _SnippetValues(dict):
    def __missing__(self, key):
        return "{" + key + "}"


def snippet_values(session: dict | None = None) -> dict[str, str]:
    values = {
        "name": "",
        "type": "",
        "host": "",
        "user": "",
        "port": "",
        "auth": "",
        "command": "",
        "proxy_jump": "",
        "local_os": platform.system(),
    }
    if isinstance(session, dict):
        for key in values:
            if key in session:
                values[key] = str(session.get(key) or "")
    return values


def expand_snippet(text: str, session: dict | None = None) -> str:
    try:
        return text.format_map(_SnippetValues(snippet_values(session)))
    except (ValueError, TypeError):
        return text

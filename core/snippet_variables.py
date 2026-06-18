import platform
import re

# Matches a doubled brace (`{{` / `}}`, e.g. Go templates) OR a single-brace
# placeholder around a bare identifier (`{host}`). Doubled braces are matched
# first so they're left untouched rather than mistaken for placeholders.
_PLACEHOLDER = re.compile(r"\{\{|\}\}|\{(\w+)\}")


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
    """Substitute `{known_var}` placeholders, leaving everything else verbatim.

    Deliberately not `str.format_map`: that collapses `{{...}}` (Go templates,
    common in Docker `-f` snippets) into single braces and raises on attribute
    access like `{name.upper}`. A targeted regex only touches the placeholders
    we know about — unknown names, doubled braces, `${VAR}`, and `awk '{...}'`
    all pass through unchanged.
    """
    values = snippet_values(session)

    def _replace(match: re.Match) -> str:
        name = match.group(1)
        if name is None:  # a `{{` or `}}` token — leave as written
            return match.group(0)
        if name in values:
            return values[name]
        return match.group(0)  # unknown placeholder preserved

    return _PLACEHOLDER.sub(_replace, text)

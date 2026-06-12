import re
import shlex


TMUX_PRESETS = {
    "Attach or create": "attach_or_create",
    "Attach existing": "attach_existing",
    "New named session": "new_named",
}

_TMUX_NAME_UNSAFE = re.compile(r"[^A-Za-z0-9_.-]+")


def tmux_session_name(session_name: str = "", host: str = "") -> str:
    raw = (session_name or host or "main").strip()
    name = _TMUX_NAME_UNSAFE.sub("_", raw).strip("._-")
    return name or "main"


def tmux_command(preset: str, session_name: str = "", host: str = "") -> str:
    name = shlex.quote(tmux_session_name(session_name, host))
    if preset == "attach_existing":
        return f"tmux attach-session -t {name}"
    if preset == "new_named":
        return f"tmux new-session -s {name}"
    return f"tmux new-session -A -s {name}"

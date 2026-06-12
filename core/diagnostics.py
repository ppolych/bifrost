import os

from core.security import redact_text


def diagnostic_text(value: object) -> str:
    return _home_to_tilde(redact_text(value))


def _home_to_tilde(value: str) -> str:
    home = os.path.expanduser("~")
    if not home or home == "~":
        return value
    return value.replace(home, "~")

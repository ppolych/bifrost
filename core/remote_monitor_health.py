import re
import time


OK = "#8bd17c"
WARN = "#f59e0b"
CRIT = "#ef4444"
INFO = "#60a5fa"
MUTED = "#cccccc"


def percent_value(text: object) -> int | None:
    match = re.search(r"(\d+)%", str(text or ""))
    return int(match.group(1)) if match else None


def health_color(percent: int | None, *, warn: int = 80, crit: int = 95) -> str:
    if percent is None:
        return MUTED
    if percent >= crit:
        return CRIT
    if percent >= warn:
        return WARN
    return OK


def disk_worst_percent(disks: object) -> int | None:
    values = [percent_value(disk) for disk in disks or []]
    values = [value for value in values if value is not None]
    return max(values) if values else None


def freshness_text(updated_at: float | None, now: float | None = None) -> str:
    if updated_at is None:
        return "not updated"
    age = max(0, int((now or time.monotonic()) - updated_at))
    return f"updated {age}s ago"


def is_stale(updated_at: float | None, interval_ms: int, now: float | None = None) -> bool:
    if updated_at is None:
        return False
    max_age = max(1.0, interval_ms / 1000 * 2)
    return ((now or time.monotonic()) - updated_at) > max_age

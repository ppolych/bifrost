import subprocess
import sys


def is_wsl_available() -> bool:
    return sys.platform == "win32"


def list_distros() -> list[str]:
    """Return installed WSL distro names, or [] if WSL isn't available."""
    if not is_wsl_available():
        return []
    try:
        result = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if result.returncode != 0:
        return []
    raw = _decode_wsl_list_output(result.stdout)
    distros = [line.strip() for line in raw.splitlines() if line.strip()]
    return distros


def _decode_wsl_list_output(data: bytes) -> str:
    # `wsl.exe --list --quiet` normally emits UTF-16LE with NUL padding, but
    # tests and some wrapper environments can produce UTF-8.
    if b"\x00" in data:
        return data.decode("utf-16-le", errors="ignore").replace("\x00", "")
    return data.decode("utf-8", errors="replace")


def spawn_command(distro: str | None = None) -> list[str]:
    """Build the argv for launching a WSL shell, optionally pinned to a distro."""
    if distro:
        return ["wsl.exe", "-d", distro]
    return ["wsl.exe"]

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
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    # `wsl.exe --list --quiet` emits UTF-16LE with NUL padding.
    raw = result.stdout.decode("utf-16-le", errors="ignore")
    distros = [line.strip() for line in raw.splitlines() if line.strip()]
    return distros


def spawn_command(distro: str | None = None) -> list[str]:
    """Build the argv for launching a WSL shell, optionally pinned to a distro."""
    if distro:
        return ["wsl.exe", "-d", distro]
    return ["wsl.exe"]

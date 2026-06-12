"""External RDP launcher helpers.

Bifrost does not embed an RDP client. It delegates to the platform-native or
commonly installed external client while keeping session parsing testable.
"""

from __future__ import annotations

import platform
import shutil
import subprocess


DEFAULT_RDP_PORT = 3389


class RdpLaunchError(RuntimeError):
    pass


def normalize_rdp_port(value) -> int:
    text = str(value or "").strip()
    return int(text) if text.isdigit() else DEFAULT_RDP_PORT


def rdp_target(host: str, port) -> str:
    clean_host = (host or "localhost").strip() or "localhost"
    return f"{clean_host}:{normalize_rdp_port(port)}"


def build_rdp_command(
    session: dict,
    *,
    system: str | None = None,
    which=shutil.which,
) -> list[str]:
    system_name = system or platform.system()
    host = session.get("host") or "localhost"
    port = session.get("port")
    user = (session.get("user") or "").strip()
    target = rdp_target(host, port)

    if system_name == "Windows":
        executable = which("mstsc.exe") or which("mstsc") or "mstsc.exe"
        return [executable, f"/v:{target}"]

    if system_name == "Darwin":
        opener = which("open") or "open"
        return [opener, f"rdp://full%20address=s:{target}"]

    xfreerdp = which("xfreerdp")
    if xfreerdp:
        command = [xfreerdp, f"/v:{target}"]
        if user:
            command.append(f"/u:{user}")
        return command

    rdesktop = which("rdesktop")
    if rdesktop:
        command = [rdesktop]
        if user:
            command.extend(["-u", user])
        command.append(target)
        return command

    raise RdpLaunchError(
        "No RDP client found. Install xfreerdp or rdesktop on Linux, "
        "Microsoft Remote Desktop on macOS, or use mstsc on Windows."
    )


def launch_rdp_session(session: dict) -> list[str]:
    command = build_rdp_command(session)
    try:
        subprocess.Popen(command)
    except OSError as e:
        raise RdpLaunchError(str(e) or e.__class__.__name__) from e
    return command

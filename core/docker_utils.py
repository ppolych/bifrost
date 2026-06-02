import subprocess
import logging
import shlex

log = logging.getLogger(__name__)

DOCKER_PS_FORMAT = "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}"

def parse_containers(output: str):
    containers = []
    for line in (output or "").strip().split("\n"):
        if not line:
            continue
        parts = line.split("|")
        if len(parts) == 4:
            containers.append({
                "id": parts[0],
                "name": parts[1],
                "image": parts[2],
                "status": parts[3],
            })
    return containers

def list_containers():
    """Return a list of dicts with container info."""
    try:
        # Get ID, Names, Image, Status
        cmd = ["docker", "ps", "-a", "--format", DOCKER_PS_FORMAT]
        output = subprocess.check_output(cmd, text=True, timeout=5)
        return parse_containers(output)
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []

def list_remote_containers(backend):
    command = f"docker ps -a --format {shlex.quote(DOCKER_PS_FORMAT)}"
    try:
        code, out, err = backend.exec_command_text(command, timeout=8)
    except Exception as e:
        log.debug("remote docker ps failed", exc_info=True)
        return [], str(e) or e.__class__.__name__
    if code != 0:
        return [], err.strip() or f"docker ps exited with {code}"
    return parse_containers(out), ""

def container_action(container_name, action, backend=None):
    """Run a basic docker container lifecycle action."""
    if action not in {"start", "stop", "restart"}:
        raise ValueError(f"Unsupported docker action: {action}")
    if backend is not None:
        command = f"docker {action} {shlex.quote(container_name)}"
        try:
            code, _out, err = backend.exec_command_text(command, timeout=20)
        except Exception as e:
            log.debug("remote docker %s failed", action, exc_info=True)
            return False, str(e) or e.__class__.__name__
        return code == 0, "" if code == 0 else (err.strip() or f"docker {action} exited with {code}")
    try:
        subprocess.run(
            ["docker", action, container_name],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        )
        return True, ""
    except (subprocess.CalledProcessError, FileNotFoundError, OSError) as e:
        stderr = getattr(e, "stderr", "") or str(e)
        return False, stderr.strip()

def exec_shell_command(container_name):
    """Return the command list to exec into a container shell."""
    return ["docker", "exec", "-it", container_name, "/bin/sh", "-c", "[ -e /bin/bash ] && /bin/bash || /bin/sh"]

def exec_shell_remote_command(container_name):
    return f"docker exec -it {shlex.quote(container_name)} /bin/sh -c '[ -e /bin/bash ] && exec /bin/bash || exec /bin/sh'"

def logs_command(container_name):
    return ["docker", "logs", "-f", container_name]

def remote_logs_text(backend, container_name, tail=200):
    command = f"docker logs --tail {int(tail)} {shlex.quote(container_name)}"
    try:
        code, out, err = backend.exec_command_text(command, timeout=15)
    except Exception as e:
        log.debug("remote docker logs failed", exc_info=True)
        return False, str(e) or e.__class__.__name__
    if code != 0:
        return False, err.strip() or f"docker logs exited with {code}"
    return True, out

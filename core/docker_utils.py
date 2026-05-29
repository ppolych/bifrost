import subprocess
import logging

log = logging.getLogger(__name__)

def list_containers():
    """Return a list of dicts with container info."""
    try:
        # Get ID, Names, Image, Status
        cmd = ["docker", "ps", "--format", "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}"]
        output = subprocess.check_output(cmd, text=True, timeout=5)
        containers = []
        for line in output.strip().split("\n"):
            if not line: continue
            parts = line.split("|")
            if len(parts) == 4:
                containers.append({
                    "id": parts[0],
                    "name": parts[1],
                    "image": parts[2],
                    "status": parts[3]
                })
        return containers
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        return []

def exec_shell_command(container_name):
    """Return the command list to exec into a container shell."""
    return ["docker", "exec", "-it", container_name, "/bin/sh", "-c", "[ -e /bin/bash ] && /bin/bash || /bin/sh"]

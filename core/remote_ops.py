from dataclasses import dataclass


@dataclass(frozen=True)
class RemoteAction:
    label: str
    command: str
    timeout: float = 12.0


REMOTE_ACTIONS = [
    RemoteAction("Uptime", "uptime"),
    RemoteAction("Disk", "df -h"),
    RemoteAction("Memory", "free -m || vm_stat"),
    RemoteAction("Failed services", "systemctl --failed --no-pager || true"),
    RemoteAction("Docker", "docker ps --format 'table {{.Names}}\\t{{.Status}}\\t{{.Image}}'"),
    RemoteAction("Kubernetes", "kubectl get pods -A"),
]

import logging
from core.platform_utils import atomic_write_json, config_path, load_json

log = logging.getLogger(__name__)

class SnippetManager:
    def __init__(self, filename: str = "snippets.json"):
        self.filename = config_path(filename)
        self.snippets = self.load()

    def load(self):
        return load_json(self.filename, {
            "Docker": {
                "List Containers": "docker ps -a",
                "Container Logs": "docker logs -f ",
                "Container Shell": "docker exec -it  /bin/sh",
            },
            "System": {
                "Disk Usage": "df -h",
                "Memory Usage": "free -m",
                "Open Ports": "ss -tulpen || netstat -tulpen",
            },
            "SSH": {
                "Tmux Attach": "tmux new-session -A -s {name}",
                "Remote Identity": "printf 'host={host} user={user} port={port}\\n'",
            },
            "Kubernetes": {
                "Pods": "kubectl get pods -A",
                "Events": "kubectl get events -A --sort-by=.lastTimestamp",
            }
        })

    def save(self):
        try:
            atomic_write_json(self.filename, self.snippets)
        except OSError:
            log.exception("Failed to save snippets to %s", self.filename)

    def add_snippet(self, group, name, command):
        group = (group or "").strip()
        name = (name or "").strip()
        command = (command or "").strip()
        if not group or not name or not command:
            raise ValueError("Group, name, and command are required")
        if group not in self.snippets:
            self.snippets[group] = {}
        self.snippets[group][name] = command
        self.save()

    def update_snippet(self, group, old_name, new_group, new_name, command):
        if self.delete_snippet(group, old_name):
            self.add_snippet(new_group, new_name, command)
            return True
        return False

    def delete_snippet(self, group, name):
        if group in self.snippets and name in self.snippets[group]:
            del self.snippets[group][name]
            if not self.snippets[group]:
                del self.snippets[group]
            self.save()
            return True
        return False

    def get_snippet(self, group, name):
        return self.snippets.get(group, {}).get(name)

import logging

from core.platform_utils import atomic_write_json, config_path, load_json

log = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, filename: str = "sessions.json"):
        self.filename = config_path(filename)
        self.sessions = self.load()
        self.recent_sessions: list[str] = []

    def load(self):
        return load_json(self.filename, self.get_defaults())

    def save(self):
        try:
            atomic_write_json(self.filename, self.sessions)
        except OSError:
            log.exception("Failed to save sessions to %s", self.filename)

    def get_defaults(self):
        return {
            "Local sessions": [
                {"name": "Local Shell", "type": "Local", "favorite": True},
            ],
            "User sessions": [],
            "Work Folders": {
                "Production": [],
                "Staging": [],
            },
        }

    def add_session(self, path, session_data):
        parts = path.split("/")
        target = self.sessions
        for part in parts[:-1]:
            if part not in target:
                target[part] = {}
            target = target[part]

        last_part = parts[-1]
        if last_part not in target:
            target[last_part] = []

        if isinstance(target[last_part], list):
            target[last_part].append(session_data)

        self.save()
        self.add_to_recents(session_data["name"])

    def add_to_recents(self, name):
        if name in self.recent_sessions:
            self.recent_sessions.remove(name)
        self.recent_sessions.insert(0, name)
        if len(self.recent_sessions) > 10:
            self.recent_sessions.pop()

    def export_sessions(self, export_path):
        atomic_write_json(export_path, self.sessions)

    def import_sessions(self, import_path):
        merged = load_json(import_path, None)
        if not isinstance(merged, dict):
            log.warning("Refusing to import non-dict session data from %s", import_path)
            return
        self.sessions.update(merged)
        self.save()

    def find_by_name(self, name: str) -> dict | None:
        """Walk the nested folder/list structure and return the first session matching `name`."""
        return _walk_for_name(self.sessions, name)


def _walk_for_name(node, name: str):
    if isinstance(node, dict):
        for value in node.values():
            hit = _walk_for_name(value, name)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and item.get("name") == name:
                return item
    return None

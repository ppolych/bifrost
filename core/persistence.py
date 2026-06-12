import copy
import logging

from core import security, session_crypto
from core.platform_utils import atomic_write_json, config_path, load_json
from core.session_tree import (
    insert_after_in_dict,
    list_at,
    rename_dict_key,
    resolve_container,
    session_index,
    uniquify_key,
    uniquify_name,
    walk_for_name,
)

log = logging.getLogger(__name__)


class SessionManager:
    def __init__(self, filename: str = "sessions.json"):
        self.filename = config_path(filename)
        self.sessions = self.load()
        self.recent_sessions: list[str] = []

    def load(self):
        data = load_json(self.filename, self.get_defaults())
        return data if isinstance(data, dict) else self.get_defaults()

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
        atomic_write_json(export_path, security.sanitize_for_export(self.sessions))

    def export_sessions_encrypted(self, export_path, password: str):
        atomic_write_json(
            export_path,
            session_crypto.encrypt_sessions(security.sanitize_for_export(self.sessions), password),
        )

    def import_sessions(self, import_path):
        merged = load_json(import_path, None)
        if session_crypto.is_encrypted_session_file(merged):
            raise ValueError("Encrypted session file requires a password")
        if not isinstance(merged, dict):
            log.warning("Refusing to import non-dict session data from %s", import_path)
            return
        self.sessions.update(merged)
        self.save()

    def import_sessions_encrypted(self, import_path, password: str):
        merged = session_crypto.decrypt_sessions(load_json(import_path, None), password)
        self.sessions.update(merged)
        self.save()

    def import_group(self, group_name: str, data) -> str:
        """Import a top-level group without overwriting an existing group."""
        unique = uniquify_key(self.sessions, group_name)
        self.sessions[unique] = data
        self.save()
        return unique

    def find_by_name(self, name: str) -> dict | None:
        """Walk the nested folder/list structure and return the first session matching `name`."""
        return walk_for_name(self.sessions, name)

    # ----- folder / group ops -----
    #
    # Data model invariant: a folder's value is *either* a dict (sub-groups)
    # *or* a list (sessions). The two can't be mixed at the same level. Empty
    # containers are malleable — an empty [] becomes {} on first sub-group add,
    # and vice versa for sessions. Non-empty containers refuse the wrong kind.

    def add_subgroup(self, parent_path, name: str) -> str | None:
        """Create an empty sub-group under `parent_path` (list of folder names,
        empty for root). Returns the (possibly uniquified) name, or None if
        the parent doesn't exist."""
        if not parent_path:
            parent = self.sessions
        else:
            container, key = resolve_container(self.sessions, parent_path)
            if container is None:
                return None
            target = container[key]
            if isinstance(target, list) and not target:
                container[key] = {}
                target = container[key]
            if not isinstance(target, dict):
                raise ValueError(
                    "This group already contains sessions; sessions and "
                    "sub-groups can't be mixed at the same level."
                )
            parent = target
        unique = uniquify_key(parent, name)
        parent[unique] = []
        self.save()
        return unique

    def add_session_at(self, parent_path, session_data: dict) -> str | None:
        """Add a session into the folder at `parent_path` (list of folder
        names). Empty parent dict is converted to a list. Returns the
        (possibly uniquified) session name, or None if the parent doesn't
        exist."""
        if not parent_path:
            # Fall back to the historical default landing zone.
            return self.add_session("User sessions", session_data) or session_data.get("name")
        container, key = resolve_container(self.sessions, parent_path)
        if container is None:
            return None
        target = container[key]
        if isinstance(target, dict) and not target:
            container[key] = []
            target = container[key]
        if not isinstance(target, list):
            raise ValueError(
                "This group contains sub-groups; pick one of them, or "
                "create the session under a different group."
            )
        existing_names = {s.get("name", "") for s in target if isinstance(s, dict)}
        original = session_data.get("name", "session")
        unique = uniquify_name(existing_names, original)
        if unique != original:
            session_data = dict(session_data)
            session_data["name"] = unique
        target.append(session_data)
        self.save()
        self.add_to_recents(unique)
        return unique

    def rename_folder(self, path, new_name: str) -> bool:
        """Rename the folder at `path`. Refuses if `new_name` collides with a
        sibling. Preserves the folder's position in the parent dict."""
        if not path:
            return False
        new_name = new_name.strip()
        if not new_name:
            return False
        if not path[:-1]:
            parent = self.sessions
        else:
            container, key = resolve_container(self.sessions, path[:-1])
            if container is None:
                return False
            parent = container[key]
        if not isinstance(parent, dict):
            return False
        old = path[-1]
        if old not in parent:
            return False
        if new_name == old:
            return True
        if new_name in parent:
            raise ValueError(f"A group named “{new_name}” already exists here.")
        rename_dict_key(parent, old, new_name)
        self.save()
        return True

    def rename_session(self, parent_path, session: dict, new_name: str) -> bool:
        """Rename a session dict in the list at `parent_path`. Refuses if
        `new_name` collides with a sibling session."""
        new_name = new_name.strip()
        if not new_name:
            return False
        container = list_at(self.sessions, parent_path)
        idx = session_index(container, session) if container is not None else None
        if container is None or idx is None:
            return False
        if new_name == container[idx].get("name"):
            return True
        if any(i != idx and s.get("name") == new_name for i, s in enumerate(container)):
            raise ValueError(f"A session named “{new_name}” already exists here.")
        container[idx]["name"] = new_name
        self.save()
        return True

    def update_session(self, parent_path, session: dict, new_data: dict) -> bool:
        """Replace a session dict in-place while preserving list position."""
        container = list_at(self.sessions, parent_path)
        idx = session_index(container, session) if container is not None else None
        if container is None or idx is None:
            return False
        new_name = (new_data.get("name") or "").strip()
        if not new_name:
            return False
        if any(i != idx and s.get("name") == new_name for i, s in enumerate(container)):
            raise ValueError(f"A session named “{new_name}” already exists here.")
        container[idx].clear()
        container[idx].update(new_data)
        self.save()
        return True

    def delete_folder(self, path) -> bool:
        """Delete a folder/group at `path`, including all nested contents."""
        if not path:
            return False
        if not path[:-1]:
            parent = self.sessions
        else:
            container, key = resolve_container(self.sessions, path[:-1])
            if container is None:
                return False
            parent = container[key]
        if not isinstance(parent, dict):
            return False
        old = path[-1]
        if old not in parent:
            return False
        del parent[old]
        self.save()
        return True

    def delete_session(self, parent_path, session: dict) -> bool:
        """Delete a session dict from the list at `parent_path`."""
        container = list_at(self.sessions, parent_path)
        idx = session_index(container, session) if container is not None else None
        if container is None or idx is None:
            return False
        del container[idx]
        self.save()
        return True

    def duplicate_folder(self, path) -> str | None:
        """Deep-copy the folder at `path` into the same parent with a
        ‘(copy)’-suffixed name. Returns the new name, or None on failure."""
        if not path:
            return None
        if not path[:-1]:
            parent = self.sessions
        else:
            container, key = resolve_container(self.sessions, path[:-1])
            if container is None:
                return None
            parent = container[key]
        if not isinstance(parent, dict):
            return None
        old = path[-1]
        if old not in parent:
            return None
        new_name = uniquify_key(parent, f"{old} (copy)")
        insert_after_in_dict(parent, old, new_name, copy.deepcopy(parent[old]))
        self.save()
        return new_name

    def duplicate_session(self, parent_path, session: dict) -> dict | None:
        """Append a deep copy of `session` to the list at `parent_path` with
        a ‘(copy)’-suffixed name. Returns the new session dict, or None."""
        container = list_at(self.sessions, parent_path)
        idx = session_index(container, session) if container is not None else None
        if container is None or idx is None:
            return None
        clone = copy.deepcopy(container[idx])
        existing_names = {s.get("name", "") for s in container if isinstance(s, dict)}
        clone["name"] = uniquify_name(existing_names, f"{container[idx].get('name', 'session')} (copy)")
        container.insert(idx + 1, clone)
        self.save()
        return clone


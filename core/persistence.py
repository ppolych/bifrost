import copy
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

    def import_group(self, group_name: str, data) -> str:
        """Import a top-level group without overwriting an existing group."""
        unique = _uniquify_key(self.sessions, group_name)
        self.sessions[unique] = data
        self.save()
        return unique

    def find_by_name(self, name: str) -> dict | None:
        """Walk the nested folder/list structure and return the first session matching `name`."""
        return _walk_for_name(self.sessions, name)

    # ----- folder / group ops -----
    #
    # Data model invariant: a folder's value is *either* a dict (sub-groups)
    # *or* a list (sessions). The two can't be mixed at the same level. Empty
    # containers are malleable — an empty [] becomes {} on first sub-group add,
    # and vice versa for sessions. Non-empty containers refuse the wrong kind.

    def _resolve_container(self, path):
        """Return (parent_dict, key) so callers can read/replace the folder
        at the leaf of `path`. None if any segment is missing."""
        if not path:
            return None, None
        node = self.sessions
        for part in path[:-1]:
            if not isinstance(node, dict) or part not in node:
                return None, None
            node = node[part]
            if not isinstance(node, dict):
                return None, None
        last = path[-1]
        if not isinstance(node, dict) or last not in node:
            return None, None
        return node, last

    def add_subgroup(self, parent_path, name: str) -> str | None:
        """Create an empty sub-group under `parent_path` (list of folder names,
        empty for root). Returns the (possibly uniquified) name, or None if
        the parent doesn't exist."""
        if not parent_path:
            parent = self.sessions
        else:
            container, key = self._resolve_container(parent_path)
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
        unique = _uniquify_key(parent, name)
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
        container, key = self._resolve_container(parent_path)
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
        unique = _uniquify_name(existing_names, original)
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
            container, key = self._resolve_container(path[:-1])
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
        _rename_dict_key(parent, old, new_name)
        self.save()
        return True

    def rename_session(self, parent_path, session: dict, new_name: str) -> bool:
        """Rename a session dict in the list at `parent_path`. Refuses if
        `new_name` collides with a sibling session."""
        new_name = new_name.strip()
        if not new_name:
            return False
        container = self._list_at(parent_path)
        if container is None or session not in container:
            return False
        if new_name == session.get("name"):
            return True
        if any(s.get("name") == new_name for s in container if s is not session):
            raise ValueError(f"A session named “{new_name}” already exists here.")
        session["name"] = new_name
        self.save()
        return True

    def update_session(self, parent_path, session: dict, new_data: dict) -> bool:
        """Replace a session dict in-place while preserving list position."""
        container = self._list_at(parent_path)
        if container is None or session not in container:
            return False
        new_name = (new_data.get("name") or "").strip()
        if not new_name:
            return False
        if any(s.get("name") == new_name for s in container if s is not session):
            raise ValueError(f"A session named “{new_name}” already exists here.")
        session.clear()
        session.update(new_data)
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
            container, key = self._resolve_container(path[:-1])
            if container is None:
                return None
            parent = container[key]
        if not isinstance(parent, dict):
            return None
        old = path[-1]
        if old not in parent:
            return None
        new_name = _uniquify_key(parent, f"{old} (copy)")
        _insert_after_in_dict(parent, old, new_name, copy.deepcopy(parent[old]))
        self.save()
        return new_name

    def duplicate_session(self, parent_path, session: dict) -> dict | None:
        """Append a deep copy of `session` to the list at `parent_path` with
        a ‘(copy)’-suffixed name. Returns the new session dict, or None."""
        container = self._list_at(parent_path)
        if container is None or session not in container:
            return None
        clone = copy.deepcopy(session)
        existing_names = {s.get("name", "") for s in container if isinstance(s, dict)}
        clone["name"] = _uniquify_name(existing_names, f"{session.get('name', 'session')} (copy)")
        idx = container.index(session) + 1
        container.insert(idx, clone)
        self.save()
        return clone

    def _list_at(self, path):
        """Return the session list at `path`, or None if `path` doesn't point
        at a list-typed folder."""
        if not path:
            return None
        container, key = self._resolve_container(path)
        if container is None:
            return None
        target = container[key]
        return target if isinstance(target, list) else None


def _uniquify_key(d: dict, name: str) -> str:
    if name not in d:
        return name
    i = 2
    while f"{name} ({i})" in d:
        i += 1
    return f"{name} ({i})"


def _uniquify_name(taken, name: str) -> str:
    taken = set(taken)
    if name not in taken:
        return name
    i = 2
    while f"{name} ({i})" in taken:
        i += 1
    return f"{name} ({i})"


def _rename_dict_key(d: dict, old: str, new: str) -> None:
    """Rename in place, preserving insertion order."""
    out = {(new if k == old else k): v for k, v in d.items()}
    d.clear()
    d.update(out)


def _insert_after_in_dict(d: dict, after_key: str, new_key: str, new_value) -> None:
    """Insert (new_key, new_value) right after `after_key`, in place."""
    out = {}
    inserted = False
    for k, v in d.items():
        out[k] = v
        if k == after_key and not inserted:
            out[new_key] = new_value
            inserted = True
    if not inserted:
        out[new_key] = new_value
    d.clear()
    d.update(out)


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

"""Pure helpers for Bifrost's nested session tree."""


def uniquify_key(d: dict, name: str) -> str:
    if name not in d:
        return name
    i = 2
    while f"{name} ({i})" in d:
        i += 1
    return f"{name} ({i})"


def uniquify_name(taken, name: str) -> str:
    taken = set(taken)
    if name not in taken:
        return name
    i = 2
    while f"{name} ({i})" in taken:
        i += 1
    return f"{name} ({i})"


def session_index(container: list | None, session: dict) -> int | None:
    """Return the index for a session object or an equal dict from Qt item data."""
    if container is None:
        return None
    for i, item in enumerate(container):
        if item is session:
            return i
    for i, item in enumerate(container):
        if item == session:
            return i
    return None


def rename_dict_key(d: dict, old: str, new: str) -> None:
    """Rename in place, preserving insertion order."""
    out = {(new if k == old else k): v for k, v in d.items()}
    d.clear()
    d.update(out)


def insert_after_in_dict(d: dict, after_key: str, new_key: str, new_value) -> None:
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


def resolve_container(sessions: dict, path):
    """Return (parent_dict, key) for a tree path, or (None, None)."""
    if not path:
        return None, None
    node = sessions
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


def list_at(sessions: dict, path):
    """Return the session list at path, or None if path is not a list folder."""
    if not path:
        return None
    container, key = resolve_container(sessions, path)
    if container is None:
        return None
    target = container[key]
    return target if isinstance(target, list) else None


def walk_for_name(node, name: str):
    if isinstance(node, dict):
        for value in node.values():
            hit = walk_for_name(value, name)
            if hit is not None:
                return hit
    elif isinstance(node, list):
        for item in node:
            if isinstance(item, dict) and item.get("name") == name:
                return item
    return None

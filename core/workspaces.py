"""Workspace profiles for reopening a set of sessions together."""

from __future__ import annotations

import copy
import logging

from core.platform_utils import atomic_write_json, config_path, load_json

log = logging.getLogger(__name__)

WORKSPACES_FILE = "workspaces.json"
SECRET_KEYS = {"password", "passphrase"}


class WorkspaceManager:
    def __init__(self, filename: str = WORKSPACES_FILE):
        self.filename = config_path(filename)
        self.profiles = self.load()

    def load(self) -> dict:
        data = load_json(self.filename, {})
        return data if isinstance(data, dict) else {}

    def save(self) -> None:
        try:
            atomic_write_json(self.filename, self.profiles)
        except OSError:
            log.exception("Failed to save workspaces to %s", self.filename)

    def names(self) -> list[str]:
        return sorted(self.profiles.keys(), key=str.lower)

    def upsert(self, name: str, sessions: list[dict]) -> None:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Workspace name is required")
        cleaned = [_sanitize_session(s) for s in sessions if isinstance(s, dict)]
        if not cleaned:
            raise ValueError("Workspace has no SSH sessions to save")
        self.profiles[clean_name] = cleaned
        self.save()

    def get(self, name: str) -> list[dict]:
        sessions = self.profiles.get(name) or []
        return [copy.deepcopy(s) for s in sessions if isinstance(s, dict)]

    def delete(self, name: str) -> bool:
        if name not in self.profiles:
            return False
        del self.profiles[name]
        self.save()
        return True


def _sanitize_session(session: dict) -> dict:
    cleaned = {}
    for key, value in session.items():
        if key in SECRET_KEYS:
            continue
        cleaned[key] = copy.deepcopy(value)
    cleaned.setdefault("type", "SSH")
    cleaned.setdefault("name", cleaned.get("host") or "SSH session")
    return cleaned

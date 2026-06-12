"""Workspace profiles for reopening a set of sessions together."""

from __future__ import annotations

import copy
import logging

from core.platform_utils import atomic_write_json, config_path, load_json
from core.security import sanitize_for_export

log = logging.getLogger(__name__)

WORKSPACES_FILE = "workspaces.json"
WORKSPACE_SCHEMA_VERSION = 2


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

    def upsert(self, name: str, sessions: list[dict], layout: dict | None = None) -> None:
        clean_name = (name or "").strip()
        if not clean_name:
            raise ValueError("Workspace name is required")
        cleaned = [_sanitize_session(s) for s in sessions if isinstance(s, dict)]
        if not cleaned:
            raise ValueError("Workspace has no SSH sessions to save")
        self.profiles[clean_name] = {
            "version": WORKSPACE_SCHEMA_VERSION,
            "sessions": cleaned,
            "layout": _sanitize_layout(layout or {}),
        }
        self.save()

    def get(self, name: str) -> list[dict]:
        sessions = self.get_profile(name).get("sessions", [])
        return [copy.deepcopy(s) for s in sessions if isinstance(s, dict)]

    def get_profile(self, name: str) -> dict:
        profile = self.profiles.get(name) or {}
        if isinstance(profile, list):
            sessions = profile
            layout = {}
            version = 1
        elif isinstance(profile, dict):
            sessions = profile.get("sessions") or []
            layout = profile.get("layout") or {}
            version = profile.get("version", WORKSPACE_SCHEMA_VERSION)
        else:
            sessions = []
            layout = {}
            version = 1
        return {
            "version": copy.deepcopy(version),
            "sessions": [_sanitize_session(s) for s in sessions if isinstance(s, dict)],
            "layout": _sanitize_layout(layout if isinstance(layout, dict) else {}),
        }

    def delete(self, name: str) -> bool:
        if name not in self.profiles:
            return False
        del self.profiles[name]
        self.save()
        return True


def workspace_summary(sessions: list[dict]) -> str:
    counts: dict[str, int] = {}
    clustered = 0
    for session in sessions:
        kind = str(session.get("type") or "SSH")
        counts[kind] = counts.get(kind, 0) + 1
        if session.get("cluster"):
            clustered += 1
    parts = [f"{kind}: {counts[kind]}" for kind in sorted(counts)]
    if clustered:
        parts.append(f"Clustered: {clustered}")
    return ", ".join(parts) or "No sessions"


def _sanitize_session(session: dict) -> dict:
    cleaned = sanitize_for_export(session)
    cleaned.setdefault("type", "SSH")
    cleaned.setdefault("name", cleaned.get("host") or "SSH session")
    return cleaned


def _sanitize_layout(layout: dict) -> dict:
    cleaned: dict = {}
    for key in ("main_splitter_sizes", "sidebar_splitter_sizes"):
        value = layout.get(key)
        if isinstance(value, list) and len(value) == 2:
            sizes = []
            for item in value:
                try:
                    sizes.append(max(0, int(item)))
                except (TypeError, ValueError):
                    sizes = []
                    break
            if len(sizes) == 2:
                cleaned[key] = sizes
    for key in ("last_sidebar_tab", "active_tab"):
        try:
            value = int(layout.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            cleaned[key] = value
    return cleaned

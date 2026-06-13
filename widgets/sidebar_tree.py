from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QTreeWidgetItem

from core.icons import folder_icon, session_icon


class _SessionRef:
    def __init__(self, session: dict):
        self.session = session


def _session_tooltip(session: dict) -> str:
    name = session.get("name", "")
    proto = session.get("type", "")
    lines: list[str] = []
    if name:
        lines.append(f"<b>{name}</b>")
    if proto:
        lines.append(f"Type: {proto}")
    if session.get("host"):
        user = session.get("user", "") or ""
        host = session["host"]
        port = session.get("port", 22)
        target = f"{user}@{host}" if user else host
        lines.append(f"Target: {target}:{port}")
    if session.get("favorite"):
        lines.append("⭐ Favorite")
    tags = session.get("tags")
    if isinstance(tags, list) and tags:
        lines.append("Tags: " + ", ".join(str(tag) for tag in tags))
    return "<br>".join(lines) if lines else name


def _session_search_text(session: dict) -> str:
    tags = session.get("tags") if isinstance(session, dict) else []
    tag_text = " ".join(str(tag) for tag in tags) if isinstance(tags, list) else ""
    return " ".join([
        str(session.get("name", "")),
        str(session.get("type", "")),
        str(session.get("host", "")),
        str(session.get("user", "")),
        tag_text,
    ]).lower()


class SidebarTreeMixin:
    SESSION_ROLE = Qt.ItemDataRole.UserRole
    FOLDER_ROLE = Qt.ItemDataRole.UserRole + 1
    PATH_ROLE = Qt.ItemDataRole.UserRole + 2
    SESSION_OPEN_ROLE = Qt.ItemDataRole.UserRole + 3

    def _session_for_item(self, item):
        ref = item.data(0, self.SESSION_ROLE) if item is not None else None
        if isinstance(ref, _SessionRef):
            return ref.session
        return ref if isinstance(ref, dict) else None

    def refresh_sessions(self):
        self.tree.clear()
        self._populate_tree(self.session_manager.sessions, self.tree, [])
        self._filter_sessions(self.session_filter.text())

    def set_open_session_ids(self, session_ids: set[int]) -> None:
        self._open_session_ids = set(session_ids)
        self.refresh_sessions()

    def _populate_tree(self, data, parent, path):
        if isinstance(data, dict):
            for key, value in data.items():
                item_path = path + [key]
                item = QTreeWidgetItem(parent, [key])
                item.setIcon(0, folder_icon(is_open=False))
                item.setData(0, self.FOLDER_ROLE, True)
                item.setData(0, self.PATH_ROLE, item_path)
                self._populate_tree(value, item, item_path)
        elif isinstance(data, list):
            for session in sorted(
                data,
                key=lambda item: (not item.get("favorite"), item.get("name", "").lower()),
            ):
                name = session.get("name", "<unnamed>")
                is_open = id(session) in getattr(self, "_open_session_ids", set())
                item = QTreeWidgetItem(parent, [f"● {name}" if is_open else name])
                item.setIcon(0, session_icon(session))
                item.setData(0, self.SESSION_ROLE, _SessionRef(session))
                item.setData(0, self.PATH_ROLE, list(path))
                item.setData(0, self.SESSION_OPEN_ROLE, is_open)
                tooltip = _session_tooltip(session)
                if is_open:
                    tooltip += "<br>Open: double-click to focus the tab"
                item.setToolTip(0, tooltip)

    def _filter_sessions(self, text: str) -> None:
        needle = (text or "").strip().lower()

        def apply(item) -> bool:
            session = self._session_for_item(item)
            haystack = _session_search_text(session) if session else item.text(0).lower()
            self_match = needle in haystack or not needle
            child_match = False
            for i in range(item.childCount()):
                if apply(item.child(i)):
                    child_match = True
            visible = self_match or child_match
            item.setHidden(not visible)
            if needle and child_match:
                item.setExpanded(True)
            return visible

        for i in range(self.tree.topLevelItemCount()):
            apply(self.tree.topLevelItem(i))

    def refresh_macros(self):
        self.macro_tree.clear()
        for name in self.macro_engine.macros.keys():
            QTreeWidgetItem(self.macro_tree, [name])

    def on_session_click(self, item, column):
        session = self._session_for_item(item)
        if session:
            if item.data(0, self.SESSION_OPEN_ROLE):
                self.session_focus_requested.emit(session)
                return
            self.session_activated.emit(session)

    def _on_item_expanded(self, item):
        if item.data(0, self.FOLDER_ROLE):
            item.setIcon(0, folder_icon(is_open=True))

    def _on_item_collapsed(self, item):
        if item.data(0, self.FOLDER_ROLE):
            item.setIcon(0, folder_icon(is_open=False))

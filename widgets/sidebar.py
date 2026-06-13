from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QInputDialog, QMenu, QMessageBox, QWidget
from PyQt6.QtGui import QAction

from core.icons import named_icon
from widgets.sidebar_tree import SidebarTreeMixin
from widgets.sidebar_ui import build_sidebar_ui


class Sidebar(QWidget, SidebarTreeMixin):
    tool_triggered = pyqtSignal(str)
    session_activated = pyqtSignal(dict)       # full session dict
    session_focus_requested = pyqtSignal(dict) # focus an already-open session tab
    favorite_toggled = pyqtSignal(dict, bool)  # session, new state
    forget_credentials = pyqtSignal(dict)      # forget saved password / passphrase
    wake_on_lan = pyqtSignal(dict)             # send a WoL magic packet for this session
    new_session_requested = pyqtSignal(list)   # parent folder path; opens SessionDialog
    edit_session_requested = pyqtSignal(list, dict)
    edit_session_section_requested = pyqtSignal(list, dict, str)
    macro_triggered = pyqtSignal(str)
    snippet_triggered = pyqtSignal(str, bool)
    container_shell_requested = pyqtSignal(str, object)
    collapse_requested = pyqtSignal(bool)
    
    def __init__(self, session_manager, macro_engine, snippet_manager):
        super().__init__()
        self.session_manager = session_manager
        self.macro_engine = macro_engine
        self.snippet_manager = snippet_manager
        self.is_collapsed = False
        self._open_session_ids: set[int] = set()
        self._lazy_tab_builders: dict[int, object] = {}
        self._docker_widget = None
        build_sidebar_ui(self)
        self.tabs.currentChanged.connect(self._ensure_lazy_tab)
        self.refresh_sessions()
        self.refresh_macros()

    def _add_lazy_tab(self, icon, tooltip: str, builder) -> None:
        placeholder = QWidget()
        placeholder.setMinimumWidth(0)
        index = self.tabs.addTab(placeholder, icon, "")
        self.tabs.setTabToolTip(index, tooltip)
        self._lazy_tab_builders[index] = (builder, icon, tooltip)

    def _ensure_lazy_tab(self, index: int):
        entry = self._lazy_tab_builders.pop(index, None)
        if entry is None:
            return self.tabs.widget(index)
        builder, icon, tooltip = entry
        widget = builder()
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, widget, icon, "")
        self.tabs.setTabToolTip(index, tooltip)
        self.tabs.setCurrentIndex(index)
        return widget

    def _build_docker_tab(self):
        from widgets.docker_dashboard import DockerDashboard

        self._docker_widget = DockerDashboard()
        self._docker_widget.container_shell_requested.connect(self.container_shell_requested.emit)
        self.docker_widget = self._docker_widget
        return self._docker_widget

    def docker_widget_if_loaded(self):
        return self._docker_widget

    def toggle_collapse(self):
        self.is_collapsed = not self.is_collapsed
        # Hide the splitter (contains tabs + SFTP), not just the tab widget,
        # so collapsing reclaims all the sidebar width.
        self.content_splitter.setVisible(not self.is_collapsed)
        self.collapse_btn.setText("›" if self.is_collapsed else "‹")
        self.collapse_requested.emit(self.is_collapsed)

    def show_sftp_pane(self, sizes: tuple[int, int] = (500, 400)) -> None:
        """Expand the SFTP pane to a reasonable size (called when SSH attaches)."""
        current = self.content_splitter.sizes()
        if len(current) == 2 and current[1] == 0:
            self.content_splitter.setSizes(list(sizes))

    def hide_sftp_pane(self) -> None:
        """Collapse the SFTP pane back to zero height."""
        sizes = self.content_splitter.sizes()
        if len(sizes) == 2 and sizes[1] != 0:
            self.content_splitter.setSizes([sizes[0] + sizes[1], 0])

    def _show_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        session = self._session_for_item(item)

        if item is None:
            act_group = QAction("New top-level group…", self)
            act_group.triggered.connect(lambda: self._prompt_new_group([]))
            menu.addAction(act_group)
            collapse_all = QAction("Collapse all folders", self)
            collapse_all.triggered.connect(self.collapse_all_folders)
            menu.addAction(collapse_all)
        elif session:
            parent_path = list(item.data(0, self.PATH_ROLE) or [])
            if item.data(0, self.SESSION_OPEN_ROLE):
                focus = QAction("Focus open tab", self)
                focus.triggered.connect(lambda: self.session_focus_requested.emit(session))
                menu.addAction(focus)
            is_fav = bool(session.get("favorite"))
            toggle = QAction("Remove favorite" if is_fav else "Mark as favorite", self)
            toggle.triggered.connect(lambda: self._toggle_favorite(item))
            menu.addAction(toggle)
            connect = QAction("Connect", self)
            connect.triggered.connect(lambda: self.session_activated.emit(session))
            menu.addAction(connect)
            edit = QAction("Edit session...", self)
            edit.triggered.connect(lambda: self.edit_session_requested.emit(parent_path, session))
            menu.addAction(edit)
            edit_menu = menu.addMenu("Edit session section")
            advanced = QAction("Advanced SSH settings", self)
            advanced.triggered.connect(
                lambda: self.edit_session_section_requested.emit(parent_path, session, "advanced_ssh")
            )
            edit_menu.addAction(advanced)
            terminal = QAction("Terminal settings", self)
            terminal.triggered.connect(
                lambda: self.edit_session_section_requested.emit(parent_path, session, "terminal")
            )
            edit_menu.addAction(terminal)
            network = QAction("Network settings", self)
            network.triggered.connect(
                lambda: self.edit_session_section_requested.emit(parent_path, session, "network")
            )
            edit_menu.addAction(network)
            menu.addSeparator()
            rename = QAction("Rename…", self)
            rename.triggered.connect(lambda: self._prompt_rename_session(parent_path, session))
            menu.addAction(rename)
            dup = QAction("Duplicate", self)
            dup.triggered.connect(lambda: self._duplicate_session(parent_path, session))
            menu.addAction(dup)
            delete = QAction("Delete session...", self)
            delete.triggered.connect(lambda: self._delete_session(parent_path, session))
            menu.addAction(delete)
            if session.get("type") == "SSH":
                menu.addSeparator()
                forget = QAction("Forget saved password / passphrase", self)
                forget.triggered.connect(lambda: self.forget_credentials.emit(session))
                menu.addAction(forget)
                if session.get("mac"):
                    wol = QAction("Wake on LAN", self)
                    wol.setIcon(named_icon("power_settings_new.svg"))
                    wol.triggered.connect(lambda: self.wake_on_lan.emit(session))
                    menu.addAction(wol)
        elif item.data(0, self.FOLDER_ROLE):
            folder_path = list(item.data(0, self.PATH_ROLE) or [])
            new_sess = QAction("New session in this group…", self)
            new_sess.triggered.connect(lambda: self.new_session_requested.emit(folder_path))
            menu.addAction(new_sess)
            new_sub = QAction("New sub-group…", self)
            new_sub.triggered.connect(lambda: self._prompt_new_group(folder_path))
            menu.addAction(new_sub)
            menu.addSeparator()
            rename = QAction("Rename group…", self)
            rename.triggered.connect(lambda: self._prompt_rename_folder(folder_path))
            menu.addAction(rename)
            dup = QAction("Duplicate group", self)
            dup.triggered.connect(lambda: self._duplicate_folder(folder_path))
            menu.addAction(dup)
            collapse_all = QAction("Collapse all folders", self)
            collapse_all.triggered.connect(self.collapse_all_folders)
            menu.addAction(collapse_all)
            delete = QAction("Delete group...", self)
            delete.triggered.connect(lambda: self._delete_folder(folder_path))
            menu.addAction(delete)
        else:
            return

        menu.exec(self.tree.mapToGlobal(pos))

    def collapse_all_folders(self) -> None:
        self.tree.collapseAll()

    # ----- group / session mutation helpers -----

    def _prompt_new_group(self, parent_path):
        name, ok = QInputDialog.getText(self, "New group", "Group name:")
        if not ok:
            return
        name = name.strip()
        if not name:
            return
        try:
            added = self.session_manager.add_subgroup(parent_path, name)
        except ValueError as e:
            QMessageBox.information(self, "Can't add sub-group", str(e))
            return
        if added is None:
            QMessageBox.warning(self, "Couldn't add group", "Parent group not found.")
            return
        self.refresh_sessions()

    def _prompt_rename_folder(self, folder_path):
        if not folder_path:
            return
        current = folder_path[-1]
        new, ok = QInputDialog.getText(self, "Rename group", "Group name:", text=current)
        if not ok:
            return
        new = new.strip()
        if not new or new == current:
            return
        try:
            ok2 = self.session_manager.rename_folder(folder_path, new)
        except ValueError as e:
            QMessageBox.warning(self, "Can't rename", str(e))
            return
        if ok2:
            self.refresh_sessions()

    def _duplicate_folder(self, folder_path):
        if not folder_path:
            return
        try:
            new_name = self.session_manager.duplicate_folder(folder_path)
        except ValueError as e:
            QMessageBox.warning(self, "Can't duplicate", str(e))
            return
        if new_name:
            self.refresh_sessions()

    def _prompt_rename_session(self, parent_path, session):
        current = session.get("name", "")
        new, ok = QInputDialog.getText(self, "Rename session", "Session name:", text=current)
        if not ok:
            return
        new = new.strip()
        if not new or new == current:
            return
        try:
            ok2 = self.session_manager.rename_session(parent_path, session, new)
        except ValueError as e:
            QMessageBox.warning(self, "Can't rename", str(e))
            return
        if ok2:
            self.refresh_sessions()

    def _duplicate_session(self, parent_path, session):
        new = self.session_manager.duplicate_session(parent_path, session)
        if new:
            self.refresh_sessions()

    def _delete_folder(self, folder_path):
        if not folder_path:
            return
        name = folder_path[-1]
        reply = QMessageBox.question(
            self,
            "Delete group",
            f"Delete group '{name}' and everything inside it?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.session_manager.delete_folder(folder_path):
            self.refresh_sessions()
        else:
            QMessageBox.warning(self, "Can't delete group", "Group not found.")

    def _delete_session(self, parent_path, session):
        name = session.get("name", "session")
        reply = QMessageBox.question(
            self,
            "Delete session",
            f"Delete session '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.session_manager.delete_session(parent_path, session):
            self.refresh_sessions()
        else:
            QMessageBox.warning(self, "Can't delete session", "Session not found.")

    def _toggle_favorite(self, item):
        session = self._session_for_item(item)
        if not session:
            return
        new_state = not bool(session.get("favorite"))
        session["favorite"] = new_state
        # No visible star anymore; the favorite flag still drives the sort
        # order in _populate_tree, so refresh to bring the change into view.
        self.favorite_toggled.emit(session, new_state)
        self.refresh_sessions()

    def on_macro_click(self, item, column):
        self.macro_triggered.emit(item.text(0))

from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QInputDialog, QLineEdit, QMenu, QMessageBox, QPushButton,
    QSizePolicy, QSplitter, QTabWidget, QToolButton, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QAction

from core.icons import folder_icon, named_icon, session_icon


class _SessionRef:
    def __init__(self, session: dict):
        self.session = session


def _session_tooltip(session: dict) -> str:
    """Human-readable session details for hover. Falls back to just the name
    when the session dict is sparse (Local sessions, etc.)."""
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
    return "<br>".join(lines) if lines else name
from widgets.local_servers import LocalServersManager
from widgets.sftp_browser import SftpBrowser
from widgets.ssh_browser import SshBrowser
from widgets.snippet_manager import SnippetWidget
from widgets.docker_dashboard import DockerDashboard

class Sidebar(QWidget):
    tool_triggered = pyqtSignal(str)
    session_activated = pyqtSignal(dict)       # full session dict
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
        self.setMinimumWidth(140)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Compact stylesheet: trims default Qt padding on the west tab strip
        # and lets application themes provide the actual colors.
        self.setStyleSheet(
            """
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                padding: 6px 4px;
                min-width: 26px;
                min-height: 26px;
            }
            QTreeWidget::item { padding: 0px; height: 18px; }
            """
        )

        # Vertical splitter so the user sees Sessions/etc. AND the SFTP browser
        # at the same time (MobaXterm-style). SFTP is a sibling of the tab
        # widget, not one of its tabs.
        self.content_splitter = QSplitter(Qt.Orientation.Vertical)
        self.content_splitter.setChildrenCollapsible(True)
        self.content_splitter.setHandleWidth(3)
        self.content_splitter.setMinimumWidth(130)
        self.content_splitter.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.main_layout.addWidget(self.content_splitter)

        # Tab Widget (top half). Icon-only west strip — the labels were eating
        # ~80 px of horizontal space; tooltips replace the text.
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.tabs.setIconSize(QSize(18, 18))
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.tabs.setMinimumWidth(130)
        self.tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.content_splitter.addWidget(self.tabs)

        # 1. Sessions Tab
        self.session_widget = QWidget()
        self.session_widget.setMinimumWidth(0)
        self.session_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.session_layout = QVBoxLayout(self.session_widget)
        self.session_layout.setContentsMargins(2, 2, 2, 2)
        self.session_layout.setSpacing(2)
        self.session_filter = QLineEdit()
        self.session_filter.setPlaceholderText("Search sessions...")
        self.session_filter.textChanged.connect(self._filter_sessions)
        self.session_layout.addWidget(self.session_filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setIconSize(QSize(14, 14))
        # Make horizontal-scroll-on-overflow the behavior when the user
        # squeezes the sidebar — the connection name doesn't get cut off
        # silently. Hover tooltips also carry the full session details.
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.header().setStretchLastSection(True)
        self.tree.header().setMinimumSectionSize(80)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.tree.itemDoubleClicked.connect(self.on_session_click)
        self.tree.itemExpanded.connect(self._on_item_expanded)
        self.tree.itemCollapsed.connect(self._on_item_collapsed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._show_tree_context_menu)
        self.session_layout.addWidget(self.tree)

        btn_row = QHBoxLayout()
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.setSpacing(2)
        self.add_btn = QPushButton(named_icon("add.svg"), "")
        self.add_btn.setToolTip("New session")
        self.export_btn = QPushButton(named_icon("upload.svg"), "")
        self.export_btn.setToolTip("Export sessions to file")
        self.import_btn = QPushButton(named_icon("download.svg"), "")
        self.import_btn.setToolTip("Import sessions from file")
        for b in [self.add_btn, self.export_btn, self.import_btn]:
            b.setProperty("compact", True)
            b.setIconSize(QSize(16, 16))
            b.setFixedSize(QSize(28, 24))  # square-ish icon buttons
            btn_row.addWidget(b)
        btn_row.addStretch()  # left-align the three icons
        self.session_layout.addLayout(btn_row)

        self.tabs.addTab(self.session_widget, named_icon("list_alt.svg"), "")
        self.tabs.setTabToolTip(0, "Sessions")

        # 2. SSH Browser Tab
        self.ssh_browser = SshBrowser()
        self.tabs.addTab(self.ssh_browser, named_icon("dns.svg"), "")
        self.tabs.setTabToolTip(1, "Active SSH sessions")

        # 3. Servers Tab
        self.servers_widget = LocalServersManager()
        self.tabs.addTab(self.servers_widget, named_icon("hub.svg"), "")
        self.tabs.setTabToolTip(2, "Local servers")

        # 4. Tools Tab
        self.tools_widget = QWidget()
        self.tools_widget.setMinimumWidth(0)
        self.tools_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.tools_layout = QVBoxLayout(self.tools_widget)
        self.tools_layout.setContentsMargins(2, 2, 2, 2)
        self.tools_layout.setSpacing(2)
        tools = ["Network Scanner", "Port Scanner", "SSH Key Gen", "IP Calculator"]
        for tool in tools:
            btn = QPushButton(tool)
            btn.setProperty("compact", True)
            btn.setStyleSheet("text-align: left;")  # additive to the compact rule
            btn.clicked.connect(lambda checked, t=tool: self.tool_triggered.emit(t))
            self.tools_layout.addWidget(btn)
        self.tools_layout.addStretch()
        self.tabs.addTab(self.tools_widget, named_icon("build.svg"), "")
        self.tabs.setTabToolTip(3, "Tools")

        # 5. Macros Tab
        self.macro_widget = QWidget()
        self.macro_widget.setMinimumWidth(0)
        self.macro_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.macro_layout = QVBoxLayout(self.macro_widget)
        self.macro_layout.setContentsMargins(2, 2, 2, 2)
        self.macro_layout.setSpacing(2)
        self.macro_tree = QTreeWidget()
        self.macro_tree.setHeaderHidden(True)
        self.macro_tree.itemDoubleClicked.connect(self.on_macro_click)
        self.macro_layout.addWidget(self.macro_tree)

        self.record_btn = QPushButton("Record Macro")
        self.record_btn.setProperty("compact", True)
        self.macro_layout.addWidget(self.record_btn)
        self.tabs.addTab(self.macro_widget, named_icon("code.svg"), "")
        self.tabs.setTabToolTip(4, "Macros")

        # 6. Snippets Tab
        self.snippet_widget = SnippetWidget(self.snippet_manager)
        self.snippet_widget.snippet_triggered.connect(self.snippet_triggered.emit)
        self.tabs.addTab(self.snippet_widget, named_icon("list_alt.svg"), "")
        self.tabs.setTabToolTip(5, "Command Snippets")

        # 7. Docker Tab
        self.docker_widget = DockerDashboard()
        self.docker_widget.container_shell_requested.connect(self.container_shell_requested.emit)
        self.tabs.addTab(self.docker_widget, named_icon("desktop_windows.svg"), "")
        self.tabs.setTabToolTip(6, "Docker Containers")

        # SFTP browser — sibling of the tab widget, persistent.
        self.sftp_widget = SftpBrowser()
        self.content_splitter.addWidget(self.sftp_widget)
        # Sensible default split: ~60% tabs, ~40% SFTP. Start with the SFTP
        # pane collapsed when nothing is attached so it doesn't take screen
        # real estate until an SSH session needs it.
        self.content_splitter.setSizes([600, 0])
        self.content_splitter.setStretchFactor(0, 1)
        self.content_splitter.setStretchFactor(1, 1)

        # Collapse rail — narrow strip on the right edge of the sidebar.
        self.collapse_btn = QToolButton()
        self.collapse_btn.setText("‹")
        self.collapse_btn.setCheckable(True)
        self.collapse_btn.setFixedWidth(10)
        self.collapse_btn.setStyleSheet("border: none; font-size: 10px;")
        self.collapse_btn.clicked.connect(self.toggle_collapse)
        self.main_layout.addWidget(self.collapse_btn)

        self.refresh_sessions()
        self.refresh_macros()

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

    SESSION_ROLE = Qt.ItemDataRole.UserRole
    FOLDER_ROLE = Qt.ItemDataRole.UserRole + 1
    # Folder items carry the path *to* themselves; session items carry the
    # path of their containing folder. Both as a list[str] from root.
    PATH_ROLE = Qt.ItemDataRole.UserRole + 2

    def _session_for_item(self, item):
        ref = item.data(0, self.SESSION_ROLE) if item is not None else None
        if isinstance(ref, _SessionRef):
            return ref.session
        return ref if isinstance(ref, dict) else None

    def refresh_sessions(self):
        self.tree.clear()
        self._populate_tree(self.session_manager.sessions, self.tree, [])
        self._filter_sessions(self.session_filter.text())

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
            # Favorites still float to the top of each folder even though the
            # star column is gone — that's the main payoff of the favorite flag.
            for s in sorted(
                data,
                key=lambda x: (not x.get("favorite"), x.get("name", "").lower()),
            ):
                item = QTreeWidgetItem(parent, [s.get("name", "<unnamed>")])
                item.setIcon(0, session_icon(s))
                item.setData(0, self.SESSION_ROLE, _SessionRef(s))
                item.setData(0, self.PATH_ROLE, list(path))
                # Tooltip carries the full session identity so a narrow sidebar
                # never hides what you're about to connect to.
                item.setToolTip(0, _session_tooltip(s))

    def _filter_sessions(self, text: str) -> None:
        needle = (text or "").strip().lower()

        def apply(item) -> bool:
            self_match = needle in item.text(0).lower() or not needle
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
            self.session_activated.emit(session)

    def _on_item_expanded(self, item):
        if item.data(0, self.FOLDER_ROLE):
            item.setIcon(0, folder_icon(is_open=True))

    def _on_item_collapsed(self, item):
        if item.data(0, self.FOLDER_ROLE):
            item.setIcon(0, folder_icon(is_open=False))

    def _show_tree_context_menu(self, pos):
        item = self.tree.itemAt(pos)
        menu = QMenu(self)
        session = self._session_for_item(item)

        if item is None:
            act_group = QAction("New top-level group…", self)
            act_group.triggered.connect(lambda: self._prompt_new_group([]))
            menu.addAction(act_group)
        elif session:
            parent_path = list(item.data(0, self.PATH_ROLE) or [])
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
            delete = QAction("Delete group...", self)
            delete.triggered.connect(lambda: self._delete_folder(folder_path))
            menu.addAction(delete)
        else:
            return

        menu.exec(self.tree.mapToGlobal(pos))

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

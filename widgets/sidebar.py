from PyQt6.QtCore import QSize, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QMenu, QPushButton, QSplitter, QTabWidget,
    QToolButton, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)
from PyQt6.QtGui import QAction

from core.icons import folder_icon, named_icon, session_icon


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
from widgets.credential_manager import CredentialManager
from widgets.local_servers import LocalServersManager
from widgets.sftp_browser import SftpBrowser
from widgets.ssh_browser import SshBrowser

class Sidebar(QWidget):
    tool_triggered = pyqtSignal(str)
    session_activated = pyqtSignal(dict)       # full session dict
    favorite_toggled = pyqtSignal(dict, bool)  # session, new state
    forget_credentials = pyqtSignal(dict)      # forget saved password / passphrase
    wake_on_lan = pyqtSignal(dict)             # send a WoL magic packet for this session
    macro_triggered = pyqtSignal(str)
    collapse_requested = pyqtSignal(bool)
    
    def __init__(self, session_manager, macro_engine):
        super().__init__()
        self.session_manager = session_manager
        self.macro_engine = macro_engine
        self.is_collapsed = False

        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # Compact stylesheet: trims default Qt padding on the west tab strip
        # and the small action buttons that live below trees.
        self.setStyleSheet(
            """
            QTabWidget::pane { border: none; }
            QTabBar::tab {
                background: #3c3f41;
                color: #cccccc;
                padding: 6px 4px;
                min-width: 26px;
                min-height: 26px;
            }
            QTabBar::tab:selected { background: #2b2b2b; }
            QTabBar::tab:hover    { background: #4b4b4b; }
            QPushButton[compact="true"] {
                background-color: #3c3f41;
                color: #cccccc;
                border: 1px solid #555;
                padding: 3px 6px;
                font-size: 10px;
            }
            QPushButton[compact="true"]:hover { background-color: #4b4b4b; }
            QTreeWidget {
                background-color: #2b2b2b;
                color: #ccc;
                border: none;
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
        self.main_layout.addWidget(self.content_splitter)

        # Tab Widget (top half). Icon-only west strip — the labels were eating
        # ~80 px of horizontal space; tooltips replace the text.
        self.tabs = QTabWidget()
        self.tabs.setTabPosition(QTabWidget.TabPosition.West)
        self.tabs.setIconSize(QSize(18, 18))
        self.tabs.tabBar().setExpanding(False)
        self.tabs.tabBar().setUsesScrollButtons(False)
        self.content_splitter.addWidget(self.tabs)

        # 1. Sessions Tab
        self.session_widget = QWidget()
        self.session_layout = QVBoxLayout(self.session_widget)
        self.session_layout.setContentsMargins(2, 2, 2, 2)
        self.session_layout.setSpacing(2)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(1)
        self.tree.setIconSize(QSize(14, 14))
        # Make horizontal-scroll-on-overflow the behavior when the user
        # squeezes the sidebar — the connection name doesn't get cut off
        # silently. Hover tooltips also carry the full session details.
        self.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
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

        # 2. Credentials Tab
        self.cred_widget = CredentialManager()
        self.tabs.addTab(self.cred_widget, named_icon("key.svg"), "")
        self.tabs.setTabToolTip(1, "Saved passwords / passphrases")

        # 3. SSH Browser Tab
        self.ssh_browser = SshBrowser()
        self.tabs.addTab(self.ssh_browser, named_icon("dns.svg"), "")
        self.tabs.setTabToolTip(2, "Active SSH sessions")

        # 4. Servers Tab
        self.servers_widget = LocalServersManager()
        self.tabs.addTab(self.servers_widget, named_icon("hub.svg"), "")
        self.tabs.setTabToolTip(3, "Local servers")

        # 5. Tools Tab
        self.tools_widget = QWidget()
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
        self.tabs.setTabToolTip(4, "Tools")

        # 6. Macros Tab
        self.macro_widget = QWidget()
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
        self.tabs.setTabToolTip(5, "Macros")

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
        self.collapse_btn.setStyleSheet(
            "background: #3c3f41; color: #888; border: none; font-size: 10px;"
        )
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

    def refresh_sessions(self):
        self.tree.clear()
        self._populate_tree(self.session_manager.sessions, self.tree)
        self.tree.expandAll()

    def _populate_tree(self, data, parent):
        if isinstance(data, dict):
            for key, value in data.items():
                item = QTreeWidgetItem(parent, [key])
                item.setIcon(0, folder_icon(is_open=True))
                item.setData(0, self.FOLDER_ROLE, True)
                self._populate_tree(value, item)
        elif isinstance(data, list):
            # Favorites still float to the top of each folder even though the
            # star column is gone — that's the main payoff of the favorite flag.
            for s in sorted(
                data,
                key=lambda x: (not x.get("favorite"), x.get("name", "").lower()),
            ):
                item = QTreeWidgetItem(parent, [s.get("name", "<unnamed>")])
                item.setIcon(0, session_icon(s))
                item.setData(0, self.SESSION_ROLE, s)
                # Tooltip carries the full session identity so a narrow sidebar
                # never hides what you're about to connect to.
                item.setToolTip(0, _session_tooltip(s))

    def refresh_macros(self):
        self.macro_tree.clear()
        for name in self.macro_engine.macros.keys():
            QTreeWidgetItem(self.macro_tree, [name])

    def on_session_click(self, item, column):
        session = item.data(0, self.SESSION_ROLE)
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
        if item is None:
            return
        session = item.data(0, self.SESSION_ROLE)
        if not session:
            return
        menu = QMenu(self)
        is_fav = bool(session.get("favorite"))
        toggle = QAction("Remove favorite" if is_fav else "Mark as favorite", self)
        toggle.triggered.connect(lambda: self._toggle_favorite(item))
        menu.addAction(toggle)
        connect = QAction("Connect", self)
        connect.triggered.connect(lambda: self.session_activated.emit(session))
        menu.addAction(connect)
        if session.get("type") == "SSH":
            menu.addSeparator()
            forget = QAction("Forget saved password / passphrase", self)
            forget.triggered.connect(lambda: self.forget_credentials.emit(session))
            menu.addAction(forget)
            if session.get("mac"):
                wol = QAction("Wake on LAN", self)
                wol.setIcon(named_icon("asbru-wol.svg"))
                wol.triggered.connect(lambda: self.wake_on_lan.emit(session))
                menu.addAction(wol)
        menu.exec(self.tree.mapToGlobal(pos))

    def _toggle_favorite(self, item):
        session = item.data(0, self.SESSION_ROLE)
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

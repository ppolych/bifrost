from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLineEdit, QPushButton, QSizePolicy, QSplitter,
    QTabWidget, QToolButton, QTreeWidget, QVBoxLayout, QWidget,
)

from core.icons import named_icon
from widgets.local_servers import LocalServersManager
from widgets.sftp_browser import SftpBrowser
from widgets.snippet_manager import SnippetWidget
from widgets.ssh_browser import SshBrowser
from widgets.remote_ops import RemoteOpsWidget


def build_sidebar_ui(sidebar) -> None:
    sidebar.setMinimumWidth(140)
    sidebar.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)

    sidebar.main_layout = QHBoxLayout(sidebar)
    sidebar.main_layout.setContentsMargins(0, 0, 0, 0)
    sidebar.main_layout.setSpacing(0)
    sidebar.setStyleSheet(
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

    sidebar.content_splitter = QSplitter(Qt.Orientation.Vertical)
    sidebar.content_splitter.setChildrenCollapsible(True)
    sidebar.content_splitter.setHandleWidth(3)
    sidebar.content_splitter.setMinimumWidth(130)
    sidebar.content_splitter.setSizePolicy(
        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
    )
    sidebar.main_layout.addWidget(sidebar.content_splitter)

    sidebar.tabs = QTabWidget()
    sidebar.tabs.setTabPosition(QTabWidget.TabPosition.West)
    sidebar.tabs.setIconSize(QSize(18, 18))
    sidebar.tabs.tabBar().setExpanding(False)
    sidebar.tabs.tabBar().setUsesScrollButtons(False)
    sidebar.tabs.setMinimumWidth(130)
    sidebar.tabs.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    sidebar.content_splitter.addWidget(sidebar.tabs)

    build_sessions_tab(sidebar)
    build_builtin_tabs(sidebar)
    build_sftp_pane(sidebar)
    build_collapse_button(sidebar)


def build_sessions_tab(sidebar) -> None:
    sidebar.session_widget = QWidget()
    sidebar.session_widget.setMinimumWidth(0)
    sidebar.session_widget.setSizePolicy(
        QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
    )
    sidebar.session_layout = QVBoxLayout(sidebar.session_widget)
    sidebar.session_layout.setContentsMargins(2, 2, 2, 2)
    sidebar.session_layout.setSpacing(2)
    sidebar.session_filter = QLineEdit()
    sidebar.session_filter.setPlaceholderText("Search sessions...")
    sidebar.session_filter.textChanged.connect(sidebar._filter_sessions)
    sidebar.session_layout.addWidget(sidebar.session_filter)

    sidebar.tree = QTreeWidget()
    sidebar.tree.setHeaderHidden(True)
    sidebar.tree.setColumnCount(1)
    sidebar.tree.setIconSize(QSize(14, 14))
    sidebar.tree.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    sidebar.tree.header().setStretchLastSection(True)
    sidebar.tree.header().setMinimumSectionSize(80)
    sidebar.tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    sidebar.tree.itemDoubleClicked.connect(sidebar.on_session_click)
    sidebar.tree.itemExpanded.connect(sidebar._on_item_expanded)
    sidebar.tree.itemCollapsed.connect(sidebar._on_item_collapsed)
    sidebar.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
    sidebar.tree.customContextMenuRequested.connect(sidebar._show_tree_context_menu)
    sidebar.session_layout.addWidget(sidebar.tree)

    btn_row = QHBoxLayout()
    btn_row.setContentsMargins(0, 0, 0, 0)
    btn_row.setSpacing(2)
    sidebar.add_btn = QPushButton(named_icon("add.svg"), "")
    sidebar.add_btn.setToolTip("New session")
    sidebar.export_btn = QPushButton(named_icon("upload.svg"), "")
    sidebar.export_btn.setToolTip("Export sessions to file")
    sidebar.import_btn = QPushButton(named_icon("download.svg"), "")
    sidebar.import_btn.setToolTip("Import sessions from file")
    for button in [sidebar.add_btn, sidebar.export_btn, sidebar.import_btn]:
        button.setProperty("compact", True)
        button.setIconSize(QSize(16, 16))
        button.setFixedSize(QSize(28, 24))
        btn_row.addWidget(button)
    btn_row.addStretch()
    sidebar.session_layout.addLayout(btn_row)

    sidebar.tabs.addTab(sidebar.session_widget, named_icon("list_alt.svg"), "")
    sidebar.tabs.setTabToolTip(0, "Sessions")


def build_builtin_tabs(sidebar) -> None:
    sidebar.ssh_browser = SshBrowser()
    sidebar.tabs.addTab(sidebar.ssh_browser, named_icon("dns.svg"), "")
    sidebar.tabs.setTabToolTip(1, "Active SSH sessions")

    sidebar.servers_widget = LocalServersManager()
    sidebar.tabs.addTab(sidebar.servers_widget, named_icon("hub.svg"), "")
    sidebar.tabs.setTabToolTip(2, "Local servers")

    sidebar.tools_widget = QWidget()
    sidebar.tools_widget.setMinimumWidth(0)
    sidebar.tools_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    sidebar.tools_layout = QVBoxLayout(sidebar.tools_widget)
    sidebar.tools_layout.setContentsMargins(2, 2, 2, 2)
    sidebar.tools_layout.setSpacing(2)
    for tool in ["Network Scanner", "Port Scanner", "SSH Key Gen", "IP Calculator"]:
        btn = QPushButton(tool)
        btn.setProperty("compact", True)
        btn.setStyleSheet("text-align: left;")
        btn.clicked.connect(lambda checked, t=tool: sidebar.tool_triggered.emit(t))
        sidebar.tools_layout.addWidget(btn)
    sidebar.tools_layout.addStretch()
    sidebar.tabs.addTab(sidebar.tools_widget, named_icon("build.svg"), "")
    sidebar.tabs.setTabToolTip(3, "Tools")

    sidebar.macro_widget = QWidget()
    sidebar.macro_widget.setMinimumWidth(0)
    sidebar.macro_widget.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
    sidebar.macro_layout = QVBoxLayout(sidebar.macro_widget)
    sidebar.macro_layout.setContentsMargins(2, 2, 2, 2)
    sidebar.macro_layout.setSpacing(2)
    sidebar.macro_tree = QTreeWidget()
    sidebar.macro_tree.setHeaderHidden(True)
    sidebar.macro_tree.itemDoubleClicked.connect(sidebar.on_macro_click)
    sidebar.macro_layout.addWidget(sidebar.macro_tree)

    sidebar.record_btn = QPushButton("Record Macro")
    sidebar.record_btn.setProperty("compact", True)
    sidebar.macro_layout.addWidget(sidebar.record_btn)
    sidebar.tabs.addTab(sidebar.macro_widget, named_icon("code.svg"), "")
    sidebar.tabs.setTabToolTip(4, "Macros")

    sidebar.snippet_widget = SnippetWidget(sidebar.snippet_manager)
    sidebar.snippet_widget.snippet_triggered.connect(sidebar.snippet_triggered.emit)
    sidebar.tabs.addTab(sidebar.snippet_widget, named_icon("list_alt.svg"), "")
    sidebar.tabs.setTabToolTip(5, "Command Snippets")

    sidebar._add_lazy_tab(named_icon("desktop_windows.svg"), "Docker Containers", sidebar._build_docker_tab)
    sidebar.tabs.setTabToolTip(6, "Docker Containers")

    sidebar.remote_ops_widget = RemoteOpsWidget()
    sidebar.tabs.addTab(sidebar.remote_ops_widget, named_icon("terminal.svg"), "")
    sidebar.tabs.setTabToolTip(7, "Remote Ops")


def build_sftp_pane(sidebar) -> None:
    sidebar.sftp_widget = SftpBrowser()
    sidebar.content_splitter.addWidget(sidebar.sftp_widget)
    sidebar.content_splitter.setSizes([600, 0])
    sidebar.content_splitter.setStretchFactor(0, 1)
    sidebar.content_splitter.setStretchFactor(1, 1)


def build_collapse_button(sidebar) -> None:
    sidebar.collapse_btn = QToolButton()
    sidebar.collapse_btn.setText("‹")
    sidebar.collapse_btn.setCheckable(True)
    sidebar.collapse_btn.setFixedWidth(10)
    sidebar.collapse_btn.setStyleSheet("border: none; font-size: 10px;")
    sidebar.collapse_btn.clicked.connect(sidebar.toggle_collapse)
    sidebar.main_layout.addWidget(sidebar.collapse_btn)

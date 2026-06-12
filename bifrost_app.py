from bifrost_app_deps import *
from bifrost_app_persistence_tabs import BifrostPersistenceTabsMixin
from bifrost_app_remote_files import BifrostRemoteFilesMixin
from bifrost_app_sessions import BifrostSessionsMixin
from bifrost_app_settings_tools import BifrostSettingsToolsMixin
from bifrost_app_ssh_status import BifrostSshStatusMixin
from bifrost_app_tabs import BifrostTabsMixin
from bifrost_app_terminal_sessions import BifrostTerminalSessionsMixin
from bifrost_app_deps import (
    _font_from_override,
    _iter_sessions,
    _remote_display_name,
    _safe_temp_suffix,
    _split_user_command,
    _strip_outer_quotes,
)

class BifrostApp(
    BifrostTabsMixin,
    BifrostSettingsToolsMixin,
    BifrostRemoteFilesMixin,
    BifrostSessionsMixin,
    BifrostTerminalSessionsMixin,
    BifrostPersistenceTabsMixin,
    BifrostSshStatusMixin,
    QMainWindow,
):
    def __init__(self, is_detached=False, settings=None):
        super().__init__()
        self.setWindowTitle("Bifrost Connection Manager")
        self.setWindowIcon(app_icon())
        self.resize(1200, 900)
        
        self.settings = settings if settings is not None else load_settings()
        credentials.set_provider(self.settings.get("credential_provider", "system"))
        
        self.apply_global_visuals()
        self.session_manager = SessionManager()
        self.workspace_manager = WorkspaceManager()
        self.macro_engine = MacroEngine()
        self.snippet_manager = SnippetManager()
        self.host_key_prompter = HostKeyPrompter(self)
        self.detached_windows = []
        self.pinned_tabs = set()
        # Cluster = the subset of tabs MultiExec targets when scoped to
        # "Cluster only". Holds container objects (not indexes) so membership
        # survives tab reordering.
        self.cluster_tabs = set()
        self.multi_exec_enabled = False
        setup_app_menus(self)
        
        # Toolbar
        self.toolbar = MainToolBar(self)
        self.toolbar.multi_exec_toggled.connect(self.on_multi_exec_toggled)
        self.toolbar.session_act.triggered.connect(self.open_session_dialog)
        self.toolbar.servers_act.triggered.connect(
            lambda: self.sidebar.tabs.setCurrentIndex(2)  # Servers tab
        )
        self.toolbar.quick_connect_triggered.connect(self.on_quick_connect)
        self.toolbar.wol_act.triggered.connect(self.on_wol_dialog)
        self.toolbar.split_triggered.connect(self.on_split_requested)
        self.toolbar.diagnostics_requested.connect(self.show_diagnostics)
        self.toolbar.settings_act.triggered.connect(self.open_settings_dialog)
        self.addToolBar(self.toolbar)

        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_vbox = QVBoxLayout(self.central_widget)
        self.main_vbox.setContentsMargins(0, 0, 0, 0)
        self.main_vbox.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Sidebar
        self.sidebar = Sidebar(self.session_manager, self.macro_engine, self.snippet_manager)
        self.sidebar.session_activated.connect(self.on_session_activated)
        self.sidebar.favorite_toggled.connect(self.on_favorite_toggled)
        self.sidebar.forget_credentials.connect(self.on_forget_credentials)
        self.sidebar.wake_on_lan.connect(self.on_wake_on_lan)
        self.sidebar.new_session_requested.connect(self.open_session_dialog)
        self.sidebar.edit_session_requested.connect(self.edit_session)
        self.sidebar.edit_session_section_requested.connect(self.edit_session)
        self.sidebar.add_btn.clicked.connect(self.open_session_dialog)
        self.sidebar.export_btn.clicked.connect(self.export_sessions)
        self.sidebar.import_btn.clicked.connect(self.import_sessions)
        self.sidebar.ssh_browser.refresh_requested.connect(self._refresh_ssh_browser)
        # self.tabs is created later in __init__; defer the lookup with a lambda.
        self.sidebar.ssh_browser.focus_tab.connect(lambda i: self.tabs.setCurrentIndex(i))
        self.sidebar.ssh_browser.disconnect_tab.connect(self._disconnect_tab)
        self.sidebar.ssh_browser.reconnect_tab.connect(self._reconnect_tab)
        self.sidebar.ssh_browser.reconnect_all.connect(self._reconnect_all_disconnected)
        self.sidebar.ssh_browser.stop_tunnel.connect(self._stop_ssh_tunnel)
        self.sidebar.sftp_widget.file_double_clicked.connect(self.open_file_in_editor)
        self.sidebar.sftp_widget.file_text_editor_requested.connect(self.open_file_in_text_editor)
        self.sidebar.sftp_widget.file_open_with_requested.connect(self.open_file_with_command)
        self.sidebar.sftp_widget.file_system_open_requested.connect(self.open_file_with_system_default)
        self.sidebar.sftp_widget.path_to_terminal_requested.connect(self.send_remote_path_to_terminal)
        self.sidebar.sftp_widget.set_show_hidden(self.settings.get("sftp_show_hidden", False))
        self.sidebar.tool_triggered.connect(self.on_tool_triggered)
        self.sidebar.macro_triggered.connect(self.run_macro)
        self.sidebar.snippet_triggered.connect(self.run_snippet)
        self.sidebar.container_shell_requested.connect(self.open_container_terminal)
        self.sidebar.record_btn.clicked.connect(self.toggle_macro_recording)
        self.sidebar.collapse_requested.connect(self.on_sidebar_collapsed)
        
        if not is_detached:
            self.splitter.addWidget(self.sidebar)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)  # drag to reorder tabs
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.tabs.currentChanged.connect(self.on_tab_changed)
        self.tabs.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self.show_tab_context_menu)
        self.splitter.addWidget(self.tabs)

        self.splitter.setSizes([260, 940])
        self._restore_layout_state()
        self.splitter.splitterMoved.connect(lambda *_: self._remember_layout_state())
        self.sidebar.content_splitter.splitterMoved.connect(lambda *_: self._remember_layout_state())
        self.sidebar.tabs.currentChanged.connect(lambda *_: self._remember_layout_state())
        self.main_vbox.addWidget(self.splitter)

        # MultiExec Bar
        self.multi_exec_bar = QWidget()
        self.multi_exec_bar.setFixedHeight(35)
        self.multi_exec_layout = QHBoxLayout(self.multi_exec_bar)
        self.multi_exec_layout.setContentsMargins(10, 0, 10, 0)
        self.multi_exec_label = QLabel("ALL TERMINALS:")
        self.multi_exec_label.setStyleSheet("color: red; font-weight: bold; font-size: 10px;")
        self.multi_exec_layout.addWidget(self.multi_exec_label)
        self.multi_exec_scope = QComboBox()
        self.multi_exec_scope.addItem("All terminals", "all")
        self.multi_exec_scope.addItem("Cluster only", "cluster")
        self.multi_exec_scope.setToolTip(
            "Broadcast to every tab, or only to tabs added to the cluster\n"
            "(right-click a tab → Add to cluster)"
        )
        self.multi_exec_scope.currentIndexChanged.connect(lambda *_: self._refresh_multi_exec_ui())
        self.multi_exec_layout.addWidget(self.multi_exec_scope)
        self.multi_exec_input = QLineEdit()
        self.multi_exec_input.setPlaceholderText("Type command to send to ALL active terminals...")
        self.multi_exec_input.returnPressed.connect(self.broadcast_command)
        self.multi_exec_layout.addWidget(self.multi_exec_input)
        self.auto_cluster_cb = QCheckBox("Auto-add SSH tabs")
        self.auto_cluster_cb.setToolTip("New SSH tabs join the cluster automatically")
        self.multi_exec_layout.addWidget(self.auto_cluster_cb)
        self.multi_exec_bar.hide()
        self.main_vbox.addWidget(self.multi_exec_bar)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.remote_monitor = RemoteMonitorWidget(self)
        self.status_bar.addWidget(self.remote_monitor, 1)
        self.ip_label = QLabel(f"Local IP: {self.get_local_ip()}")
        self.status_bar.addPermanentWidget(self.ip_label)
        self.cpu_label = QLabel("CPU: 0%")
        self.mem_label = QLabel("MEM: 0%")
        self.status_bar.addPermanentWidget(self.cpu_label)
        self.status_bar.addPermanentWidget(self.mem_label)
        
        self.metrics_timer = QTimer(self)
        self.metrics_timer.timeout.connect(self.update_metrics)
        self.metrics_timer.start(2000)

        self.ssh_state_timer = QTimer(self)
        self.ssh_state_timer.timeout.connect(self._refresh_ssh_browser)
        self.ssh_state_timer.start(1000)
        
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.toggle_terminal_search)
        self.command_palette_shortcut = QShortcut(QKeySequence("Ctrl+Shift+P"), self)
        self.command_palette_shortcut.activated.connect(self.open_command_palette)
        
        # Re-apply visuals now that self.tabs exists so tab_position takes effect.
        self.apply_global_visuals()
        # Populate the credentials view + active-sessions browser once at startup.
        self._refresh_credentials_view()
        self._refresh_ssh_browser()
        # Restore window geometry if the setting is on and a saved blob exists.
        if not is_detached and self.settings.get("restore_window_geometry", True):
            blob_hex = self.settings.get("window_geometry") or ""
            if isinstance(blob_hex, str) and blob_hex:
                try:
                    self.restoreGeometry(bytes.fromhex(blob_hex))
                except ValueError:
                    log.debug("ignoring malformed window_geometry blob")
        if not is_detached:
            if self.settings["show_dashboard"]: self.show_dashboard()
            else: self.new_terminal_tab("Local Shell")


def main() -> int:
    QApplication.setApplicationName("bifrost")
    app = QApplication(sys.argv)
    # Run the legacy-config migration BEFORE configure_logging — once the log
    # handler opens bifrost.log the new config dir is no longer empty and the
    # migration would skip itself.
    migrated = migrate_legacy_config()
    log_path = configure_logging()
    log.info("bifrost-cm starting, log file: %s", log_path)
    if migrated:
        count, source = migrated
        log.info("Migrated %d item(s) from %s to the new bifrost config dir.", count, source)
    window = BifrostApp()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())

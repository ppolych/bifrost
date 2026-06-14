"""Menu-bar construction for BifrostApp.

Moved out of bifrost_app.py verbatim: `setup_app_menus(window)` builds the
Session / Connections / View / Tools / Workspaces / Help menus and wires
every action to methods on the passed BifrostApp instance.
"""

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QKeySequence

from core.platform_utils import config_dir


def setup_app_menus(window) -> None:
    menubar = window.menuBar()

    session_menu = menubar.addMenu("Session")
    new_session = QAction("New session...", window)
    new_session.triggered.connect(window.open_session_dialog)
    session_menu.addAction(new_session)
    local_terminal = QAction("Start local terminal", window)
    local_terminal.triggered.connect(lambda: window.new_terminal_tab("Local Shell"))
    session_menu.addAction(local_terminal)
    session_menu.addSeparator()
    import_act = QAction("Import sessions...", window)
    import_act.triggered.connect(window.import_sessions)
    session_menu.addAction(import_act)
    import_ssh_config = QAction("Import OpenSSH config...", window)
    import_ssh_config.triggered.connect(window.import_ssh_config_sessions)
    session_menu.addAction(import_ssh_config)
    export_act = QAction("Export sessions...", window)
    export_act.triggered.connect(window.export_sessions)
    session_menu.addAction(export_act)
    session_menu.addSeparator()
    close_tab = QAction("Close current tab", window)
    close_tab.triggered.connect(window.close_current_tab)
    session_menu.addAction(close_tab)

    connections_menu = menubar.addMenu("Connections")
    reconnect_tab = QAction("Reconnect current tab", window)
    reconnect_tab.triggered.connect(window.reconnect_current_tab)
    connections_menu.addAction(reconnect_tab)
    reconnect_all = QAction("Reconnect all disconnected", window)
    reconnect_all.triggered.connect(window._reconnect_all_disconnected)
    connections_menu.addAction(reconnect_all)
    disconnect_tab = QAction("Disconnect current tab", window)
    disconnect_tab.triggered.connect(window.disconnect_current_tab)
    connections_menu.addAction(disconnect_tab)
    connections_menu.addSeparator()
    sftp_act = QAction("Open SFTP here", window)
    sftp_act.triggered.connect(window.attach_sftp_for_current_tab)
    connections_menu.addAction(sftp_act)
    wol_act = QAction("Wake on LAN...", window)
    wol_act.triggered.connect(window.on_wol_dialog)
    connections_menu.addAction(wol_act)
    saved_credentials = QAction("Saved credentials...", window)
    saved_credentials.triggered.connect(window.open_saved_credentials_dialog)
    connections_menu.addAction(saved_credentials)
    forget_act = QAction("Forget credentials for current session", window)
    forget_act.triggered.connect(window.forget_current_session_credentials)
    connections_menu.addAction(forget_act)

    view_menu = menubar.addMenu("View")
    sidebar_act = QAction("Toggle sidebar", window)
    sidebar_act.triggered.connect(lambda: window.sidebar.toggle_collapse())
    view_menu.addAction(sidebar_act)
    for label, index in (
        ("Sessions", 0),
        ("Active SSH", 1),
        ("Local servers", 2),
        ("Tools", 3),
        ("Macros", 4),
        ("Snippets", 5),
        ("Docker", 6),
    ):
        act = QAction(label, window)
        act.triggered.connect(lambda _checked=False, i=index: window.sidebar.tabs.setCurrentIndex(i))
        view_menu.addAction(act)
    view_menu.addSeparator()
    sftp_pane = QAction("Toggle SFTP pane", window)
    sftp_pane.triggered.connect(window.toggle_sftp_pane)
    view_menu.addAction(sftp_pane)
    view_menu.addSeparator()
    for label, key in (("Split vertical", "vert"), ("Split horizontal", "horiz"), ("Split quad", "quad")):
        act = QAction(label, window)
        act.triggered.connect(lambda _checked=False, k=key: window.on_split_requested(k))
        view_menu.addAction(act)
    multi = QAction("Toggle MultiExec", window)
    multi.triggered.connect(lambda: window.toolbar.multi_act.toggle())
    view_menu.addAction(multi)
    fullscreen = QAction("Toggle full screen", window)
    fullscreen.setShortcut(QKeySequence("F11"))
    fullscreen.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
    fullscreen.triggered.connect(window.toggle_full_screen)
    view_menu.addAction(fullscreen)

    tools_menu = menubar.addMenu("Tools")
    for tool_name in ("Port Scanner", "Network Scanner", "IP Calculator", "SSH Key Gen"):
        act = QAction(tool_name, window)
        act.triggered.connect(lambda _checked=False, t=tool_name: window.on_tool_triggered(t))
        tools_menu.addAction(act)
    tools_menu.addSeparator()
    diagnostics = QAction("Diagnostics...", window)
    diagnostics.triggered.connect(window.show_diagnostics)
    tools_menu.addAction(diagnostics)
    settings = QAction("Settings...", window)
    settings.triggered.connect(window.open_settings_dialog)
    tools_menu.addAction(settings)

    workspace_menu = menubar.addMenu("Workspaces")
    save_act = QAction("Save current SSH tabs...", window)
    save_act.triggered.connect(window.save_current_workspace)
    workspace_menu.addAction(save_act)

    open_act = QAction("Open workspace...", window)
    open_act.triggered.connect(window.open_workspace_profile)
    workspace_menu.addAction(open_act)

    delete_act = QAction("Delete workspace...", window)
    delete_act.triggered.connect(window.delete_workspace_profile)
    workspace_menu.addAction(delete_act)

    help_menu = menubar.addMenu("Help")
    copy_diag = QAction("Copy diagnostics", window)
    copy_diag.triggered.connect(window.copy_diagnostics)
    help_menu.addAction(copy_diag)
    open_logs = QAction("Open logs folder", window)
    open_logs.triggered.connect(window.open_logs_folder)
    help_menu.addAction(open_logs)
    open_config = QAction("Open config folder", window)
    open_config.triggered.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(config_dir())))
    help_menu.addAction(open_config)
    help_menu.addSeparator()
    about = QAction("About Bifrost", window)
    about.triggered.connect(window.show_about_dialog)
    help_menu.addAction(about)

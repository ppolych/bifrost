import configparser
import importlib.metadata
import json
import logging
import os
import platform
import shutil
import socket
import subprocess
import sys

import psutil
import paramiko
import pyte
from PyQt6.QtCore import QT_VERSION_STR, Qt, QTimer, QUrl
from PyQt6.QtGui import QAction, QDesktopServices, QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication, QColorDialog, QFileDialog, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
    QMainWindow, QMenu, QMessageBox, QSplitter, QStatusBar, QTabBar, QTabWidget,
    QVBoxLayout, QWidget,
)

log = logging.getLogger(__name__)
from widgets.sidebar import Sidebar
from widgets.terminal import TerminalWidget
from widgets.terminal_container import TerminalContainer
from widgets.toolbar import MainToolBar
from widgets.session_dialog import SessionDialog
from widgets.settings_dialog import SettingsDialog
from widgets.editor import MobaEditor
from widgets.dashboard import Dashboard
from widgets.remote_monitor import RemoteMonitorWidget
from core.styles import get_dark_theme
from core import credentials, ip_tools, keygen, session_crypto, wake_on_lan, wsl
from core.host_key_prompt import HostKeyPrompter, QtHostKeyPolicy
from core.icons import app_icon
from core.logging_setup import _log_path, configure_logging
from core.mobaxterm_import import parse_mobaxterm_file
from core.persistence import SessionManager
from core.macro_engine import MacroEngine
from core.network_tools import scan_ports, scan_ip_range
from core.platform_utils import config_dir, default_monospace_font, migrate_legacy_config
from core.settings_store import load_settings, save_settings
from core.ssh_backend import ParamikoBackend, SshCredentials
from core.workspaces import WorkspaceManager
from widgets.credential_prompt import CredentialPrompt

class BifrostApp(QMainWindow):
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
        self.host_key_prompter = HostKeyPrompter(self)
        self.setStyleSheet(get_dark_theme())
        self.detached_windows = []
        self.pinned_tabs = set()
        self._setup_workspace_menu()
        
        # Toolbar
        self.toolbar = MainToolBar(self)
        self.toolbar.multi_exec_toggled.connect(self.on_multi_exec_toggled)
        self.toolbar.session_act.triggered.connect(self.open_session_dialog)
        self.toolbar.servers_act.triggered.connect(
            lambda: self.sidebar.tabs.setCurrentIndex(3)  # Servers tab
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
        self.sidebar = Sidebar(self.session_manager, self.macro_engine)
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
        self.sidebar.cred_widget.refresh_requested.connect(self._refresh_credentials_view)
        self.sidebar.cred_widget.forget_requested.connect(self.on_forget_credentials)
        self.sidebar.sftp_widget.file_double_clicked.connect(self.open_file_in_editor)
        self.sidebar.sftp_widget.file_text_editor_requested.connect(self.open_file_in_text_editor)
        self.sidebar.sftp_widget.file_open_with_requested.connect(self.open_file_with_command)
        self.sidebar.sftp_widget.file_system_open_requested.connect(self.open_file_with_system_default)
        self.sidebar.sftp_widget.path_to_terminal_requested.connect(self.send_remote_path_to_terminal)
        self.sidebar.sftp_widget.set_show_hidden(self.settings.get("sftp_show_hidden", False))
        self.sidebar.tool_triggered.connect(self.on_tool_triggered)
        self.sidebar.macro_triggered.connect(self.run_macro)
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
        self.multi_exec_bar.setStyleSheet("background-color: #3c3f41; border-top: 1px solid #555;")
        self.multi_exec_layout = QHBoxLayout(self.multi_exec_bar)
        self.multi_exec_layout.setContentsMargins(10, 0, 10, 0)
        self.multi_exec_label = QLabel("ALL TERMINALS:")
        self.multi_exec_label.setStyleSheet("color: red; font-weight: bold; font-size: 10px;")
        self.multi_exec_layout.addWidget(self.multi_exec_label)
        self.multi_exec_input = QLineEdit()
        self.multi_exec_input.setPlaceholderText("Type command to send to ALL active terminals...")
        self.multi_exec_input.setStyleSheet("background: #1a0000; color: #ffcccc; border: 1px solid red;")
        self.multi_exec_input.returnPressed.connect(self.broadcast_command)
        self.multi_exec_layout.addWidget(self.multi_exec_input)
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
        
        self.search_shortcut = QShortcut(QKeySequence("Ctrl+F"), self)
        self.search_shortcut.activated.connect(self.toggle_terminal_search)
        
        self.multi_exec_enabled = False
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

    def get_local_ip(self):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            log.debug("local IP detection failed", exc_info=True)
            return "127.0.0.1"

    def _setup_workspace_menu(self):
        menu = self.menuBar().addMenu("Workspaces")
        save_act = QAction("Save current SSH tabs...", self)
        save_act.triggered.connect(self.save_current_workspace)
        menu.addAction(save_act)

        open_act = QAction("Open workspace...", self)
        open_act.triggered.connect(self.open_workspace_profile)
        menu.addAction(open_act)

        delete_act = QAction("Delete workspace...", self)
        delete_act.triggered.connect(self.delete_workspace_profile)
        menu.addAction(delete_act)

    def broadcast_command(self):
        cmd = self.multi_exec_input.text() + "\r"
        if cmd:
            for i in range(self.tabs.count()):
                container = self.tabs.widget(i)
                if isinstance(container, TerminalContainer):
                    for term in container.findChildren(TerminalWidget):
                        term.write_to_backend(cmd)
            self.multi_exec_input.clear()

    def on_multi_exec_toggled(self, enabled):
        self.multi_exec_enabled = enabled
        if enabled: self.multi_exec_bar.show()
        else: self.multi_exec_bar.hide()
        for i in range(self.tabs.count()):
            container = self.tabs.widget(i)
            if isinstance(container, TerminalContainer):
                for term in container.findChildren(TerminalWidget):
                    term.set_broadcast_mode(enabled)

    def show_tab_context_menu(self, pos):
        index = self.tabs.tabBar().tabAt(pos)
        if index == -1: return
        menu = QMenu(self)
        
        pin_act = QAction("Pin tab" if index not in self.pinned_tabs else "Unpin tab", self)
        pin_act.triggered.connect(lambda: self.toggle_tab_pin(index))
        menu.addAction(pin_act)
        
        rename_act = QAction("Rename tab", self)
        rename_act.triggered.connect(lambda: self.rename_tab(index))
        menu.addAction(rename_act)
        
        color_act = QAction("Set tab color", self)
        color_act.triggered.connect(lambda: self.set_tab_color(index))
        menu.addAction(color_act)
        
        menu.addSeparator()
        duplicate_act = QAction("Duplicate tab", self)
        duplicate_act.triggered.connect(lambda: self.new_terminal_tab(self.tabs.tabText(index)))
        menu.addAction(duplicate_act)
        widget = self.tabs.widget(index)
        if isinstance(widget, TerminalContainer) and widget.ssh_session:
            reconnect_act = QAction("Reconnect tab", self)
            reconnect_act.triggered.connect(lambda: self._reconnect_tab(index))
            menu.addAction(reconnect_act)
            sftp_act = QAction("Open SFTP here", self)
            sftp_act.triggered.connect(lambda: self._attach_sftp_for_tab(index))
            menu.addAction(sftp_act)
            save_copy = QAction("Save session copy", self)
            save_copy.triggered.connect(lambda: self._save_session_copy(widget.ssh_session))
            menu.addAction(save_copy)
        
        menu.exec(self.tabs.mapToGlobal(pos))

    def toggle_tab_pin(self, index):
        # Qt's enum is QTabBar.ButtonPosition (QTabWidget has no TabButton).
        # On the close-button side: None restores the standard close button;
        # an empty widget effectively hides it (pinned).
        if index in self.pinned_tabs:
            self.pinned_tabs.remove(index)
            self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, None)
        else:
            self.pinned_tabs.add(index)
            self.tabs.tabBar().setTabButton(index, QTabBar.ButtonPosition.RightSide, QWidget())
        self.status_bar.showMessage(
            f"Tab {index} {'pinned' if index in self.pinned_tabs else 'unpinned'}", 4000
        )

    def rename_tab(self, index):
        new_name, ok = QInputDialog.getText(self, "Rename Tab", "New name:", QLineEdit.EchoMode.Normal, self.tabs.tabText(index))
        if ok and new_name: self.tabs.setTabText(index, new_name)

    def set_tab_color(self, index):
        color = QColorDialog.getColor(Qt.GlobalColor.white, self, "Select Tab Color")
        if color.isValid(): self.tabs.tabBar().setTabTextColor(index, color)

    def on_sidebar_collapsed(self, collapsed):
        if collapsed:
            self.splitter.setSizes([10, 1190])
        else:
            sizes = self.settings.get("main_splitter_sizes") or []
            if isinstance(sizes, list) and len(sizes) == 2 and sizes[0] > 20:
                self.splitter.setSizes(sizes)
            else:
                self.splitter.setSizes([260, 940])
            self._remember_layout_state()

    def _restore_layout_state(self):
        if self.settings.get("restore_window_geometry", True):
            main_sizes = self.settings.get("main_splitter_sizes") or []
            if isinstance(main_sizes, list) and len(main_sizes) == 2 and all(isinstance(v, int) for v in main_sizes):
                self.splitter.setSizes(main_sizes)
            sidebar_sizes = self.settings.get("sidebar_splitter_sizes") or []
            if (
                isinstance(sidebar_sizes, list)
                and len(sidebar_sizes) == 2
                and all(isinstance(v, int) for v in sidebar_sizes)
            ):
                self.sidebar.content_splitter.setSizes(sidebar_sizes)
            try:
                self.sidebar.tabs.setCurrentIndex(int(self.settings.get("last_sidebar_tab", 0) or 0))
            except (TypeError, ValueError):
                self.sidebar.tabs.setCurrentIndex(0)

    def _remember_layout_state(self):
        if not self.settings.get("restore_window_geometry", True):
            return
        main_sizes = self.splitter.sizes()
        if len(main_sizes) == 2 and main_sizes[0] > 20:
            self.settings["main_splitter_sizes"] = main_sizes
        self.settings["sidebar_splitter_sizes"] = self.sidebar.content_splitter.sizes()
        self.settings["last_sidebar_tab"] = self.sidebar.tabs.currentIndex()
        save_settings(self.settings)

    _TAB_POSITION_MAP = {
        "Top": QTabWidget.TabPosition.North,
        "Bottom": QTabWidget.TabPosition.South,
        "Left": QTabWidget.TabPosition.West,
        "Right": QTabWidget.TabPosition.East,
    }

    def apply_global_visuals(self):
        self.setWindowOpacity(self.settings["opacity"] / 100.0)
        if hasattr(self, "tabs"):
            pos = self._TAB_POSITION_MAP.get(
                self.settings.get("tab_position", "Top"),
                QTabWidget.TabPosition.North,
            )
            self.tabs.setTabPosition(pos)

    def open_settings_dialog(self):
        dialog = SettingsDialog(self, current_settings=self.settings)
        dialog.import_mobaxterm_requested.connect(self.import_mobaxterm_sessions)
        if dialog.exec():
            self.settings = dialog.get_settings()
            credentials.set_provider(self.settings.get("credential_provider", "system"))
            save_settings(self.settings)
            self.apply_global_visuals()
            self.sidebar.sftp_widget.set_show_hidden(self.settings.get("sftp_show_hidden", False))
            for i in range(self.tabs.count()):
                container = self.tabs.widget(i)
                if isinstance(container, TerminalContainer):
                    container.settings = self.settings
                    for term in container.findChildren(TerminalWidget):
                        term.settings = self.settings
                        term.apply_settings()
            self.status_bar.showMessage("Settings applied.")

    def show_diagnostics(self):
        ssh_agent = "unavailable"
        ssh_add = shutil.which("ssh-add")
        if ssh_add:
            try:
                proc = subprocess.run(
                    [ssh_add, "-l"],
                    capture_output=True,
                    text=True,
                    timeout=3,
                    check=False,
                )
                ssh_agent = "available" if proc.returncode == 0 else "no identities"
            except (OSError, subprocess.SubprocessError):
                ssh_agent = "error"

        try:
            app_version = importlib.metadata.version("bifrost-cm")
        except importlib.metadata.PackageNotFoundError:
            app_version = "development checkout"

        lines = [
            f"Bifrost: {app_version}",
            f"Python: {platform.python_version()} ({platform.system()} {platform.release()})",
            f"Qt: {QT_VERSION_STR}",
            f"Paramiko: {paramiko.__version__}",
            f"pyte: {getattr(pyte, '__version__', 'unknown')}",
            "",
            f"Config dir: {config_dir()}",
            f"Log file: {_log_path()}",
            f"Keyring available: {'yes' if credentials.is_available() else 'no'}",
            f"SSH agent: {ssh_agent}",
            f"Git: {shutil.which('git') or 'not found'}",
        ]
        QMessageBox.information(self, "Bifrost diagnostics", "\n".join(lines))

    def import_mobaxterm_sessions(self):
        parent = QApplication.activeModalWidget() or self
        path, _ = QFileDialog.getOpenFileName(
            parent, "Import MobaXterm sessions", "",
            "MobaXterm sessions (*.mxtsessions *.moba *.ini);;All files (*)",
        )
        if not path:
            return
        try:
            result = parse_mobaxterm_file(path)
        except (OSError, UnicodeError, configparser.Error) as e:
            QMessageBox.warning(parent, "MobaXterm import failed", str(e))
            return
        if result.imported == 0:
            QMessageBox.information(
                parent,
                "No sessions imported",
                "No supported SSH sessions were found in that MobaXterm file.",
            )
            return
        imported_group = ""
        for group_name, data in result.tree.items():
            imported_group = self.session_manager.import_group(group_name, data)
        self.sidebar.refresh_sessions()
        self._refresh_credentials_view()
        message = f"Imported {result.imported} MobaXterm session"
        if result.imported != 1:
            message += "s"
        message += f" into {imported_group}"
        if result.skipped:
            message += f" ({result.skipped} unsupported skipped)"
        self.status_bar.showMessage(message, 6000)

    def show_dashboard(self):
        dashboard = Dashboard(recent_sessions=self.session_manager.recent_sessions)
        dashboard.session_requested.connect(self._dashboard_session_requested)
        dashboard.btn_ssh.clicked.connect(lambda: self.new_terminal_tab("Local Shell"))
        dashboard.btn_session.clicked.connect(self.open_session_dialog)
        # Sidebar tabs after the SFTP-pane refactor: 0 Sessions, 1 Credentials,
        # 2 SSH, 3 Servers, 4 Tools, 5 Macros.
        dashboard.btn_tools.clicked.connect(lambda: self.sidebar.tabs.setCurrentIndex(4))
        self.tabs.addTab(dashboard, "🏠 Home")
        self.tabs.setCurrentIndex(self.tabs.count()-1)

    def _dashboard_session_requested(self, name: str):
        """Route Dashboard recent-session clicks through the dict-based flow.

        Looks up the saved session by name so we route by type instead of
        sniffing the string. If it's not found (e.g. an ad-hoc quick-connect
        name in recents), fall back to a Local Shell.
        """
        session = self.session_manager.find_by_name(name)
        if session is not None:
            self.on_session_activated(session)
        else:
            self.new_terminal_tab(name)

    def toggle_terminal_search(self):
        current = self.tabs.currentWidget()
        if isinstance(current, TerminalContainer): current.toggle_search()

    def update_metrics(self):
        try:
            cpu = psutil.cpu_percent()
            mem = psutil.virtual_memory().percent
            self.cpu_label.setText(f"CPU: {cpu}%")
            self.mem_label.setText(f"MEM: {mem}%")
        except (psutil.Error, OSError):
            log.debug("metrics update failed", exc_info=True)

    def run_macro(self, name):
        macro = self.macro_engine.get_macro(name)
        current_tab = self.tabs.currentWidget()
        if isinstance(current_tab, TerminalContainer) and macro:
            term = current_tab.findChild(TerminalWidget)
            if term:
                for key in macro: term.write_to_backend(key)

    def toggle_macro_recording(self):
        if not self.macro_engine.recording:
            self.macro_engine.start_recording()
            self.sidebar.record_btn.setText("STOP Recording")
        else:
            name, ok = QInputDialog.getText(self, "Save Macro", "Macro Name:")
            if ok and name:
                self.macro_engine.stop_recording(name)
                self.sidebar.refresh_macros()
            self.sidebar.record_btn.setText("Record Macro")

    def open_file_in_editor(self, remote_path: str):
        """Fetch a remote file via the currently-attached SFTP and open it.

        Honors the `default_editor_command` setting: if set, the file is
        downloaded and launched with that external editor (shelled out via
        subprocess.Popen). Otherwise the built-in `MobaEditor` tab opens.

        To push edits back to the remote, the user uses the SFTP browser's
        Upload action.
        """
        import shlex
        import subprocess
        import tempfile

        sftp = self.sidebar.sftp_widget.sftp
        local_path: str | None = None

        if sftp is not None:
            try:
                fd, local_path = tempfile.mkstemp(
                    prefix="bifrost-",
                    suffix="-" + (os.path.basename(remote_path) or "file"),
                )
                os.close(fd)
                sftp.get(remote_path, local_path)
            except Exception as e:
                log.exception("Failed to fetch remote file %s", remote_path)
                local_path = None
                editor = MobaEditor()
                editor.set_content(f"# Failed to fetch {remote_path}:\n# {e}\n")
                self.tabs.addTab(editor, f"📝 {os.path.basename(remote_path) or 'Editor'}")
                self.tabs.setCurrentIndex(self.tabs.count() - 1)
                return

        ext_cmd = (self.settings.get("default_editor_command") or "").strip()
        if ext_cmd and local_path:
            argv = shlex.split(ext_cmd) + [local_path]
            try:
                subprocess.Popen(argv)
                self.status_bar.showMessage(
                    f"Opened {os.path.basename(local_path)} in external editor", 4000,
                )
                return
            except OSError as e:
                log.warning("Failed to launch external editor %r: %s", argv, e)
                # Fall through to the built-in editor.

        editor = MobaEditor()
        if local_path:
            editor.open_path(local_path)
        else:
            editor.set_content(
                f"# {remote_path}\n# (No SFTP connection — open a local file via Save As to start editing.)\n",
            )
        self.tabs.addTab(editor, f"📝 {os.path.basename(remote_path) or 'Editor'}")
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _download_remote_temp(self, remote_path: str) -> str | None:
        import tempfile

        sftp = self.sidebar.sftp_widget.sftp
        if sftp is None:
            return None
        fd, local_path = tempfile.mkstemp(
            prefix="bifrost-",
            suffix="-" + (os.path.basename(remote_path) or "file"),
        )
        os.close(fd)
        try:
            sftp.get(remote_path, local_path)
        except Exception:
            try:
                os.unlink(local_path)
            except OSError:
                pass
            raise
        return local_path

    def _open_local_with_command(self, local_path: str, command: str, label: str) -> bool:
        import shlex

        argv = shlex.split(command) + [local_path]
        try:
            subprocess.Popen(argv)
        except OSError as e:
            log.warning("Failed to launch %s %r: %s", label, argv, e)
            return False
        self.status_bar.showMessage(f"Opened {os.path.basename(local_path)} with {label}", 4000)
        return True

    def open_file_in_text_editor(self, remote_path: str):
        try:
            local_path = self._download_remote_temp(remote_path)
        except Exception as e:
            log.exception("Failed to fetch remote file %s", remote_path)
            QMessageBox.warning(self, "Open in text editor failed", str(e))
            return

        command = (self.settings.get("default_text_editor_command") or "").strip()
        if command and local_path and self._open_local_with_command(local_path, command, "text editor"):
            return

        editor = MobaEditor()
        if local_path:
            editor.open_path(local_path)
        else:
            editor.set_content(f"# {remote_path}\n")
        self.tabs.addTab(editor, f"Editor: {os.path.basename(remote_path) or 'remote file'}")
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def open_file_with_command(self, remote_path: str, command: str):
        try:
            local_path = self._download_remote_temp(remote_path)
        except Exception as e:
            log.exception("Failed to fetch remote file %s", remote_path)
            QMessageBox.warning(self, "Open with command failed", str(e))
            return
        if local_path:
            self._open_local_with_command(local_path, command, "custom command")

    def open_file_with_system_default(self, remote_path: str):
        try:
            local_path = self._download_remote_temp(remote_path)
        except Exception as e:
            log.exception("Failed to fetch remote file %s", remote_path)
            QMessageBox.warning(self, "Open with system default failed", str(e))
            return
        if local_path and QDesktopServices.openUrl(QUrl.fromLocalFile(local_path)):
            self.status_bar.showMessage(f"Opened {os.path.basename(remote_path)} with system default", 4000)
        elif local_path:
            QMessageBox.warning(self, "Open with system default failed", local_path)

    def send_remote_path_to_terminal(self, remote_path: str):
        current_tab = self.tabs.currentWidget()
        if not isinstance(current_tab, TerminalContainer):
            return
        term = current_tab.findChild(TerminalWidget)
        if term is not None:
            term.write_to_backend(remote_path)

    def on_tool_triggered(self, tool_name):
        if tool_name == "Port Scanner":
            host, ok = QInputDialog.getText(self, "Port Scanner", "Host:", QLineEdit.EchoMode.Normal, "127.0.0.1")
            if ok and host:
                open_ports = scan_ports(host, 1, 100)
                QMessageBox.information(self, "Scan Results", f"Open ports: {open_ports}")
        elif tool_name == "Network Scanner":
            base, ok = QInputDialog.getText(self, "Network Scanner", "IP Subnet:", QLineEdit.EchoMode.Normal, "127.0.0")
            if ok and base:
                active = scan_ip_range(base)
                QMessageBox.information(self, "Network Scan", f"Active hosts found:\n{active}")
        elif tool_name == "IP Calculator":
            cidr, ok = QInputDialog.getText(
                self, "IP Calculator",
                "CIDR (e.g. 10.0.0.0/24 or 192.168.1.5):",
                QLineEdit.EchoMode.Normal, "10.0.0.0/24",
            )
            if not ok or not cidr.strip():
                return
            try:
                info = ip_tools.calculate(cidr)
            except ValueError as e:
                QMessageBox.warning(self, "IP Calculator", str(e))
                return
            lines = "\n".join(f"{k:<14} {v}" for k, v in info.items())
            QMessageBox.information(self, f"IP Calculator — {cidr}", lines)
        elif tool_name == "SSH Key Gen":
            self._run_ssh_keygen()

    def _run_ssh_keygen(self):
        default = os.path.expanduser("~/.ssh/id_ed25519")
        path, _ = QFileDialog.getSaveFileName(
            self, "Generate SSH key — choose output file", default,
        )
        if not path:
            return
        passphrase, ok = QInputDialog.getText(
            self, "Key passphrase",
            "Passphrase (empty = unencrypted; keyring opt-in is on next prompt):",
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return
        try:
            priv, pub = keygen.generate_keypair(path, algorithm="ed25519", passphrase=passphrase or None)
        except FileExistsError as e:
            QMessageBox.warning(self, "Key Gen", str(e))
            return
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "Key Gen failed", str(e))
            return
        if passphrase and credentials.is_available():
            reply = QMessageBox.question(
                self, "Store passphrase?",
                f"Save the passphrase for {priv} in the system keyring?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                credentials.set_passphrase(priv, passphrase)
        QMessageBox.information(
            self, "Key Gen",
            f"Generated:\n• {priv}\n• {pub}\n\n"
            "Copy the .pub line into the remote host's ~/.ssh/authorized_keys.",
        )

    def on_session_activated(self, session: dict):
        """Route a session opening by its explicit `type`, not by name sniffing."""
        name = session.get("name") or "Session"
        proto = session.get("type")
        if proto == "WSL":
            self.new_terminal_tab(name, kind="WSL", distro=session.get("distro") or None)
        elif proto == "SSH":
            self.new_terminal_tab(name, ssh_session=session)
        elif proto == "Local":
            cmd = session.get("cmd")
            self.new_terminal_tab(name, command=[cmd] if isinstance(cmd, str) else cmd)
        else:
            self.new_terminal_tab(name)

    def save_current_workspace(self):
        sessions = self._current_workspace_sessions()
        if not sessions:
            QMessageBox.information(
                self,
                "Save workspace",
                "There are no SSH tabs to save in this workspace.",
            )
            return
        name, ok = QInputDialog.getText(self, "Save workspace", "Workspace name:")
        if not ok or not name.strip():
            return
        try:
            self.workspace_manager.upsert(name, sessions)
        except ValueError as e:
            QMessageBox.warning(self, "Save workspace failed", str(e))
            return
        self.status_bar.showMessage(
            f"Saved workspace {name.strip()} with {len(sessions)} session(s)", 5000,
        )

    def open_workspace_profile(self):
        names = self.workspace_manager.names()
        if not names:
            QMessageBox.information(self, "Open workspace", "No workspace profiles saved yet.")
            return
        name, ok = QInputDialog.getItem(
            self, "Open workspace", "Workspace:", names, 0, False,
        )
        if not ok or not name:
            return
        sessions = self.workspace_manager.get(name)
        if not sessions:
            QMessageBox.warning(self, "Open workspace", "Workspace is empty or missing.")
            return
        for session in sessions:
            self.on_session_activated(session)
        self.status_bar.showMessage(
            f"Opened workspace {name} ({len(sessions)} session(s))", 5000,
        )

    def delete_workspace_profile(self):
        names = self.workspace_manager.names()
        if not names:
            QMessageBox.information(self, "Delete workspace", "No workspace profiles saved yet.")
            return
        name, ok = QInputDialog.getItem(
            self, "Delete workspace", "Workspace:", names, 0, False,
        )
        if not ok or not name:
            return
        reply = QMessageBox.question(
            self,
            "Delete workspace",
            f"Delete workspace '{name}'?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        if self.workspace_manager.delete(name):
            self.status_bar.showMessage(f"Deleted workspace {name}", 5000)

    def _current_workspace_sessions(self) -> list[dict]:
        sessions: list[dict] = []
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            if not isinstance(widget, TerminalContainer):
                continue
            backend = self._ssh_backend_of(widget)
            if widget.ssh_session:
                session = dict(widget.ssh_session)
            elif backend is not None:
                session = self._session_from_backend(widget.name, backend)
            else:
                continue
            if session.get("type") == "SSH" or session.get("host"):
                sessions.append(session)
        return sessions

    def on_favorite_toggled(self, session: dict, _new_state: bool):
        # The session dict is the same object the sidebar mutated, so we only
        # need to persist. SessionManager.save writes the whole tree atomically.
        self.session_manager.save()

    def on_quick_connect(self, method: str, text: str):
        text = (text or "").strip()
        if method == "SSH":
            if not text:
                return
            # Allow user@host[:port] in one shot.
            user, _, host_port = text.partition("@")
            if not host_port:
                host_port, user = user, ""
            host, _, port = host_port.partition(":")
            default_user = self.settings.get("ssh_default_user", "") or ""
            default_port = int(self.settings.get("ssh_default_port", 22) or 22)
            session = {
                "host": host or text,
                "user": user or default_user,
                "port": int(port) if port.isdigit() else default_port,
                "auth": "agent",
                "type": "SSH",
            }
            display_user = session["user"]
            display = f"{display_user}@{host}" if display_user else host
            self.new_terminal_tab(display or text, ssh_session=session)
        elif method == "Telnet":
            host, _, port = text.partition(":")
            cmd = ["telnet", host or "localhost"]
            if port:
                cmd.append(port)
            self.new_terminal_tab(text or "telnet", command=cmd)
        elif method == "WSL":
            self.new_terminal_tab(f"WSL: {text or 'default'}", kind="WSL", distro=text or None)
        elif method == "Local":
            cmd = [text] if text else None
            self.new_terminal_tab(text or "Local Shell", command=cmd)

    def on_wol_dialog(self):
        mac, ok = QInputDialog.getText(
            self, "Wake on LAN", "MAC address (AA:BB:CC:11:22:33):",
        )
        if not ok or not mac.strip():
            return
        try:
            wake_on_lan.send_magic_packet(mac.strip())
        except ValueError as e:
            QMessageBox.warning(self, "Wake on LAN", f"Invalid MAC address: {e}")
            return
        except OSError as e:
            QMessageBox.warning(self, "Wake on LAN", f"Failed to send packet: {e}")
            return
        self.status_bar.showMessage(f"WoL packet sent to {mac.strip()}", 4000)

    def on_wake_on_lan(self, session: dict):
        mac = (session.get("mac") or "").strip()
        if not mac:
            self.status_bar.showMessage("Session has no MAC address configured", 4000)
            return
        broadcast = (session.get("wol_broadcast") or "255.255.255.255").strip() or "255.255.255.255"
        try:
            wake_on_lan.send_magic_packet(mac, broadcast_address=broadcast)
        except ValueError as e:
            QMessageBox.warning(self, "Wake on LAN", f"Invalid MAC address: {e}")
            return
        except OSError as e:
            QMessageBox.warning(self, "Wake on LAN", f"Failed to send packet: {e}")
            return
        self.status_bar.showMessage(
            f"WoL packet sent to {mac} via {broadcast}", 4000,
        )

    def on_forget_credentials(self, session: dict):
        host = session.get("host", "")
        user = session.get("user", "")
        port = session.get("port", 22)
        key_path = session.get("key_path") or ""
        removed_pw = credentials.forget_password(user, host, port)
        removed_pp = credentials.forget_passphrase(key_path) if key_path else False
        if removed_pw or removed_pp:
            self.status_bar.showMessage(
                f"Cleared saved credentials for {user}@{host}", 4000,
            )
        else:
            self.status_bar.showMessage(
                f"No saved credentials found for {user}@{host}", 4000,
            )
        self._refresh_credentials_view()

    def new_terminal_tab(
        self,
        name="Local Shell",
        command=None,
        is_ssh=False,
        kind=None,
        distro=None,
        ssh_session: dict | None = None,
    ):
        backend = None
        session = None
        prefix = "🐚 "

        if kind == "WSL" or (kind is None and "WSL" in name):
            command = wsl.spawn_command(distro)
            prefix = "🐧 "
        elif ssh_session is not None or is_ssh:
            session = ssh_session or self.session_manager.find_by_name(name)
            backend = self._build_ssh_backend(name, session)
            if backend is None:
                return  # user cancelled the password prompt
            if session is None:
                session = self._session_from_backend(name, backend)
            prefix = "🌐 "

        if name != "Local Shell":
            self.session_manager.add_to_recents(name)

        container = TerminalContainer(
            name,
            command,
            self.on_terminal_key,
            settings=self.settings,
            backend=backend,
            ssh_session=session if backend is not None else None,
        )
        container.detach_requested.connect(self.detach_terminal)
        self.tabs.addTab(container, prefix + name)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _session_from_backend(self, name: str, backend: ParamikoBackend) -> dict:
        creds = backend.creds
        return {
            "name": name,
            "type": "SSH",
            "host": creds.host,
            "user": creds.username,
            "port": creds.port,
            "auth": creds.auth,
            "key_path": creds.key_filename,
            "command": creds.startup_command,
        }

    def _build_ssh_backend(self, name: str, session: dict | None) -> ParamikoBackend | None:
        if not session or "host" not in session:
            # Fall back to parsing user@host out of the name (quick-connect path).
            user, _, host = name.partition("@")
            if not host:
                host, user = user, ""
            session = {
                "host": host,
                "user": user or self.settings.get("ssh_default_user", "") or "",
                "port": int(self.settings.get("ssh_default_port", 22) or 22),
                "auth": self.settings.get("ssh_default_auth", "agent") or "agent",
            }
            if session["auth"] == "key":
                session["key_path"] = self.settings.get("ssh_default_key_path", "") or None

        creds = SshCredentials.from_session(session)
        if not creds.startup_command:
            creds.startup_command = self.settings.get("ssh_startup_command", "") or ""
        # Apply settings-level defaults that aren't part of the session dict.
        if "connect_timeout" not in session:
            try:
                creds.connect_timeout = float(self.settings.get("ssh_connect_timeout", 15) or 15)
            except (TypeError, ValueError):
                creds.connect_timeout = 15.0
        if "agent_forwarding" not in session:
            creds.agent_forwarding = bool(self.settings.get("ssh_agent_forwarding", False))
        if "known_hosts_file" not in session:
            creds.known_hosts_file = self.settings.get("known_hosts_file") or None
        if "keepalive_interval" not in session:
            try:
                creds.keepalive_interval = int(self.settings.get("ssh_keepalive_interval", 0) or 0)
            except (TypeError, ValueError):
                creds.keepalive_interval = 0
        if "tcp_keepalive" not in session:
            creds.tcp_keepalive = bool(self.settings.get("ssh_tcp_keepalive", True))

        # Track whether we should persist after a successful connect.
        save_password = False
        save_passphrase = False
        keyring_ok = credentials.is_available()
        credential_store = credentials.provider_label()
        credential_policy = self.settings.get("credential_save_policy", "ask")
        remember_enabled = keyring_ok and credential_policy != "never"

        if creds.auth == "password":
            stored = credentials.get_password(creds.username, creds.host, creds.port)
            if stored is not None:
                creds.password = stored
            else:
                text, remember = CredentialPrompt.ask(
                    title=f"Password for {creds.username}@{creds.host}",
                    prompt=f"Enter SSH password for {creds.username}@{creds.host}:{creds.port}",
                    remember_enabled=remember_enabled,
                    remember_label=f"Remember in {credential_store}",
                    parent=self,
                )
                if text is None:
                    return None
                creds.password = text
                save_password = remember and credential_policy != "never"
        elif creds.auth == "key":
            stored = credentials.get_passphrase(creds.key_filename or "")
            if stored is not None:
                creds.passphrase = stored
            else:
                # Passphrase prompt is optional — user can leave blank for an
                # unencrypted key. Remember is offered too.
                text, remember = CredentialPrompt.ask(
                    title=f"Passphrase for {creds.key_filename or '(key)'}",
                    prompt="Enter key passphrase (leave blank if the key is unencrypted):",
                    remember_enabled=remember_enabled,
                    remember_label=f"Remember in {credential_store}",
                    parent=self,
                )
                if text is None:
                    return None
                creds.passphrase = text or None
                save_passphrase = remember and bool(text) and credential_policy != "never"

        policy = QtHostKeyPolicy(self.host_key_prompter)
        backend = ParamikoBackend(creds, host_key_policy=policy)
        self._last_ssh_backend = backend

        if save_password or save_passphrase:
            self._save_credentials_on_success(
                backend,
                save_password=save_password,
                save_passphrase=save_passphrase,
            )

        return backend

    def _save_credentials_on_success(
        self,
        backend: ParamikoBackend,
        *,
        save_password: bool,
        save_passphrase: bool,
    ) -> None:
        """Poll until the SSH connect finishes; on success, persist to keyring."""
        def check():
            if not backend.wait_ready(timeout=0):
                QTimer.singleShot(300, check)
                return
            if backend.connect_error is not None:
                # Don't save credentials we know are wrong.
                return
            creds = backend.creds
            persisted = False
            if save_password and creds.password:
                if credentials.set_password(
                    creds.username, creds.host, creds.port, creds.password
                ):
                    persisted = True
                    self.status_bar.showMessage(
                        f"Saved password for {creds.username}@{creds.host} to {credentials.provider_label()}",
                        4000,
                    )
            if save_passphrase and creds.passphrase and creds.key_filename:
                if credentials.set_passphrase(creds.key_filename, creds.passphrase):
                    persisted = True
                    self.status_bar.showMessage(
                        f"Saved passphrase for {creds.key_filename} to {credentials.provider_label()}",
                        4000,
                    )
            if persisted:
                self._refresh_credentials_view()

        QTimer.singleShot(300, check)

    def detach_terminal(self, container):
        index = self.tabs.indexOf(container)
        if index != -1:
            name = self.tabs.tabText(index)
            self.tabs.removeTab(index)
            new_win = BifrostApp(is_detached=True, settings=self.settings)
            new_win.setWindowTitle(f"Detached: {name}")
            new_win.tabs.addTab(container, name)
            new_win.show()
            self.detached_windows.append(new_win)

    def on_split_requested(self, orientation):
        current = self.tabs.currentWidget()
        if isinstance(current, TerminalContainer): current.split(orientation)

    def on_terminal_key(self, key):
        if self.macro_engine.recording: self.macro_engine.record_key(key)
        if self.multi_exec_enabled:
            for i in range(self.tabs.count()):
                container = self.tabs.widget(i)
                if isinstance(container, TerminalContainer):
                    for term in container.findChildren(TerminalWidget): term.write_to_backend(key)
        else:
            sender = self.sender()
            if isinstance(sender, TerminalWidget): sender.write_to_backend(key)

    def export_sessions(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Export sessions", "bifrost-sessions.json",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        try:
            encrypt = QMessageBox.question(
                self,
                "Encrypt export?",
                "Encrypt this session export with a password?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if encrypt == QMessageBox.StandardButton.Yes:
                password, ok = QInputDialog.getText(
                    self, "Export password", "Password:", QLineEdit.EchoMode.Password,
                )
                if not ok or not password:
                    return
                self.session_manager.export_sessions_encrypted(path, password)
            else:
                self.session_manager.export_sessions(path)
        except OSError as e:
            QMessageBox.warning(self, "Export failed", str(e))
            return
        except ValueError as e:
            QMessageBox.warning(self, "Export failed", str(e))
            return
        self.status_bar.showMessage(f"Exported sessions to {path}", 4000)

    def import_sessions(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import sessions", "",
            "JSON files (*.json);;All files (*)",
        )
        if not path:
            return
        before = len(self.session_manager.sessions)
        try:
            with open(path, "r", encoding="utf-8") as f:
                incoming = json.load(f)
            if session_crypto.is_encrypted_session_file(incoming):
                password, ok = QInputDialog.getText(
                    self, "Import password", "Password:", QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return
                self.session_manager.import_sessions_encrypted(path, password)
            else:
                self.session_manager.import_sessions(path)
        except (OSError, ValueError, json.JSONDecodeError) as e:
            QMessageBox.warning(self, "Import failed", str(e))
            return
        after = len(self.session_manager.sessions)
        self.sidebar.refresh_sessions()
        self.status_bar.showMessage(
            f"Imported sessions from {path} ({after - before} new top-level group{'s' if after - before != 1 else ''})",
            4000,
        )

    def open_session_dialog(self, parent_path=None):
        # `parent_path` may arrive as False (Qt's default clicked-signal arg)
        # or as a list (the sidebar's new_session_requested signal). Normalize.
        if not isinstance(parent_path, list):
            parent_path = None
        dialog = SessionDialog(self)
        if dialog.exec():
            data = dialog.get_data()
            try:
                if parent_path is None:
                    self.session_manager.add_session("User sessions", data)
                else:
                    added = self.session_manager.add_session_at(parent_path, data)
                    if added is not None and added != data.get("name"):
                        data["name"] = added
            except ValueError as e:
                QMessageBox.warning(self, "Can't add session", str(e))
                return
            self.sidebar.refresh_sessions()
            self._refresh_credentials_view()
            if data["type"] == "WSL":
                self.new_terminal_tab(data["name"], kind="WSL", distro=data.get("distro") or None)
            elif data["type"] == "SSH":
                self.new_terminal_tab(data["name"], ssh_session=data)
            else:
                self.new_terminal_tab(data["name"])

    def edit_session(self, parent_path: list, session: dict, section: str = "connection"):
        dialog = SessionDialog(self, session=session)
        dialog.set_current_section(section)
        if not dialog.exec():
            return
        data = dialog.get_data()
        try:
            ok = self.session_manager.update_session(parent_path, session, data)
        except ValueError as e:
            QMessageBox.warning(self, "Can't update session", str(e))
            return
        if not ok:
            QMessageBox.warning(self, "Can't update session", "Session was not found.")
            return
        self.sidebar.refresh_sessions()
        self._refresh_credentials_view()
        self.status_bar.showMessage(f"Updated session {data['name']}", 4000)

    def _save_session_copy(self, session: dict):
        data = dict(session)
        data["name"] = f"{data.get('name', 'session')} (copy)"
        added = self.session_manager.add_session_at(["User sessions"], data)
        if added:
            data["name"] = added
            self.sidebar.refresh_sessions()
            self.status_bar.showMessage(f"Saved session copy {added}", 4000)

    def close_tab(self, index):
        if index in self.pinned_tabs:
            QMessageBox.information(self, "Tab Pinned", "This tab is pinned and cannot be closed. Unpin it first.")
            return
        if self.tabs.count() == 0:
            return
        widget = self.tabs.widget(index)
        if self.settings.get("confirm_close_tab", True) and self._tab_is_live(widget):
            name = self.tabs.tabText(index)
            reply = QMessageBox.question(
                self, "Close tab",
                f"Close “{name}”?\n\nThe session will be disconnected.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        widget.deleteLater()
        self.tabs.removeTab(index)

    def _tab_is_live(self, widget) -> bool:
        """A tab is 'live' if it contains at least one terminal whose backend is still running."""
        if not isinstance(widget, TerminalContainer):
            return False
        for term in widget.findChildren(TerminalWidget):
            backend = getattr(term, "backend", None)
            if backend is None:
                continue
            if isinstance(backend, ParamikoBackend):
                if not backend._closed and backend.channel is not None:
                    return True
            else:
                if not getattr(backend, "_closed", True):
                    return True
        return False

    def closeEvent(self, event):
        # Save window geometry first so a "confirm and cancel" path still updates
        # the blob (the user's last-seen state is the right snapshot to keep).
        if self.settings.get("restore_window_geometry", True):
            try:
                blob = bytes(self.saveGeometry()).hex()
                self.settings["window_geometry"] = blob
                main_sizes = self.splitter.sizes()
                if len(main_sizes) == 2 and main_sizes[0] > 20:
                    self.settings["main_splitter_sizes"] = main_sizes
                self.settings["sidebar_splitter_sizes"] = self.sidebar.content_splitter.sizes()
                self.settings["last_sidebar_tab"] = self.sidebar.tabs.currentIndex()
                save_settings(self.settings)
            except Exception:
                log.debug("saveGeometry failed", exc_info=True)

        if self.settings.get("confirm_quit_with_sessions", True):
            live = sum(
                1 for i in range(self.tabs.count())
                if self._tab_is_live(self.tabs.widget(i))
            )
            if live > 0:
                reply = QMessageBox.question(
                    self, "Quit Bifrost",
                    f"{live} session{'s' if live != 1 else ''} still active. Quit anyway?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    event.ignore()
                    return
        super().closeEvent(event)

    def on_tab_changed(self, index):
        # Keep the SSH browser pane in sync as tabs come and go.
        self._refresh_ssh_browser()
        if index < 0:
            self.remote_monitor.set_backend(None)
            return
        name = self.tabs.tabText(index)
        widget = self.tabs.widget(index)
        ssh_backend = self._ssh_backend_of(widget)
        self.remote_monitor.set_backend(ssh_backend)

        if ssh_backend is not None:
            # MobaXterm-style: SFTP pane is always visible alongside the
            # terminal. Auto-expand it when an SSH tab activates if the user
            # has auto_sftp on; otherwise leave the user's split untouched.
            if self.settings.get("auto_sftp", True):
                self.sidebar.show_sftp_pane()
            self._attach_sftp_when_ready(ssh_backend)
        else:
            # Non-SSH tab: drop the attachment and collapse the SFTP pane so
            # we don't show stale state or waste screen real estate.
            if self.sidebar.sftp_widget.is_attached():
                self.sidebar.sftp_widget.detach()
            self.sidebar.hide_sftp_pane()

        if "Servers" in name:
            self.sidebar.tabs.setCurrentIndex(3)  # Servers tab (was 4 before SFTP moved out)

    def _refresh_ssh_browser(self):
        from widgets.ssh_browser import ActiveConnection

        connections: list[ActiveConnection] = []
        for i in range(self.tabs.count()):
            backend = self._ssh_backend_of(self.tabs.widget(i))
            if backend is None:
                continue
            if backend._closed:
                status = "closed"
            elif backend.connect_error is not None:
                status = "failed"
            elif backend.channel is not None:
                status = "connected"
            else:
                status = "connecting"
            connections.append(ActiveConnection(
                tab_index=i,
                host=backend.creds.host,
                user=backend.creds.username,
                port=backend.creds.port,
                status=status,
            ))
        self.sidebar.ssh_browser.update_from_tabs(connections)

    def _refresh_credentials_view(self):
        """Walk the saved sessions tree and let the keyring view check what's stored."""
        sessions: list[dict] = []
        def walk(node):
            if isinstance(node, dict):
                for v in node.values():
                    walk(v)
            elif isinstance(node, list):
                for item in node:
                    if isinstance(item, dict):
                        sessions.append(item)
        walk(self.session_manager.sessions)
        self.sidebar.cred_widget.set_sessions(sessions)

    def _disconnect_tab(self, tab_index: int):
        if tab_index < 0 or tab_index >= self.tabs.count():
            return
        widget = self.tabs.widget(tab_index)
        backend = self._ssh_backend_of(widget)
        if backend is None:
            return
        backend.close()
        self._refresh_ssh_browser()
        self.status_bar.showMessage(
            f"Disconnected {backend.creds.username}@{backend.creds.host}", 4000,
        )

    def _reconnect_tab(self, tab_index: int):
        if tab_index < 0 or tab_index >= self.tabs.count():
            return
        widget = self.tabs.widget(tab_index)
        if not isinstance(widget, TerminalContainer):
            return
        backend = self._ssh_backend_of(widget)
        session = widget.ssh_session or (
            self._session_from_backend(widget.name, backend) if backend is not None else None
        )
        if session is None:
            self.status_bar.showMessage("No SSH session details available for reconnect", 4000)
            return
        if backend is not None:
            backend.close()
        old_name = self.tabs.tabText(tab_index)
        self.tabs.removeTab(tab_index)
        widget.deleteLater()
        self.new_terminal_tab(session.get("name") or old_name, ssh_session=session)
        self._refresh_ssh_browser()
        self.status_bar.showMessage(
            f"Reconnecting {session.get('user', '')}@{session.get('host', '')}", 4000,
        )

    def _attach_sftp_for_tab(self, tab_index: int):
        if tab_index < 0 or tab_index >= self.tabs.count():
            return
        backend = self._ssh_backend_of(self.tabs.widget(tab_index))
        if backend is None:
            return
        self.tabs.setCurrentIndex(tab_index)
        self.sidebar.show_sftp_pane()
        self._attach_sftp_when_ready(backend)

    def _ssh_backend_of(self, widget) -> ParamikoBackend | None:
        if not isinstance(widget, TerminalContainer):
            return None
        term = widget.findChild(TerminalWidget)
        backend = getattr(term, "backend", None)
        return backend if isinstance(backend, ParamikoBackend) else None

    def _attach_sftp_when_ready(self, backend: ParamikoBackend):
        """Poll until the SSH connection is ready, then attach the SFTP browser."""
        if backend.wait_ready(timeout=0):
            self._refresh_ssh_browser()
            if backend.client is not None:
                self.sidebar.sftp_widget.attach(backend.client)
            return

        # Not ready yet — poll every 250 ms. The current-tab guard means we
        # stop polling if the user switches away.
        def poll():
            if self._ssh_backend_of(self.tabs.currentWidget()) is not backend:
                return  # user switched tabs; stop polling
            if backend.wait_ready(timeout=0):
                self._refresh_ssh_browser()
                if backend.client is not None:
                    self.sidebar.sftp_widget.attach(backend.client)
                return
            QTimer.singleShot(250, poll)

        QTimer.singleShot(250, poll)

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

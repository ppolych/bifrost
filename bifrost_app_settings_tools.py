from bifrost_app_deps import *
from core.snippet_variables import expand_snippet


class BifrostSettingsToolsMixin:
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

    def open_saved_credentials_dialog(self):
        existing = getattr(self, "_credentials_dialog", None)
        if existing is not None:
            existing.raise_()
            existing.activateWindow()
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Saved credentials")
        dialog.resize(760, 420)
        layout = QVBoxLayout(dialog)
        view = CredentialManager(dialog)
        view.refresh_requested.connect(self._refresh_credentials_view)
        view.forget_requested.connect(self.on_forget_credentials)
        layout.addWidget(view)
        self._credentials_dialog = dialog
        self._credentials_view = view
        dialog.finished.connect(lambda _result: self._clear_credentials_dialog_refs())
        self._refresh_credentials_view()
        dialog.show()

    def _clear_credentials_dialog_refs(self):
        self._credentials_dialog = None
        self._credentials_view = None

    def open_command_palette(self):
        dialog = CommandPalette(self._command_palette_entries(), self)
        dialog.exec()

    def _command_palette_entries(self) -> list[PaletteEntry]:
        entries = [
            PaletteEntry("Session: Start local terminal", lambda: self.new_terminal_tab("Local Shell")),
            PaletteEntry("Session: New session...", self.open_session_dialog),
            PaletteEntry("Session: Import OpenSSH config...", self.import_ssh_config_sessions),
            PaletteEntry("Connections: Reconnect current tab", self.reconnect_current_tab),
            PaletteEntry("Connections: Reconnect all disconnected", self._reconnect_all_disconnected),
            PaletteEntry("Connections: Open SFTP here", self.attach_sftp_for_current_tab),
            PaletteEntry("Connections: Saved credentials...", self.open_saved_credentials_dialog),
            PaletteEntry("View: Toggle sidebar", self.sidebar.toggle_collapse),
            PaletteEntry("View: Toggle SFTP pane", self.toggle_sftp_pane),
            PaletteEntry("Tools: Settings...", self.open_settings_dialog),
            PaletteEntry("Tools: Diagnostics...", self.show_diagnostics),
            PaletteEntry("Workspaces: Save current SSH tabs...", self.save_current_workspace),
            PaletteEntry("Workspaces: Open workspace...", self.open_workspace_profile),
        ]
        for path, session in _iter_sessions(self.session_manager.sessions):
            name = session.get("name") or path
            entries.append(
                PaletteEntry(
                    f"Open session: {name} ({path})",
                    lambda s=session: self.on_session_activated(s),
                )
            )
        for group, items in sorted(self.snippet_manager.snippets.items()):
            for name, command in sorted(items.items()):
                label = f"{group}/{name}"
                entries.append(
                    PaletteEntry(
                        f"Snippet: Insert {label}",
                        lambda text=command: self.run_snippet(text, execute=False),
                    )
                )
                entries.append(
                    PaletteEntry(
                        f"Snippet: Run {label}",
                        lambda text=command: self.run_snippet(text, execute=True),
                    )
                )
        return entries

    def show_diagnostics(self):
        text = self.diagnostics_text()
        box = QMessageBox(self)
        box.setWindowTitle("Bifrost diagnostics")
        box.setText(text)
        copy_btn = box.addButton("Copy diagnostics", QMessageBox.ButtonRole.ActionRole)
        box.addButton(QMessageBox.StandardButton.Ok)
        box.exec()
        if box.clickedButton() is copy_btn:
            QApplication.clipboard().setText(text)
            self.status_bar.showMessage("Diagnostics copied", 4000)

    def diagnostics_text(self) -> str:
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
            f"RDP client: {rdp_client_status()}",
            f"Git: {shutil.which('git') or 'not found'}",
            f"Open tabs: {self.tabs.count() if hasattr(self, 'tabs') else 0}",
        ]
        return "\n".join(lines)

    def copy_diagnostics(self):
        QApplication.clipboard().setText(self.diagnostics_text())
        self.status_bar.showMessage("Diagnostics copied", 4000)

    def show_about_dialog(self):
        QMessageBox.information(
            self,
            "About Bifrost",
            "Bifrost Connection Manager\n\n"
            "A desktop toolkit for SSH, SFTP, local tools, snippets, and workspaces.\n\n"
            "Author: Panagiotis Polychronis\n"
            "Email: panospolychronis@gmail.com",
        )

    def open_logs_folder(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(_log_path())))

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

    def import_ssh_config_sessions(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Import OpenSSH config", os.path.expanduser("~/.ssh/config"),
            "SSH config (config);;All files (*)",
        )
        if not path:
            return
        try:
            result = parse_ssh_config_file(path)
        except (OSError, ValueError) as e:
            QMessageBox.warning(self, "SSH config import failed", str(e))
            return
        if result.imported == 0:
            QMessageBox.information(
                self,
                "No sessions imported",
                "No concrete Host entries were found in that SSH config.",
            )
            return
        imported_group = ""
        for group_name, data in result.tree.items():
            imported_group = self.session_manager.import_group(group_name, data)
        self.sidebar.refresh_sessions()
        self._refresh_credentials_view()
        message = f"Imported {result.imported} SSH config session"
        if result.imported != 1:
            message += "s"
        message += f" into {imported_group}"
        if result.skipped:
            message += f" ({result.skipped} wildcard/skipped)"
        self.status_bar.showMessage(message, 6000)

    def show_dashboard(self):
        dashboard = Dashboard(recent_sessions=self.session_manager.recent_sessions)
        dashboard.session_requested.connect(self._dashboard_session_requested)
        dashboard.btn_ssh.clicked.connect(lambda: self.new_terminal_tab("Local Shell"))
        dashboard.btn_session.clicked.connect(self.open_session_dialog)
        # Sidebar tabs after moving credentials to the menu:
        # 0 Sessions, 1 SSH, 2 Servers, 3 Tools, 4 Macros.
        dashboard.btn_tools.clicked.connect(lambda: self.sidebar.tabs.setCurrentIndex(3))
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

    def run_snippet(self, text, execute=False):
        current_tab = self.tabs.currentWidget()
        if isinstance(current_tab, TerminalContainer) and text:
            term = current_tab.findChild(TerminalWidget)
            if term:
                text = self._expand_snippet(text)
                if execute and not text.endswith(("\n", "\r")):
                    text += "\r"
                term.write_to_backend(text)

    def _expand_snippet(self, text: str) -> str:
        current_tab = self.tabs.currentWidget()
        session = current_tab.ssh_session if isinstance(current_tab, TerminalContainer) else None
        return expand_snippet(text, session)

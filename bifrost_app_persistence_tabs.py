from bifrost_app_deps import *


class BifrostPersistenceTabsMixin:
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
                self.new_terminal_tab(
                    data["name"],
                    kind="WSL",
                    distro=data.get("distro") or None,
                    session_data=data,
                )
            elif data["type"] == "SSH":
                self.new_terminal_tab(data["name"], ssh_session=data)
            else:
                self.new_terminal_tab(data["name"], session_data=data)

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
        if hasattr(widget, "shutdown"):
            widget.shutdown()
        self.cluster_tabs.discard(widget)
        widget.deleteLater()
        self.tabs.removeTab(index)

    def close_current_tab(self):
        index = self.tabs.currentIndex()
        if index >= 0:
            self.close_tab(index)

    def disconnect_current_tab(self):
        index = self.tabs.currentIndex()
        if index >= 0:
            self._disconnect_tab(index)

    def reconnect_current_tab(self):
        index = self.tabs.currentIndex()
        if index >= 0:
            self._reconnect_tab(index)

    def attach_sftp_for_current_tab(self):
        index = self.tabs.currentIndex()
        if index >= 0:
            self._attach_sftp_for_tab(index)

    def forget_current_session_credentials(self):
        current = self.tabs.currentWidget()
        if not isinstance(current, TerminalContainer) or not current.ssh_session:
            self.status_bar.showMessage("Current tab has no saved SSH session", 4000)
            return
        self.on_forget_credentials(current.ssh_session)

    def _tab_is_live(self, widget) -> bool:
        """A tab is 'live' if it contains at least one terminal whose backend is still running."""
        if isinstance(widget, VncViewer):
            return widget.client.is_open()
        if not isinstance(widget, TerminalContainer):
            return False
        for term in widget.findChildren(TerminalWidget):
            backend = getattr(term, "backend", None)
            if backend is None:
                continue
            if isinstance(backend, ParamikoBackend):
                if backend.status in {"connecting", "connected"}:
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
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, "shutdown"):
                tab.shutdown()
            backend = self._ssh_backend_of(tab)
            if backend is not None:
                backend.close()
        if hasattr(self, "sidebar"):
            self.sidebar.sftp_widget.detach()
        super().closeEvent(event)

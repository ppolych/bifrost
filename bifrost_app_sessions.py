from bifrost_app_deps import *


class BifrostSessionsMixin:
    def on_tool_triggered(self, tool_name):
        run_tool(self, tool_name)

    def on_session_activated(self, session: dict):
        """Route a session opening by its explicit `type`, not by name sniffing."""
        name = session.get("name") or "Session"
        proto = session.get("type")
        if proto == "WSL":
            self.new_terminal_tab(name, kind="WSL", distro=session.get("distro") or None, session_data=session)
        elif proto == "SSH":
            self.new_terminal_tab(name, ssh_session=session)
        elif proto == "Telnet":
            port = session.get("port")
            self.new_terminal_tab(
                name,
                kind="Telnet",
                host=session.get("host") or "localhost",
                port=int(port) if str(port or "").isdigit() else 23,
                session_data=session,
            )
        elif proto == "Serial":
            baud = session.get("baudrate")
            self.new_terminal_tab(
                name,
                kind="Serial",
                device=session.get("device") or "",
                baud=int(baud) if str(baud or "").isdigit() else 115200,
                session_data=session,
            )
        elif proto == "VNC":
            self.open_vnc_session(session)
        elif proto == "RDP":
            self.open_rdp_session(session)
        elif proto == "Local":
            cmd = session.get("cmd")
            self.new_terminal_tab(
                name,
                command=[cmd] if isinstance(cmd, str) else cmd,
                session_data=session,
            )
        else:
            self.new_terminal_tab(name, session_data=session)

    def save_current_workspace(self):
        sessions = self._current_workspace_sessions()
        if not sessions:
            QMessageBox.information(
                self,
                "Save workspace",
                "There are no terminal sessions to save in this workspace.",
            )
            return
        name, ok = QInputDialog.getText(self, "Save workspace", "Workspace name:")
        if not ok or not name.strip():
            return
        try:
            self.workspace_manager.upsert(name, sessions, layout=self._current_workspace_layout())
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
        profile = self.workspace_manager.get_profile(name)
        sessions = profile.get("sessions", [])
        if not sessions:
            QMessageBox.warning(self, "Open workspace", "Workspace is empty or missing.")
            return
        if self.settings.get("confirm_workspace_reconnect", True):
            reply = QMessageBox.question(
                self,
                "Open workspace",
                f"Open {len(sessions)} remote session{'s' if len(sessions) != 1 else ''} from '{name}'?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        first_new_tab = self.tabs.count()
        for session in sessions:
            before = self.tabs.count()
            self.on_session_activated(session)
            # Restore cluster membership saved with the workspace. The new tab
            # (if one opened — the user may cancel a credential prompt) is
            # always appended last.
            if session.get("cluster") and self.tabs.count() > before:
                container = self.tabs.widget(self.tabs.count() - 1)
                if isinstance(container, TerminalContainer):
                    self.cluster_tabs.add(container)
        self._restore_workspace_layout(profile.get("layout") or {}, first_new_tab)
        self._refresh_multi_exec_ui()
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
                if widget.command is None:
                    continue
                session = {
                    "name": widget.name or "Local Shell",
                    "type": "Local",
                    "cmd": widget.command,
                }
            if session.get("type") == "SSH" or session.get("host") or session.get("type") == "Local":
                session["cluster"] = widget in self.cluster_tabs
                sessions.append(session)
        return sessions

    def _current_workspace_layout(self) -> dict:
        return {
            "main_splitter_sizes": self.splitter.sizes(),
            "sidebar_splitter_sizes": self.sidebar.content_splitter.sizes(),
            "last_sidebar_tab": self.sidebar.tabs.currentIndex(),
            "active_tab": self.tabs.currentIndex(),
        }

    def _restore_workspace_layout(self, layout: dict, first_new_tab: int) -> None:
        if not isinstance(layout, dict):
            return
        main_sizes = layout.get("main_splitter_sizes")
        if (
            isinstance(main_sizes, list)
            and len(main_sizes) == 2
            and all(isinstance(v, int) for v in main_sizes)
        ):
            self.splitter.setSizes(main_sizes)
        sidebar_sizes = layout.get("sidebar_splitter_sizes")
        if (
            isinstance(sidebar_sizes, list)
            and len(sidebar_sizes) == 2
            and all(isinstance(v, int) for v in sidebar_sizes)
        ):
            self.sidebar.content_splitter.setSizes(sidebar_sizes)
        try:
            sidebar_tab = int(layout.get("last_sidebar_tab", self.sidebar.tabs.currentIndex()))
        except (TypeError, ValueError):
            sidebar_tab = self.sidebar.tabs.currentIndex()
        if 0 <= sidebar_tab < self.sidebar.tabs.count():
            self.sidebar.tabs.setCurrentIndex(sidebar_tab)
        try:
            active_tab = int(layout.get("active_tab", -1))
        except (TypeError, ValueError):
            active_tab = -1
        if first_new_tab <= active_tab < self.tabs.count():
            self.tabs.setCurrentIndex(active_tab)

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
            self.new_terminal_tab(
                text or "telnet",
                kind="Telnet",
                host=host or "localhost",
                port=int(port) if port.isdigit() else 23,
            )
        elif method == "VNC":
            host, _, port = text.partition(":")
            self.open_vnc_session({
                "name": text,
                "host": host or "localhost",
                "port": port if port.isdigit() else 5900,
            })
        elif method == "RDP":
            host, _, port = text.partition(":")
            self.open_rdp_session({
                "name": text,
                "type": "RDP",
                "host": host or "localhost",
                "port": port if port.isdigit() else 3389,
            })
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

from bifrost_app_deps import *


class BifrostSshStatusMixin:
    def on_tab_changed(self, index):
        # Keep the SSH browser pane in sync as tabs come and go.
        self._refresh_ssh_browser()
        if index < 0:
            self.remote_monitor.set_backend(None)
            self.sidebar.remote_ops_widget.set_backend(None)
            docker_widget = self.sidebar.docker_widget_if_loaded()
            if docker_widget is not None:
                docker_widget.set_ssh_context(None)
            return
        name = self.tabs.tabText(index)
        widget = self.tabs.widget(index)
        ssh_backend = self._ssh_backend_of(widget)
        self.remote_monitor.set_backend(ssh_backend)
        self.sidebar.remote_ops_widget.set_backend(ssh_backend)
        docker_session = widget.ssh_session if isinstance(widget, TerminalContainer) else None
        docker_widget = self.sidebar.docker_widget_if_loaded()
        if docker_widget is not None:
            docker_widget.set_ssh_context(ssh_backend, docker_session)

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
            self.sidebar.tabs.setCurrentIndex(2)

    def _on_sidebar_tab_changed(self, index):
        if index != 6:
            return
        docker_widget = self.sidebar.docker_widget_if_loaded()
        if docker_widget is None:
            return
        widget = self.tabs.currentWidget()
        ssh_backend = self._ssh_backend_of(widget)
        docker_session = widget.ssh_session if isinstance(widget, TerminalContainer) else None
        docker_widget.set_ssh_context(ssh_backend, docker_session)

    def _refresh_open_session_indicators(self):
        open_ids = {
            session_id for i in range(self.tabs.count())
            if (session_id := getattr(self.tabs.widget(i), "source_session_id", None)) is not None
        }
        for window in list(getattr(self, "detached_windows", [])):
            if window is None:
                continue
            for i in range(window.tabs.count()):
                session_id = getattr(window.tabs.widget(i), "source_session_id", None)
                if session_id is not None:
                    open_ids.add(session_id)
        self.sidebar.set_open_session_ids(open_ids)

    def _refresh_ssh_browser(self):
        from widgets.ssh_browser import ActiveConnection

        connections: list[ActiveConnection] = []
        for i in range(self.tabs.count()):
            backend = self._ssh_backend_of(self.tabs.widget(i))
            if backend is None:
                continue
            status = backend.status
            connections.append(ActiveConnection(
                tab_index=i,
                host=backend.creds.host,
                user=backend.creds.username,
                port=backend.creds.port,
                status=status,
                tunnels=backend.tunnel_statuses(),
                error=str(backend.connect_error or ""),
            ))
        self.sidebar.ssh_browser.update_from_tabs(connections)
        self._update_ssh_tab_indicators()

    def _update_ssh_tab_indicators(self):
        status_prefix = {
            "connecting": "[...] ",
            "disconnected": "[down] ",
            "closed": "[closed] ",
            "failed": "[failed] ",
            "auth failed": "[auth] ",
            "host-key failed": "[key] ",
        }
        known_prefixes = tuple(status_prefix.values())
        for i in range(self.tabs.count()):
            widget = self.tabs.widget(i)
            backend = self._ssh_backend_of(widget)
            if backend is None:
                continue
            text = self.tabs.tabText(i)
            base = text
            for prefix in known_prefixes:
                if base.startswith(prefix):
                    base = base[len(prefix):]
                    break
            status = backend.status
            self.tabs.setTabText(i, status_prefix.get(status, "") + base)
            self.tabs.setTabToolTip(
                i,
                f"{backend.creds.username}@{backend.creds.host}:{backend.creds.port} - {status}",
            )

    def _refresh_credentials_view(self):
        """Walk the saved sessions tree and let the keyring view check what's stored."""
        view = getattr(self, "_credentials_view", None)
        if view is None:
            return
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
        view.set_sessions(sessions)

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
        new_backend = self._build_ssh_backend(session.get("name") or widget.name, session)
        if new_backend is None:
            return
        if backend is not None:
            backend.close()
        old_text = self.tabs.tabText(tab_index)
        # Carry cluster membership over to the replacement container (and drop
        # the dead widget from the set so it doesn't linger there).
        was_clustered = widget in self.cluster_tabs
        self.cluster_tabs.discard(widget)
        self.tabs.removeTab(tab_index)
        widget.shutdown()
        widget.deleteLater()
        container = TerminalContainer(
            session.get("name") or widget.name,
            None,
            self.on_terminal_key,
            settings=self.settings,
            backend=new_backend,
            ssh_session=session,
        )
        container.source_session_id = getattr(widget, "source_session_id", None)
        container.detach_requested.connect(self.detach_terminal)
        self.tabs.insertTab(tab_index, container, old_text)
        self.tabs.setCurrentIndex(tab_index)
        if was_clustered:
            self.cluster_tabs.add(container)
        if self.multi_exec_enabled:
            self._refresh_multi_exec_ui()
        self._refresh_ssh_browser()
        self._refresh_open_session_indicators()
        self.status_bar.showMessage(
            f"Reconnecting {session.get('user', '')}@{session.get('host', '')}", 4000,
        )

    def _reconnect_all_disconnected(self):
        targets: list[int] = []
        for i in range(self.tabs.count()):
            backend = self._ssh_backend_of(self.tabs.widget(i))
            if backend is not None and backend.reconnectable:
                targets.append(i)
        for index in reversed(targets):
            self._reconnect_tab(index)
        self.status_bar.showMessage(
            f"Reconnect requested for {len(targets)} SSH tab{'s' if len(targets) != 1 else ''}",
            4000,
        )

    def _stop_ssh_tunnel(self, tab_index: int, tunnel_index: int):
        if tab_index < 0 or tab_index >= self.tabs.count():
            return
        backend = self._ssh_backend_of(self.tabs.widget(tab_index))
        if backend is None:
            return
        if backend.stop_tunnel(tunnel_index):
            self._refresh_ssh_browser()
            self.status_bar.showMessage("SSH tunnel stopped", 4000)

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
            if backend.connect_error is not None:
                self.status_bar.showMessage(
                    f"SFTP unavailable: SSH connection failed ({backend.connect_error})",
                    6000,
                )
                return
            if backend.client is not None:
                docker_widget = self.sidebar.docker_widget_if_loaded()
                if docker_widget is not None:
                    docker_widget.set_ssh_context(
                        backend,
                        self.tabs.currentWidget().ssh_session
                        if isinstance(self.tabs.currentWidget(), TerminalContainer)
                        else None,
                    )
                self.sidebar.sftp_widget.attach(backend.client)
            return

        # Not ready yet — poll every 250 ms. The current-tab guard means we
        # stop polling if the user switches away.
        def poll():
            if self._ssh_backend_of(self.tabs.currentWidget()) is not backend:
                return  # user switched tabs; stop polling
            if backend.wait_ready(timeout=0):
                self._refresh_ssh_browser()
                if backend.connect_error is not None:
                    self.status_bar.showMessage(
                        f"SFTP unavailable: SSH connection failed ({backend.connect_error})",
                        6000,
                    )
                    return
                if backend.client is not None:
                    docker_widget = self.sidebar.docker_widget_if_loaded()
                    if docker_widget is not None:
                        docker_widget.set_ssh_context(
                            backend,
                            self.tabs.currentWidget().ssh_session
                            if isinstance(self.tabs.currentWidget(), TerminalContainer)
                            else None,
                        )
                    self.sidebar.sftp_widget.attach(backend.client)
                return
            QTimer.singleShot(250, poll)

        QTimer.singleShot(250, poll)

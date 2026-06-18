from bifrost_app_deps import *


class BifrostTerminalSessionsMixin:
    def new_terminal_tab(
        self,
        name="Local Shell",
        command=None,
        is_ssh=False,
        kind=None,
        distro=None,
        ssh_session: dict | None = None,
        session_data: dict | None = None,
        host=None,
        port=None,
        device=None,
        baud=None,
    ):
        backend = None
        session = None
        prefix = "🐚 "

        if kind == "WSL" or (kind is None and "WSL" in name):
            command = wsl.spawn_command(distro)
            prefix = "🐧 "
        elif kind == "Telnet":
            backend = TelnetBackend(host or "localhost", int(port or 23))
            prefix = "📡 "
        elif kind == "Serial":
            backend = SerialBackend(device or "", int(baud or 115200))
            prefix = "🔌 "
        elif ssh_session is not None or is_ssh:
            session = ssh_session or self.session_manager.find_by_name(name)
            backend = self._build_ssh_backend(name, session)
            if backend is None:
                return  # user cancelled the password prompt
            if session is None:
                session = self._session_from_backend(name, backend)
            prefix = "🌐 "
        elif isinstance(session_data, dict):
            session = session_data

        if name != "Local Shell":
            self.session_manager.add_to_recents(name)

        tab_settings = self._settings_for_session(session)
        container = TerminalContainer(
            name,
            command,
            self.on_terminal_key,
            settings=tab_settings,
            backend=backend,
            ssh_session=session if backend is not None else None,
        )
        container.source_session_id = id(session) if isinstance(session, dict) else None
        container.detach_requested.connect(self.detach_terminal)
        self.tabs.addTab(container, prefix + name)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)
        if isinstance(backend, ParamikoBackend) and self.auto_cluster_cb.isChecked():
            self.cluster_tabs.add(container)
        if self.multi_exec_enabled:
            self._refresh_multi_exec_ui()
        self._refresh_ssh_browser()
        self._refresh_open_session_indicators()

    def _settings_for_session(self, session: dict | None) -> dict:
        settings = dict(self.settings)
        overrides = session.get("overrides") if isinstance(session, dict) else None
        if not isinstance(overrides, dict):
            return settings
        scheme = overrides.get("scheme")
        if scheme:
            scheme_name = scheme if scheme in SCHEMES else DEFAULT_NAME
            apply_scheme(settings, scheme_name)
            settings["color_scheme"] = scheme_name
        font_override = overrides.get("font")
        if font_override:
            settings["font"] = _font_from_override(font_override, settings["font"])
        return settings

    def open_vnc_session(self, session: dict):
        """Open a VNC viewer tab. The password is prompted per-connect and
        never persisted (the server may not need one — blank means none)."""
        host = session.get("host") or "localhost"
        port_raw = session.get("port")
        port = int(port_raw) if str(port_raw or "").isdigit() else 5900
        password, _ = CredentialPrompt.ask(
            title=f"VNC password for {host}",
            prompt=f"Password for {host}:{port} (leave blank if the server has none):",
            remember_enabled=False,
            parent=self,
        )
        if password is None:
            return  # user cancelled
        name = session.get("name") or f"{host}:{port}"
        viewer = VncViewer(host, port, password or None, settings=self.settings)
        viewer.source_session_id = id(session) if isinstance(session, dict) else None
        self.tabs.addTab(viewer, "🖥 " + name)
        self.tabs.setCurrentIndex(self.tabs.count() - 1)
        self.session_manager.add_to_recents(name)
        self._refresh_open_session_indicators()

    def open_rdp_session(self, session: dict):
        name = session.get("name") or f"{session.get('host') or 'localhost'}:{session.get('port') or 3389}"
        try:
            command = getattr(sys.modules.get("bifrost_app"), "launch_rdp_session", launch_rdp_session)(session)
        except RdpLaunchError as e:
            QMessageBox.warning(self, "RDP launch failed", str(e))
            return
        self.session_manager.add_to_recents(name)
        self.status_bar.showMessage(f"Launched RDP session via {os.path.basename(command[0])}", 5000)

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
            "certificate_path": creds.certificate_filename,
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
            if not creds.key_filename:
                key_path, _ = QFileDialog.getOpenFileName(
                    self,
                    "Select SSH private key",
                    os.path.expanduser("~/.ssh"),
                    "Private keys (*)",
                )
                if not key_path:
                    QMessageBox.warning(
                        self,
                        "SSH key required",
                        "This session is configured for private-key authentication, but no key file is set.",
                    )
                    return None
                creds.key_filename = key_path
                session["key_path"] = key_path
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
            # Drop the container from this window's cluster/pin sets — it now
            # lives in another window, so a lingering reference here is stale.
            self.cluster_tabs.discard(container)
            self.pinned_tabs.discard(container)
            self.tabs.removeTab(index)
            new_win = BifrostApp(is_detached=True, settings=self.settings)
            new_win.setWindowTitle(f"Detached: {name}")
            new_win.tabs.addTab(container, name)
            new_win.show()
            self.detached_windows.append(new_win)
            new_win.destroyed.connect(lambda *_: self._refresh_open_session_indicators())
            self._refresh_open_session_indicators()

    def on_split_requested(self, orientation):
        current = self.tabs.currentWidget()
        if isinstance(current, TerminalContainer): current.split(orientation)

    def on_terminal_key(self, key):
        if self.macro_engine.recording: self.macro_engine.record_key(key)
        sender = self.sender()
        if self.multi_exec_enabled:
            sent_to_sender = False
            for container in self._broadcast_containers():
                for term in container.findChildren(TerminalWidget):
                    term.write_to_backend(key)
                    if term is sender:
                        sent_to_sender = True
            # Typing in a tab outside the cluster still drives that tab.
            if isinstance(sender, TerminalWidget) and not sent_to_sender:
                sender.write_to_backend(key)
        else:
            if isinstance(sender, TerminalWidget): sender.write_to_backend(key)

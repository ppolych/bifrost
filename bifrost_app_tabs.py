from bifrost_app_deps import *


class BifrostTabsMixin:
    _TAB_POSITION_MAP = {
        "Top": QTabWidget.TabPosition.North,
        "Bottom": QTabWidget.TabPosition.South,
        "Left": QTabWidget.TabPosition.West,
        "Right": QTabWidget.TabPosition.East,
    }

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

    def broadcast_command(self):
        cmd = self.multi_exec_input.text() + "\r"
        if cmd:
            for container in self._broadcast_containers():
                for term in container.findChildren(TerminalWidget):
                    term.write_to_backend(cmd)
            self.multi_exec_input.clear()

    def on_multi_exec_toggled(self, enabled):
        self.multi_exec_enabled = enabled
        if enabled: self.multi_exec_bar.show()
        else: self.multi_exec_bar.hide()
        self._refresh_multi_exec_ui()

    def _multi_exec_scope_value(self) -> str:
        return self.multi_exec_scope.currentData() or "all"

    def _broadcast_containers(self) -> list[TerminalContainer]:
        """Tabs MultiExec currently targets: all of them, or just the cluster."""
        containers = [
            w for w in (self.tabs.widget(i) for i in range(self.tabs.count()))
            if isinstance(w, TerminalContainer)
        ]
        if self._multi_exec_scope_value() == "cluster":
            containers = [c for c in containers if c in self.cluster_tabs]
        return containers

    def _refresh_multi_exec_ui(self):
        """Sync the MultiExec bar label and per-terminal broadcast tint."""
        targets = self._broadcast_containers()
        if self._multi_exec_scope_value() == "cluster":
            self.multi_exec_label.setText(f"CLUSTER ({len(targets)}):")
            self.multi_exec_input.setPlaceholderText(
                "Type command to send to the cluster tabs..."
            )
        else:
            self.multi_exec_label.setText("ALL TERMINALS:")
            self.multi_exec_input.setPlaceholderText(
                "Type command to send to ALL active terminals..."
            )
        tinted = set(targets) if self.multi_exec_enabled else set()
        for i in range(self.tabs.count()):
            container = self.tabs.widget(i)
            if isinstance(container, TerminalContainer):
                on = container in tinted
                for term in container.findChildren(TerminalWidget):
                    term.set_broadcast_mode(on)

    def toggle_tab_cluster(self, index):
        widget = self.tabs.widget(index)
        if not isinstance(widget, TerminalContainer):
            return
        if widget in self.cluster_tabs:
            self.cluster_tabs.discard(widget)
            verb = "removed from"
        else:
            self.cluster_tabs.add(widget)
            verb = "added to"
        self.status_bar.showMessage(f"{self.tabs.tabText(index)} {verb} cluster", 4000)
        self._refresh_multi_exec_ui()

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
        if isinstance(widget, TerminalContainer):
            in_cluster = widget in self.cluster_tabs
            cluster_act = QAction(
                "Remove from cluster" if in_cluster else "Add to cluster", self
            )
            cluster_act.triggered.connect(lambda: self.toggle_tab_cluster(index))
            menu.addAction(cluster_act)
        if isinstance(widget, TerminalContainer) and widget.ssh_session:
            reconnect_act = QAction("Reconnect tab", self)
            reconnect_act.triggered.connect(lambda: self._reconnect_tab(index))
            menu.addAction(reconnect_act)
            reconnect_all_act = QAction("Reconnect all disconnected SSH tabs", self)
            reconnect_all_act.triggered.connect(self._reconnect_all_disconnected)
            menu.addAction(reconnect_all_act)
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

    def toggle_sftp_pane(self):
        sizes = self.sidebar.content_splitter.sizes()
        if len(sizes) == 2 and sizes[1] > 0:
            self.sidebar.hide_sftp_pane()
        else:
            self.sidebar.show_sftp_pane()

    def toggle_full_screen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

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
                idx = int(self.settings.get("last_sidebar_tab", 0) or 0)
                if idx < 0 or idx >= self.sidebar.tabs.count():
                    idx = 0
                self.sidebar.tabs.setCurrentIndex(idx)
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

    def apply_global_visuals(self):
        self.setWindowOpacity(self.settings["opacity"] / 100.0)
        self.setStyleSheet(get_theme_stylesheet(self.settings.get("theme")))
        if hasattr(self, "tabs"):
            pos = self._TAB_POSITION_MAP.get(
                self.settings.get("tab_position", "Top"),
                QTabWidget.TabPosition.North,
            )
            self.tabs.setTabPosition(pos)

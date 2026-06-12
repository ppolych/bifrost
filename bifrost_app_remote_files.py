from bifrost_app_deps import *


class BifrostRemoteFilesMixin:
    def open_container_terminal(self, name, command_or_session):
        if isinstance(command_or_session, dict):
            self.new_terminal_tab(name, ssh_session=command_or_session)
        else:
            self.new_terminal_tab(name, command=command_or_session)

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
        import tempfile

        sftp = self.sidebar.sftp_widget.sftp
        local_path: str | None = None
        remote_name = _remote_display_name(remote_path, "Editor")

        if sftp is not None:
            try:
                fd, local_path = tempfile.mkstemp(
                    prefix="bifrost-",
                    suffix=_safe_temp_suffix(remote_path),
                )
                os.close(fd)
                sftp.get(remote_path, local_path)
            except Exception as e:
                log.exception("Failed to fetch remote file %s", remote_path)
                local_path = None
                editor = MobaEditor()
                editor.set_content(f"# Failed to fetch {remote_path}:\n# {e}\n")
                self.tabs.addTab(editor, f"📝 {remote_name}")
                self.tabs.setCurrentIndex(self.tabs.count() - 1)
                return

        ext_cmd = (self.settings.get("default_editor_command") or "").strip()
        if ext_cmd and local_path:
            argv = _split_user_command(ext_cmd) + [local_path]
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
        self.tabs.addTab(editor, f"📝 {remote_name}")
        self.tabs.setCurrentIndex(self.tabs.count() - 1)

    def _download_remote_temp(self, remote_path: str) -> str | None:
        import tempfile

        sftp = self.sidebar.sftp_widget.sftp
        if sftp is None:
            return None
        fd, local_path = tempfile.mkstemp(
            prefix="bifrost-",
            suffix=_safe_temp_suffix(remote_path),
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
        argv = _split_user_command(command) + [local_path]
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
        self.tabs.addTab(editor, f"Editor: {_remote_display_name(remote_path, 'remote file')}")
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
            self.status_bar.showMessage(
                f"Opened {_remote_display_name(remote_path)} with system default",
                4000,
            )
        elif local_path:
            QMessageBox.warning(self, "Open with system default failed", local_path)

    def send_remote_path_to_terminal(self, remote_path: str):
        current_tab = self.tabs.currentWidget()
        if not isinstance(current_tab, TerminalContainer):
            return
        term = current_tab.findChild(TerminalWidget)
        if term is not None:
            term.write_to_backend(remote_path)

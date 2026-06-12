from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox

from widgets.session_dialog_ui import build_session_dialog_ui
from widgets.session_tags import parse_tags, tags_text
from widgets.tmux_commands import tmux_command
from widgets.tunnel_validation import validate_tunnel_lines


class SessionDialog(QDialog):
    def __init__(self, parent=None, session: dict | None = None):
        super().__init__(parent)
        self.setWindowTitle("Session Settings")
        self.resize(700, 500)

        build_session_dialog_ui(self)

        if session is not None:
            self._load_session(session)
        self._on_auth_changed(self.auth_method.currentText())
        self._validate_tunnels()

    def _pick_key_file(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select private key", "", "All Files (*)")
        if path:
            self.key_path_input.setText(path)

    def _pick_known_hosts(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select known_hosts file", self.known_hosts_input.text(), "All Files (*)"
        )
        if path:
            self.known_hosts_input.setText(path)

    def _pick_cert_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SSH certificate", "", "Public Certificates (*.pub);;All Files (*)"
        )
        if path:
            self.cert_path_input.setText(path)

    def set_current_section(self, section: str) -> None:
        section_map = {
            "connection": self.conn_tab,
            "advanced_ssh": self.advanced_ssh_tab,
            "terminal": self.term_tab,
            "network": self.network_tab,
        }
        page = section_map.get(section, self.conn_tab)
        idx = self.tabs.indexOf(page)
        if idx >= 0:
            self.tabs.setCurrentIndex(idx)

    def _on_auth_changed(self, label: str):
        is_key = label == "Private key"
        is_pwd = label == "Password"
        self.key_row.setEnabled(is_key)
        self.cert_row.setEnabled(is_key)
        self.passphrase_note.setVisible(is_key)
        self.password_note.setVisible(is_pwd)

    def _apply_tmux_preset(self, _index: int):
        preset = self.tmux_preset.currentData()
        if preset:
            self.command_input.setText(
                tmux_command(preset, self.name_input.text(), self.host_input.text())
            )
            self.tmux_preset.setCurrentIndex(0)

    def _auth_value(self) -> str:
        return {
            "SSH agent": "agent",
            "Private key": "key",
            "Password": "password",
        }.get(self.auth_method.currentText(), "agent")

    def _set_auth_value(self, value: str) -> None:
        labels = {
            "agent": "SSH agent",
            "key": "Private key",
            "password": "Password",
        }
        self.auth_method.setCurrentText(labels.get(value, "SSH agent"))

    def _base_data(self, name: str, proto: str, overrides: dict) -> dict:
        data = {"name": name, "type": proto, "overrides": overrides}
        tags = parse_tags(self.tags_input.text())
        if tags:
            data["tags"] = tags
        return data

    def _validate_tunnels(self) -> bool:
        _tunnels, message = validate_tunnel_lines(self.tunnels_input.toPlainText())
        ok = not message.startswith("Line ")
        self.tunnels_status.setText(message)
        self.tunnels_status.setProperty("error", not ok)
        self.tunnels_status.style().unpolish(self.tunnels_status)
        self.tunnels_status.style().polish(self.tunnels_status)
        return ok

    def _accept_if_valid(self) -> None:
        if not self._validate_tunnels():
            self.tabs.setCurrentWidget(self.advanced_ssh_tab)
            QMessageBox.warning(self, "Invalid SSH tunnel", self.tunnels_status.text())
            return
        self.accept()

    def _load_session(self, session: dict) -> None:
        self.name_input.setText(session.get("name", ""))
        self.tags_input.setText(tags_text(session.get("tags")))
        proto = session.get("type", "SSH")
        tab = {
            "SSH": self.ssh_tab,
            "Telnet": self.telnet_tab,
            "Serial": self.serial_tab,
            "VNC": self.vnc_tab,
            "RDP": self.rdp_tab,
            "WSL": self.wsl_tab,
        }.get(proto, self.ssh_tab)
        idx = self.proto_tabs.indexOf(tab)
        if idx >= 0:
            self.proto_tabs.setCurrentIndex(idx)
        self.host_input.setText(session.get("host", "127.0.0.1"))
        self.user_input.setText(session.get("user", "root"))
        self.port_input.setText(str(session.get("port", "22") or "22"))
        self._set_auth_value(session.get("auth", "agent"))
        self.key_path_input.setText(session.get("key_path") or "")
        self.cert_path_input.setText(session.get("certificate_path") or "")
        self.command_input.setText(session.get("command") or "")
        self.mac_input.setText(session.get("mac") or "")
        self.broadcast_input.setText(session.get("wol_broadcast") or "")
        if "connect_timeout" in session:
            self.connect_timeout_sb.setValue(float(session.get("connect_timeout") or 15))
        self.agent_forwarding_cb.setChecked(bool(session.get("agent_forwarding", False)))
        self.keepalive_sb.setValue(int(session.get("keepalive_interval", 30) or 0))
        self.tcp_keepalive_cb.setChecked(bool(session.get("tcp_keepalive", True)))
        self.known_hosts_input.setText(session.get("known_hosts_file") or "")
        self.tunnels_input.setPlainText("\n".join(session.get("tunnels") or []))
        self.proxy_jump_input.setText(session.get("proxy_jump") or "")
        self.proxy_command_input.setText(session.get("proxy_command") or "")
        if proto == "Telnet":
            self.telnet_host_input.setText(session.get("host", "127.0.0.1"))
            self.telnet_port_input.setText(str(session.get("port", "23") or "23"))
        if proto == "Serial":
            self.serial_device_input.setText(session.get("device") or "")
            self.serial_baud_combo.setCurrentText(str(session.get("baudrate", "115200") or "115200"))
        if proto == "VNC":
            self.vnc_host_input.setText(session.get("host", "127.0.0.1"))
            self.vnc_port_input.setText(str(session.get("port", "5900") or "5900"))
        if proto == "RDP":
            self.rdp_host_input.setText(session.get("host", "127.0.0.1"))
            self.rdp_port_input.setText(str(session.get("port", "3389") or "3389"))
        if proto == "WSL":
            distro = session.get("distro") or "(default)"
            idx = self.wsl_distro.findText(distro)
            if idx >= 0:
                self.wsl_distro.setCurrentIndex(idx)
        overrides = session.get("overrides") or {}
        if overrides.get("font"):
            self.font_override_cb.setChecked(True)
            self.font_input.setText(overrides["font"])
        if overrides.get("scheme"):
            self.color_scheme.setCurrentText(overrides["scheme"])

    def get_data(self):
        proto = self.proto_tabs.tabText(self.proto_tabs.currentIndex())
        overrides = {
            "font": self.font_input.text() if self.font_override_cb.isChecked() else None,
            "scheme": self.color_scheme.currentText(),
        }
        if proto == "WSL":
            distro = self.wsl_distro.currentText()
            distro_label = "" if distro == "(default)" else distro
            name = self.name_input.text().strip() or f"WSL: {distro_label or 'default'}"
            data = self._base_data(name, "WSL", overrides)
            data["distro"] = distro_label
            return data
        if proto == "Telnet":
            host = self.telnet_host_input.text().strip() or "127.0.0.1"
            port = self.telnet_port_input.text().strip() or "23"
            name = self.name_input.text().strip() or f"telnet {host}:{port}"
            data = self._base_data(name, "Telnet", overrides)
            data.update({"host": host, "port": port})
            return data
        if proto == "VNC":
            host = self.vnc_host_input.text().strip() or "127.0.0.1"
            port = self.vnc_port_input.text().strip() or "5900"
            name = self.name_input.text().strip() or f"vnc {host}:{port}"
            data = self._base_data(name, "VNC", overrides)
            data.update({"host": host, "port": port})
            return data
        if proto == "RDP":
            host = self.rdp_host_input.text().strip() or "127.0.0.1"
            port = self.rdp_port_input.text().strip() or "3389"
            name = self.name_input.text().strip() or f"rdp {host}:{port}"
            data = self._base_data(name, "RDP", overrides)
            data.update({"host": host, "port": port})
            return data
        if proto == "Serial":
            device = self.serial_device_input.text().strip()
            baud = self.serial_baud_combo.currentText()
            name = self.name_input.text().strip() or f"{device or 'serial'} @{baud}"
            data = self._base_data(name, "Serial", overrides)
            data.update({"device": device, "baudrate": baud})
            return data
        if proto == "SSH":
            generated_name = f"{self.user_input.text()}@{self.host_input.text()}"
            name = self.name_input.text().strip() or generated_name
            data = self._base_data(name, "SSH", overrides)
            data.update({
                "host": self.host_input.text(),
                "user": self.user_input.text(),
                "port": self.port_input.text(),
                "auth": self._auth_value(),
                "key_path": self.key_path_input.text().strip() or None,
                "certificate_path": self.cert_path_input.text().strip() or None,
                "command": self.command_input.text().strip() or None,
                "connect_timeout": self.connect_timeout_sb.value(),
                "agent_forwarding": self.agent_forwarding_cb.isChecked(),
                "keepalive_interval": self.keepalive_sb.value(),
                "tcp_keepalive": self.tcp_keepalive_cb.isChecked(),
                "known_hosts_file": self.known_hosts_input.text().strip() or None,
                "proxy_jump": self.proxy_jump_input.text().strip() or None,
                "proxy_command": self.proxy_command_input.text().strip() or None,
                "tunnels": validate_tunnel_lines(self.tunnels_input.toPlainText())[0],
                "mac": self.mac_input.text().strip() or None,
                "wol_broadcast": self.broadcast_input.text().strip() or None,
            })
            return data
        name = self.name_input.text().strip() or f"{self.host_input.text()} ({self.user_input.text()})"
        data = self._base_data(name, proto, overrides)
        data.update({
            "host": self.host_input.text(),
            "user": self.user_input.text(),
            "port": self.port_input.text(),
        })
        return data

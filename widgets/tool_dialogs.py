"""Sidebar/menu utility-tool dialogs (port scan, network scan, IP calc, keygen).

Moved out of bifrost_app.py verbatim: `run_tool(window, tool_name)` is the
dispatch target for the sidebar's tool_triggered signal and the Tools menu.
"""

import os

from PyQt6.QtWidgets import QFileDialog, QInputDialog, QLineEdit, QMessageBox

from core import credentials, ip_tools, keygen
from core.network_tools import scan_ports, scan_ip_range


def run_tool(window, tool_name: str) -> None:
    if tool_name == "Port Scanner":
        host, ok = QInputDialog.getText(window, "Port Scanner", "Host:", QLineEdit.EchoMode.Normal, "127.0.0.1")
        if ok and host:
            open_ports = scan_ports(host, 1, 100)
            QMessageBox.information(window, "Scan Results", f"Open ports: {open_ports}")
    elif tool_name == "Network Scanner":
        base, ok = QInputDialog.getText(window, "Network Scanner", "IP Subnet:", QLineEdit.EchoMode.Normal, "127.0.0")
        if ok and base:
            active = scan_ip_range(base)
            QMessageBox.information(window, "Network Scan", f"Active hosts found:\n{active}")
    elif tool_name == "IP Calculator":
        cidr, ok = QInputDialog.getText(
            window, "IP Calculator",
            "CIDR (e.g. 10.0.0.0/24 or 192.168.1.5):",
            QLineEdit.EchoMode.Normal, "10.0.0.0/24",
        )
        if not ok or not cidr.strip():
            return
        try:
            info = ip_tools.calculate(cidr)
        except ValueError as e:
            QMessageBox.warning(window, "IP Calculator", str(e))
            return
        lines = "\n".join(f"{k:<14} {v}" for k, v in info.items())
        QMessageBox.information(window, f"IP Calculator — {cidr}", lines)
    elif tool_name == "SSH Key Gen":
        run_ssh_keygen(window)


def run_ssh_keygen(window) -> None:
    default = os.path.expanduser("~/.ssh/id_ed25519")
    path, _ = QFileDialog.getSaveFileName(
        window, "Generate SSH key — choose output file", default,
    )
    if not path:
        return
    passphrase, ok = QInputDialog.getText(
        window, "Key passphrase",
        "Passphrase (empty = unencrypted; keyring opt-in is on next prompt):",
        QLineEdit.EchoMode.Password,
    )
    if not ok:
        return
    try:
        priv, pub = keygen.generate_keypair(path, algorithm="ed25519", passphrase=passphrase or None)
    except FileExistsError as e:
        QMessageBox.warning(window, "Key Gen", str(e))
        return
    except (OSError, ValueError) as e:
        QMessageBox.warning(window, "Key Gen failed", str(e))
        return
    if passphrase and credentials.is_available():
        reply = QMessageBox.question(
            window, "Store passphrase?",
            f"Save the passphrase for {priv} in the system keyring?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            credentials.set_passphrase(priv, passphrase)
    QMessageBox.information(
        window, "Key Gen",
        f"Generated:\n• {priv}\n• {pub}\n\n"
        "Copy the .pub line into the remote host's ~/.ssh/authorized_keys.",
    )

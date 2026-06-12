import socket
import subprocess
import sys


def scan_ports(host, start_port=1, end_port=100):
    open_ports = []
    try:
        start_port = max(1, int(start_port))
        end_port = min(65535, int(end_port))
    except (TypeError, ValueError):
        return open_ports
    if start_port > end_port:
        return open_ports
    for port in range(start_port, end_port + 1):
        try:
            with socket.create_connection((host, port), timeout=0.05):
                open_ports.append(port)
        except OSError:
            continue
    return open_ports


def _ping_command(ip: str) -> list[str]:
    if sys.platform == "win32":
        return ["ping", "-n", "1", "-w", "1000", ip]
    if sys.platform == "darwin":
        return ["ping", "-c", "1", "-t", "1", ip]
    return ["ping", "-c", "1", "-W", "1", ip]


def scan_ip_range(base_ip):
    """Quick host-discovery sweep over base_ip.1 – base_ip.20 (prototype)."""
    active_hosts = []
    for i in range(1, 21):
        ip = f"{base_ip}.{i}"
        try:
            if subprocess.call(
                _ping_command(ip),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            ) == 0:
                active_hosts.append(ip)
        except OSError:
            pass
    return active_hosts

import logging
import socket

import paramiko

from core.ssh_credentials import SshCredentials

log = logging.getLogger(__name__)


def apply_transport_keepalives(client: paramiko.SSHClient, creds: SshCredentials) -> None:
    if creds.keepalive_interval and creds.keepalive_interval > 0:
        try:
            transport = client.get_transport()
            if transport is not None:
                transport.set_keepalive(int(creds.keepalive_interval))
        except Exception:
            log.debug("set_keepalive failed", exc_info=True)

    if not creds.tcp_keepalive:
        return
    try:
        transport = client.get_transport()
        sock = transport.sock if transport is not None else None
        if sock is not None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            if hasattr(socket, "TCP_KEEPIDLE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, 60)
            elif hasattr(socket, "TCP_KEEPALIVE"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPALIVE, 60)
            if hasattr(socket, "TCP_KEEPINTVL"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPINTVL, 30)
            if hasattr(socket, "TCP_KEEPCNT"):
                sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_KEEPCNT, 5)
    except Exception:
        log.debug("SO_KEEPALIVE setup failed", exc_info=True)

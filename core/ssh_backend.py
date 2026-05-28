"""SSH terminal backend powered by paramiko.

Same public surface as `core.terminal_backend.TerminalBackend` so `TerminalReader`
and `TerminalWidget` can use either interchangeably.

Connection lifecycle:
- start() spawns a worker thread that runs the connect + invoke_shell, then
  signals readiness via a threading.Event. read() blocks on the channel.
- A connect failure is converted to a one-shot byte string that read() returns,
  so the terminal renders the error to the user instead of silently dying.
- close() shuts the channel + client, which unblocks any in-flight recv().
"""

from __future__ import annotations

import logging
import os
import socket
import threading
from dataclasses import dataclass, field
from typing import Optional

import paramiko

log = logging.getLogger(__name__)


@dataclass
class SshCredentials:
    host: str
    port: int = 22
    username: str = ""
    # auth: "password" | "key" | "agent"
    auth: str = "agent"
    password: Optional[str] = None        # never persisted; supplied at connect-time
    key_filename: Optional[str] = None
    passphrase: Optional[str] = None      # never persisted; supplied at connect-time
    connect_timeout: float = 15.0
    agent_forwarding: bool = False
    keepalive_interval: int = 0   # seconds; 0 disables
    tcp_keepalive: bool = False   # SO_KEEPALIVE on the underlying socket
    known_hosts_file: Optional[str] = None
    startup_command: str = ""
    tunnels: list[str] = field(default_factory=list)
    extra_kwargs: dict = field(default_factory=dict)

    @classmethod
    def from_session(cls, data: dict) -> "SshCredentials":
        """Build credentials from a session dict (sessions.json shape)."""
        return cls(
            host=data.get("host", ""),
            port=int(data.get("port", 22) or 22),
            username=data.get("user", "") or "",
            auth=data.get("auth", "agent"),
            key_filename=data.get("key_path") or None,
            connect_timeout=float(data.get("connect_timeout", 15) or 15),
            agent_forwarding=bool(data.get("agent_forwarding", False)),
            keepalive_interval=int(data.get("keepalive_interval", 0) or 0),
            tcp_keepalive=bool(data.get("tcp_keepalive", False)),
            known_hosts_file=data.get("known_hosts_file") or None,
            startup_command=data.get("command") or "",
            tunnels=list(data.get("tunnels") or []),
        )


class ParamikoBackend:
    """SSH backend with the same surface as TerminalBackend."""

    def __init__(
        self,
        creds: SshCredentials,
        term: str = "xterm-256color",
        host_key_policy: Optional["paramiko.MissingHostKeyPolicy"] = None,
    ):
        self.creds = creds
        self.term = term
        # Caller may inject a QtHostKeyPolicy bound to a HostKeyPrompter so the
        # GUI can prompt on first-sight hosts. When None we fall back to the
        # auto-add policy used by the original implementation.
        self.host_key_policy = host_key_policy
        self.client: Optional[paramiko.SSHClient] = None
        self.channel: Optional[paramiko.Channel] = None

        self._ready = threading.Event()
        self._connect_error: Optional[BaseException] = None
        self._error_emitted = False
        self._closed = False
        self._pending_winsize = (24, 80)
        self._connect_thread: Optional[threading.Thread] = None

    # ----- lifecycle -----

    def start(self):
        self._connect_thread = threading.Thread(
            target=self._connect, name="ssh-connect", daemon=True
        )
        self._connect_thread.start()

    def _connect(self):
        try:
            client = paramiko.SSHClient()
            # System host keys are read-only on disk; we also load the user's
            # ~/.ssh/known_hosts into the writable store so save_host_keys()
            # later preserves existing entries instead of nuking them.
            try:
                client.load_system_host_keys()
            except (OSError, paramiko.SSHException):
                log.debug("could not load system host keys", exc_info=True)
            user_known_hosts = os.path.expanduser(
                self.creds.known_hosts_file or "~/.ssh/known_hosts"
            )
            try:
                if os.path.exists(user_known_hosts):
                    client.load_host_keys(user_known_hosts)
            except (OSError, paramiko.SSHException):
                log.debug("could not load user host keys", exc_info=True)

            client.set_missing_host_key_policy(
                self.host_key_policy or paramiko.AutoAddPolicy()
            )

            kwargs = dict(
                hostname=self.creds.host,
                port=self.creds.port,
                username=self.creds.username or None,
                timeout=self.creds.connect_timeout,
                banner_timeout=self.creds.connect_timeout,
                auth_timeout=self.creds.connect_timeout,
                look_for_keys=False,
                allow_agent=False,
            )

            if self.creds.auth == "password":
                kwargs["password"] = self.creds.password or ""
            elif self.creds.auth == "key":
                if not self.creds.key_filename:
                    raise paramiko.SSHException("Key authentication selected but no key file provided")
                kwargs["key_filename"] = os.path.expanduser(self.creds.key_filename)
                if self.creds.passphrase:
                    kwargs["passphrase"] = self.creds.passphrase
            elif self.creds.auth == "agent":
                kwargs["allow_agent"] = True
                kwargs["look_for_keys"] = True
            else:
                raise paramiko.SSHException(f"Unknown auth method: {self.creds.auth!r}")

            kwargs.update(self.creds.extra_kwargs)
            client.connect(**kwargs)

            # Keepalive on the transport — keeps NAT/load-balancer paths warm
            # and notices half-closed connections faster.
            if self.creds.keepalive_interval and self.creds.keepalive_interval > 0:
                try:
                    transport = client.get_transport()
                    if transport is not None:
                        transport.set_keepalive(int(self.creds.keepalive_interval))
                except Exception:
                    log.debug("set_keepalive failed", exc_info=True)

            # Kernel-level TCP keepalive backstops the SSH-layer ping for NAT
            # boxes that ignore application traffic. Default OS keepalive_time
            # is 2h on Linux/Windows, so we tune the timers where the platform
            # exposes them.
            if self.creds.tcp_keepalive:
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

            rows, cols = self._pending_winsize
            channel = client.invoke_shell(term=self.term, width=cols, height=rows)
            channel.settimeout(None)
            if self.creds.startup_command:
                command = self.creds.startup_command.rstrip("\r\n") + "\n"
                channel.send(command)

            # Optional agent forwarding for the opened shell channel.
            if self.creds.agent_forwarding:
                try:
                    paramiko.agent.AgentRequestHandler(channel)
                except Exception:
                    log.warning("agent forwarding failed", exc_info=True)

            self.client = client
            self.channel = channel
        except BaseException as e:
            log.warning("SSH connect to %s@%s:%s failed: %s",
                        self.creds.username, self.creds.host, self.creds.port, e)
            self._connect_error = e
            # Best-effort cleanup of partial state.
            try:
                if self.client is not None:
                    self.client.close()
            except Exception:
                pass
        finally:
            self._ready.set()

    # ----- io -----

    def read(self, size: int = 4096) -> bytes:
        if self._closed:
            return b""

        if not self._ready.is_set():
            # On the very first call, surface a connecting hint so the user
            # knows the terminal isn't frozen.
            self._ready.wait(timeout=0.25)
            if not self._ready.is_set():
                return f"Connecting to {self.creds.username}@{self.creds.host}:{self.creds.port}...\r\n".encode()

        if self._connect_error is not None and not self._error_emitted:
            self._error_emitted = True
            return f"\r\n\x1b[31m[connection failed: {self._connect_error}]\x1b[0m\r\n".encode()

        if self.channel is None:
            return b""

        try:
            data = self.channel.recv(size)
        except (OSError, paramiko.SSHException) as e:
            log.debug("ssh recv failed: %s", e)
            return b""

        if not data:
            return b""
        return data

    def write(self, data) -> None:
        if self._closed or self.channel is None:
            return
        if isinstance(data, str):
            data = data.encode()
        try:
            self.channel.send(data)
        except (OSError, paramiko.SSHException):
            log.debug("ssh send failed", exc_info=True)

    def set_winsize(self, rows: int, cols: int) -> None:
        self._pending_winsize = (rows, cols)
        if self.channel is None:
            return
        try:
            self.channel.resize_pty(width=cols, height=rows)
        except (OSError, paramiko.SSHException):
            log.debug("resize_pty failed", exc_info=True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            if self.channel is not None:
                self.channel.close()
        except Exception:
            log.debug("channel close failed", exc_info=True)
        try:
            if self.client is not None:
                self.client.close()
        except Exception:
            log.debug("client close failed", exc_info=True)

    # ----- accessors for SFTP attachment -----

    def wait_ready(self, timeout: float = 30.0) -> bool:
        return self._ready.wait(timeout=timeout)

    @property
    def connect_error(self) -> Optional[BaseException]:
        return self._connect_error

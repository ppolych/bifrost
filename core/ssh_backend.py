"""SSH terminal backend powered by paramiko."""

from __future__ import annotations

import logging
import os
import threading
from typing import Optional

import paramiko

from core.ssh_credentials import SshCredentials
from core.ssh_keepalive import apply_transport_keepalives
from core.ssh_proxy import (
    load_private_key_with_certificate, parse_proxy_jump, proxy_socket,
)
from core.ssh_tunnels import (
    BaseForwarder as _BaseForwarder,
    DynamicSocksForwarder,
    LocalPortForwarder,
    RemotePortForwarder,
    TunnelSpec,
    parse_tunnel_spec,
    start_tunnels,
)

log = logging.getLogger(__name__)



class ParamikoBackend:
    def __init__(
        self,
        creds: SshCredentials,
        term: str = "xterm-256color",
        host_key_policy: Optional["paramiko.MissingHostKeyPolicy"] = None,
    ):
        self.creds = creds
        self.term = term
        self.host_key_policy = host_key_policy
        self.client: Optional[paramiko.SSHClient] = None
        self.channel: Optional[paramiko.Channel] = None

        self._ready = threading.Event()
        self._connect_error: Optional[BaseException] = None
        self._error_emitted = False
        self._closed = False
        self._pending_winsize = (24, 80)
        self._connect_thread: Optional[threading.Thread] = None
        self._forwarders: list[_BaseForwarder] = []

    # ----- lifecycle -----

    def start(self):
        self._connect_thread = threading.Thread(
            target=self._connect, name="ssh-connect", daemon=True
        )
        self._connect_thread.start()

    def _connect(self):
        try:
            client = paramiko.SSHClient()
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
                if self.creds.certificate_filename:
                    kwargs["pkey"] = self._load_private_key_with_certificate()
                else:
                    kwargs["key_filename"] = [os.path.expanduser(self.creds.key_filename)]
                if self.creds.passphrase:
                    kwargs["passphrase"] = self.creds.passphrase
            elif self.creds.auth == "agent":
                kwargs["allow_agent"] = True
                kwargs["look_for_keys"] = True
            else:
                raise paramiko.SSHException(f"Unknown auth method: {self.creds.auth!r}")

            kwargs.update(self.creds.extra_kwargs)
            proxy_sock = self._proxy_socket()
            if proxy_sock is not None:
                kwargs["sock"] = proxy_sock
            client.connect(**kwargs)
            self._start_tunnels(client)
            apply_transport_keepalives(client, self.creds)

            rows, cols = self._pending_winsize
            channel = client.invoke_shell(term=self.term, width=cols, height=rows)
            channel.settimeout(None)
            if self.creds.startup_command:
                command = self.creds.startup_command.rstrip("\r\n") + "\n"
                channel.send(command)

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

    def exec_command_text(self, command: str, timeout: float = 10.0) -> tuple[int, str, str]:
        if self.client is None or self.status != "connected":
            raise paramiko.SSHException("SSH session is not connected")
        stdin, stdout, stderr = self.client.exec_command(command, timeout=timeout)
        try:
            stdin.close()
        except Exception:
            pass
        exit_code = stdout.channel.recv_exit_status()
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        return exit_code, out, err

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for forwarder in list(self._forwarders):
            forwarder.stop()
        self._forwarders.clear()
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

    @property
    def status(self) -> str:
        if self._closed:
            return "closed"
        if self._connect_error is not None:
            if isinstance(self._connect_error, paramiko.AuthenticationException):
                return "auth failed"
            if isinstance(self._connect_error, paramiko.BadHostKeyException):
                return "host-key failed"
            message = str(self._connect_error).lower()
            if "host key" in message:
                return "host-key failed"
            return "failed"
        if not self._ready.is_set():
            return "connecting"
        if self.channel is None:
            return "disconnected"
        if getattr(self.channel, "closed", False):
            return "disconnected"
        transport = self.client.get_transport() if self.client is not None else None
        if transport is not None and not transport.is_active():
            return "disconnected"
        return "connected"

    @property
    def reconnectable(self) -> bool:
        return self.status in {"closed", "disconnected", "failed", "auth failed", "host-key failed"}

    def _proxy_socket(self):
        return proxy_socket(self.creds)

    def _load_private_key_with_certificate(self) -> paramiko.PKey:
        return load_private_key_with_certificate(self.creds)

    @staticmethod
    def _parse_proxy_jump(value: str) -> tuple[str, str, int] | None:
        return parse_proxy_jump(value)

    def _start_tunnels(self, client: paramiko.SSHClient) -> None:
        self._forwarders.extend(start_tunnels(client.get_transport(), self.creds.tunnels))

    @property
    def tunnel_count(self) -> int:
        return len(self._forwarders)

    def tunnel_statuses(self) -> list[dict]:
        return [
            {
                "index": i,
                "label": forwarder.spec.label,
                "active": forwarder.active,
            }
            for i, forwarder in enumerate(self._forwarders)
        ]

    def stop_tunnel(self, index: int) -> bool:
        if index < 0 or index >= len(self._forwarders):
            return False
        self._forwarders[index].stop()
        return True

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
import select
import shlex
import socket
import threading
from dataclasses import dataclass, field
from typing import Optional

import paramiko

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class TunnelSpec:
    kind: str
    bind_host: str
    bind_port: int
    target_host: str = ""
    target_port: int = 0
    raw: str = ""

    @property
    def label(self) -> str:
        if self.kind == "D":
            return f"D {self.bind_host}:{self.bind_port}"
        return f"{self.kind} {self.bind_host}:{self.bind_port} {self.target_host}:{self.target_port}"


def parse_tunnel_spec(line: str) -> TunnelSpec:
    raw = (line or "").strip()
    parts = raw.split()
    if len(parts) not in (2, 3):
        raise ValueError(f"Invalid tunnel: {line!r}")
    kind = parts[0].upper()
    if kind not in {"L", "R", "D"}:
        raise ValueError(f"Unsupported tunnel type: {parts[0]!r}")
    bind_host, bind_port = _parse_host_port(parts[1], default_host="127.0.0.1")
    if kind == "D":
        if len(parts) != 2:
            raise ValueError("Dynamic tunnels only accept a bind address")
        return TunnelSpec(kind, bind_host, bind_port, raw=raw)
    if len(parts) != 3:
        raise ValueError(f"{kind} tunnels require a target address")
    target_host, target_port = _parse_host_port(parts[2], default_host="")
    if not target_host:
        raise ValueError(f"{kind} tunnel target host is required")
    return TunnelSpec(kind, bind_host, bind_port, target_host, target_port, raw=raw)


def _parse_host_port(value: str, *, default_host: str) -> tuple[str, int]:
    host, sep, port_text = value.rpartition(":")
    if not sep:
        host = default_host
        port_text = value
    if not host:
        host = default_host
    try:
        port = int(port_text)
    except (TypeError, ValueError) as e:
        raise ValueError(f"Invalid port in {value!r}") from e
    if port < 1 or port > 65535:
        raise ValueError(f"Port out of range in {value!r}")
    return host, port


def _bridge(left, right, stop_event: threading.Event) -> None:
    try:
        while not stop_event.is_set():
            readable, _, _ = select.select([left, right], [], [], 0.5)
            if left in readable:
                data = left.recv(32768)
                if not data:
                    break
                right.sendall(data)
            if right in readable:
                data = right.recv(32768)
                if not data:
                    break
                left.sendall(data)
    except (OSError, EOFError, paramiko.SSHException):
        log.debug("tunnel bridge stopped", exc_info=True)
    finally:
        for endpoint in (left, right):
            try:
                endpoint.close()
            except Exception:
                pass


class _BaseForwarder:
    def __init__(self, transport: paramiko.Transport, spec: TunnelSpec):
        self.transport = transport
        self.spec = spec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def stop(self) -> None:
        self._stop.set()


class LocalPortForwarder(_BaseForwarder):
    def __init__(self, transport: paramiko.Transport, spec: TunnelSpec):
        super().__init__(transport, spec)
        self._listener: socket.socket | None = None

    def start(self) -> None:
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind((self.spec.bind_host, self.spec.bind_port))
        listener.listen(50)
        listener.settimeout(0.5)
        self._listener = listener
        self._thread = threading.Thread(
            target=self._serve, name=f"ssh-local-forward-{self.spec.bind_port}", daemon=True
        )
        self._thread.start()

    def _serve(self) -> None:
        assert self._listener is not None
        while not self._stop.is_set():
            try:
                client_sock, client_addr = self._listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            threading.Thread(
                target=self._handle_client,
                args=(client_sock, client_addr),
                name=f"ssh-local-forward-client-{self.spec.bind_port}",
                daemon=True,
            ).start()

    def _handle_client(self, client_sock: socket.socket, client_addr) -> None:
        try:
            channel = self.transport.open_channel(
                "direct-tcpip",
                (self.spec.target_host, self.spec.target_port),
                client_addr,
            )
        except (OSError, paramiko.SSHException):
            log.warning("failed to open local tunnel channel for %s", self.spec.label, exc_info=True)
            client_sock.close()
            return
        _bridge(client_sock, channel, self._stop)

    def stop(self) -> None:
        super().stop()
        if self._listener is not None:
            try:
                self._listener.close()
            except OSError:
                pass


class RemotePortForwarder(_BaseForwarder):
    def start(self) -> None:
        self.transport.request_port_forward(self.spec.bind_host, self.spec.bind_port)
        self._thread = threading.Thread(
            target=self._serve, name=f"ssh-remote-forward-{self.spec.bind_port}", daemon=True
        )
        self._thread.start()

    def _serve(self) -> None:
        while not self._stop.is_set():
            channel = self.transport.accept(0.5)
            if channel is None:
                continue
            threading.Thread(
                target=self._handle_channel,
                args=(channel,),
                name=f"ssh-remote-forward-client-{self.spec.bind_port}",
                daemon=True,
            ).start()

    def _handle_channel(self, channel) -> None:
        try:
            sock = socket.create_connection(
                (self.spec.target_host, self.spec.target_port), timeout=10
            )
        except OSError:
            log.warning("failed to connect remote tunnel target for %s", self.spec.label, exc_info=True)
            channel.close()
            return
        _bridge(channel, sock, self._stop)

    def stop(self) -> None:
        super().stop()
        try:
            self.transport.cancel_port_forward(self.spec.bind_host, self.spec.bind_port)
        except Exception:
            log.debug("cancel remote port forward failed", exc_info=True)


class DynamicSocksForwarder(LocalPortForwarder):
    def _handle_client(self, client_sock: socket.socket, _client_addr) -> None:
        try:
            target = _read_socks5_target(client_sock)
            if target is None:
                return
            channel = self.transport.open_channel(
                "direct-tcpip",
                target,
                client_sock.getsockname(),
            )
            client_sock.sendall(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        except (OSError, paramiko.SSHException):
            log.warning("failed to open dynamic tunnel channel for %s", self.spec.label, exc_info=True)
            try:
                client_sock.sendall(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
            except OSError:
                pass
            client_sock.close()
            return
        _bridge(client_sock, channel, self._stop)


def _read_socks5_target(sock: socket.socket) -> tuple[str, int] | None:
    header = sock.recv(2)
    if len(header) != 2 or header[0] != 5:
        sock.close()
        return None
    methods = sock.recv(header[1])
    if len(methods) != header[1]:
        sock.close()
        return None
    sock.sendall(b"\x05\x00")
    request = sock.recv(4)
    if len(request) != 4 or request[0] != 5 or request[1] != 1:
        sock.sendall(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
        sock.close()
        return None
    atyp = request[3]
    if atyp == 1:
        host = socket.inet_ntoa(sock.recv(4))
    elif atyp == 3:
        length = sock.recv(1)
        if not length:
            sock.close()
            return None
        host = sock.recv(length[0]).decode("idna")
    elif atyp == 4:
        host = socket.inet_ntop(socket.AF_INET6, sock.recv(16))
    else:
        sock.sendall(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
        sock.close()
        return None
    port_bytes = sock.recv(2)
    if len(port_bytes) != 2:
        sock.close()
        return None
    return host, int.from_bytes(port_bytes, "big")


@dataclass
class SshCredentials:
    host: str
    port: int = 22
    username: str = ""
    # auth: "password" | "key" | "agent"
    auth: str = "agent"
    password: Optional[str] = None        # never persisted; supplied at connect-time
    key_filename: Optional[str] = None
    certificate_filename: Optional[str] = None
    passphrase: Optional[str] = None      # never persisted; supplied at connect-time
    connect_timeout: float = 15.0
    agent_forwarding: bool = False
    keepalive_interval: int = 0   # seconds; 0 disables
    tcp_keepalive: bool = False   # SO_KEEPALIVE on the underlying socket
    known_hosts_file: Optional[str] = None
    startup_command: str = ""
    tunnels: list[str] = field(default_factory=list)
    proxy_command: str = ""
    proxy_jump: str = ""
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
            certificate_filename=data.get("certificate_path") or None,
            connect_timeout=float(data.get("connect_timeout", 15) or 15),
            agent_forwarding=bool(data.get("agent_forwarding", False)),
            keepalive_interval=int(data.get("keepalive_interval", 0) or 0),
            tcp_keepalive=bool(data.get("tcp_keepalive", False)),
            known_hosts_file=data.get("known_hosts_file") or None,
            startup_command=data.get("command") or "",
            tunnels=list(data.get("tunnels") or []),
            proxy_command=data.get("proxy_command") or "",
            proxy_jump=data.get("proxy_jump") or "",
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
                key_files = [os.path.expanduser(self.creds.key_filename)]
                if self.creds.certificate_filename:
                    key_files.append(os.path.expanduser(self.creds.certificate_filename))
                kwargs["key_filename"] = key_files
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
        """User-facing connection state for tab/sidebar status surfaces."""
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
        if self.creds.proxy_command:
            command = (
                self.creds.proxy_command
                .replace("%h", self.creds.host)
                .replace("%p", str(self.creds.port))
            )
            return paramiko.proxy.ProxyCommand(command)
        if self.creds.proxy_jump:
            jump = self._parse_proxy_jump(self.creds.proxy_jump)
            if jump is None:
                raise paramiko.SSHException(f"Invalid ProxyJump: {self.creds.proxy_jump!r}")
            user, host, port = jump
            destination = f"{self.creds.host}:{self.creds.port}"
            target = f"{user}@{host}" if user else host
            command = f"ssh -W {shlex.quote(destination)} -p {port} {shlex.quote(target)}"
            return paramiko.proxy.ProxyCommand(command)
        return None

    @staticmethod
    def _parse_proxy_jump(value: str) -> tuple[str, str, int] | None:
        raw = (value or "").strip()
        if not raw:
            return None
        user = ""
        if "@" in raw:
            user, raw = raw.split("@", 1)
        host, sep, port_text = raw.rpartition(":")
        if not sep:
            host = raw
            port = 22
        else:
            try:
                port = int(port_text)
            except ValueError:
                return None
        if not host or port < 1 or port > 65535:
            return None
        return user, host, port

    def _start_tunnels(self, client: paramiko.SSHClient) -> None:
        transport = client.get_transport()
        if transport is None:
            return
        for raw in self.creds.tunnels:
            try:
                spec = parse_tunnel_spec(raw)
                if spec.kind == "L":
                    forwarder: _BaseForwarder = LocalPortForwarder(transport, spec)
                elif spec.kind == "R":
                    forwarder = RemotePortForwarder(transport, spec)
                else:
                    forwarder = DynamicSocksForwarder(transport, spec)
                forwarder.start()
                self._forwarders.append(forwarder)
                log.info("started SSH tunnel %s", spec.label)
            except Exception as e:
                raise paramiko.SSHException(f"Failed to start tunnel {raw!r}: {e}") from e

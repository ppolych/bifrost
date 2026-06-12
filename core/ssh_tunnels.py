import logging
import select
import socket
import threading
from dataclasses import dataclass

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


class BaseForwarder:
    def __init__(self, transport: paramiko.Transport, spec: TunnelSpec):
        self.transport = transport
        self.spec = spec
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def stop(self) -> None:
        self._stop.set()

    @property
    def active(self) -> bool:
        return not self._stop.is_set()


class LocalPortForwarder(BaseForwarder):
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

    @property
    def active(self) -> bool:
        return super().active and self._listener is not None


class RemotePortForwarder(BaseForwarder):
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

    @property
    def active(self) -> bool:
        return super().active and self.transport.is_active()


class DynamicSocksForwarder(LocalPortForwarder):
    def _handle_client(self, client_sock: socket.socket, _client_addr) -> None:
        try:
            target = _read_socks5_target(client_sock)
            if target is None:
                return
            channel = self.transport.open_channel("direct-tcpip", target, client_sock.getsockname())
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


def start_tunnels(transport: paramiko.Transport | None, tunnel_specs: list[str]) -> list[BaseForwarder]:
    if transport is None:
        return []
    forwarders: list[BaseForwarder] = []
    for raw in tunnel_specs:
        try:
            spec = parse_tunnel_spec(raw)
            if spec.kind == "L":
                forwarder: BaseForwarder = LocalPortForwarder(transport, spec)
            elif spec.kind == "R":
                forwarder = RemotePortForwarder(transport, spec)
            else:
                forwarder = DynamicSocksForwarder(transport, spec)
            forwarder.start()
            forwarders.append(forwarder)
            log.info("started SSH tunnel %s", spec.label)
        except Exception as e:
            raise paramiko.SSHException(f"Failed to start tunnel {raw!r}: {e}") from e
    return forwarders

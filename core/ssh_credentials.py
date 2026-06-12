from dataclasses import dataclass, field
from typing import Optional


def _coerce_int(value, default: int, *, min_value: int | None = None, max_value: int | None = None) -> int:
    try:
        result = int(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default
    if min_value is not None and result < min_value:
        return default
    if max_value is not None and result > max_value:
        return default
    return result


def _coerce_float(value, default: float, *, min_value: float | None = None) -> float:
    try:
        result = float(value if value not in (None, "") else default)
    except (TypeError, ValueError):
        return default
    if min_value is not None and result < min_value:
        return default
    return result


@dataclass
class SshCredentials:
    host: str
    port: int = 22
    username: str = ""
    auth: str = "agent"
    password: Optional[str] = None
    key_filename: Optional[str] = None
    certificate_filename: Optional[str] = None
    passphrase: Optional[str] = None
    connect_timeout: float = 15.0
    agent_forwarding: bool = False
    keepalive_interval: int = 0
    tcp_keepalive: bool = False
    known_hosts_file: Optional[str] = None
    startup_command: str = ""
    tunnels: list[str] = field(default_factory=list)
    proxy_command: str = ""
    proxy_jump: str = ""
    extra_kwargs: dict = field(default_factory=dict)

    @classmethod
    def from_session(cls, data: dict) -> "SshCredentials":
        return cls(
            host=data.get("host", ""),
            port=_coerce_int(data.get("port"), 22, min_value=1, max_value=65535),
            username=data.get("user", "") or "",
            auth=data.get("auth", "agent"),
            key_filename=data.get("key_path") or None,
            certificate_filename=data.get("certificate_path") or None,
            connect_timeout=_coerce_float(data.get("connect_timeout"), 15.0, min_value=1.0),
            agent_forwarding=bool(data.get("agent_forwarding", False)),
            keepalive_interval=_coerce_int(data.get("keepalive_interval"), 0, min_value=0),
            tcp_keepalive=bool(data.get("tcp_keepalive", False)),
            known_hosts_file=data.get("known_hosts_file") or None,
            startup_command=data.get("command") or "",
            tunnels=list(data.get("tunnels") or []) if isinstance(data.get("tunnels") or [], list) else [],
            proxy_command=data.get("proxy_command") or "",
            proxy_jump=data.get("proxy_jump") or "",
        )

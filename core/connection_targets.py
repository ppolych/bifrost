"""Host/port parsing shared by quick-connect protocols."""


def split_host_port(target: str) -> tuple[str, str]:
    """Accept host:port and [IPv6]:port; bare IPv6 has no explicit port."""
    if target.startswith("["):
        host, closing, suffix = target[1:].partition("]")
        if closing and (not suffix or suffix.startswith(":")):
            return host, suffix[1:] if suffix else ""
    if target.count(":") == 1:
        host, port = target.split(":", 1)
        return host, port
    return target, ""


def target_with_port(target: str, port: str) -> str:
    """Add a command's separate port, preserving any user and inline port."""
    user, separator, address = target.rpartition("@")
    host, existing_port = split_host_port(address)
    if existing_port:
        return target
    if ":" in host:
        host = f"[{host}]"
    return f"{user + separator if separator else ''}{host}:{port}"

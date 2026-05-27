"""IP-subnet math for the Tools panel.

Wraps `ipaddress` (stdlib) with a small returns-a-dict helper so the UI can
render fields without doing arithmetic itself.
"""

from __future__ import annotations

import ipaddress


def calculate(cidr: str) -> dict[str, str]:
    """Take "10.0.0.5/24" (or just "10.0.0.5") and return network details.

    Raises ValueError if the input is unparseable.
    """
    cidr = (cidr or "").strip()
    if "/" not in cidr:
        cidr = cidr + "/32"
    try:
        net = ipaddress.ip_network(cidr, strict=False)
    except ValueError as e:
        raise ValueError(f"Invalid CIDR: {cidr!r} ({e})") from e

    host_count = net.num_addresses
    usable = max(host_count - 2, 0) if isinstance(net, ipaddress.IPv4Network) and net.prefixlen <= 30 else host_count

    # Don't materialize net.hosts() — on IPv6 /64 that's 2**64 entries and
    # would hang. Compute first/last directly from network arithmetic.
    first_host = None
    last_host = None
    if isinstance(net, ipaddress.IPv4Network):
        if net.prefixlen <= 30:
            first_host = net.network_address + 1
            last_host = net.broadcast_address - 1
        elif net.prefixlen == 31:
            # RFC 3021: both addresses usable as host addresses.
            first_host = net.network_address
            last_host = net.broadcast_address
        else:  # /32
            first_host = net.network_address
            last_host = net.network_address
    else:  # IPv6 — first host is network+1 (skip subnet-router anycast).
        if net.prefixlen < 128:
            first_host = net.network_address + 1
            last_host = net.broadcast_address
        else:
            first_host = net.network_address
            last_host = net.network_address

    return {
        "Network":      str(net.network_address),
        "Broadcast":    str(net.broadcast_address) if isinstance(net, ipaddress.IPv4Network) else "—",
        "Netmask":      str(net.netmask),
        "Wildcard":     str(net.hostmask),
        "Prefix":       f"/{net.prefixlen}",
        "Total hosts":  str(host_count),
        "Usable hosts": str(usable),
        "First host":   str(first_host) if first_host else "—",
        "Last host":    str(last_host) if last_host else "—",
        "Version":      f"IPv{net.version}",
    }

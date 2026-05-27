"""Wake-on-LAN magic packet sender.

A magic packet is 6 bytes of 0xFF followed by 16 repetitions of the target MAC
(102 bytes total), sent as a UDP broadcast to port 9 (some hardware uses 7).
"""

from __future__ import annotations

import logging
import re
import socket

log = logging.getLogger(__name__)

_HEX12 = re.compile(r"^[0-9A-Fa-f]{12}$")


def parse_mac(mac: str) -> bytes:
    """Normalize MAC strings to a 6-byte address.

    Accepts the common separators (colon, dash, dot) as well as bare hex.
    Raises ValueError on anything that isn't exactly 12 hex digits.
    """
    if not isinstance(mac, str):
        raise ValueError("MAC must be a string")
    cleaned = re.sub(r"[\s:.\-]", "", mac)
    if not _HEX12.match(cleaned):
        raise ValueError(f"Invalid MAC address: {mac!r}")
    return bytes.fromhex(cleaned)


def build_magic_packet(mac: str) -> bytes:
    addr = parse_mac(mac)
    return b"\xff" * 6 + addr * 16


def send_magic_packet(
    mac: str,
    broadcast_address: str = "255.255.255.255",
    port: int = 9,
) -> None:
    """Broadcast a WoL magic packet to wake the host owning `mac`.

    Raises ValueError on bad MAC and OSError on socket failure.
    """
    packet = build_magic_packet(mac)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.sendto(packet, (broadcast_address, port))
    log.info("WoL packet sent to %s via %s:%d", mac, broadcast_address, port)

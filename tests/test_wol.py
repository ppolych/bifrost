"""Wake-on-LAN tests — pure unit, no sockets actually opened."""

import socket
from unittest.mock import patch

import pytest


def test_parse_mac_colon():
    from core.wake_on_lan import parse_mac
    assert parse_mac("AA:BB:CC:11:22:33") == bytes.fromhex("aabbcc112233")


def test_parse_mac_dash():
    from core.wake_on_lan import parse_mac
    assert parse_mac("aa-bb-cc-11-22-33") == bytes.fromhex("aabbcc112233")


def test_parse_mac_dot():
    from core.wake_on_lan import parse_mac
    assert parse_mac("aabb.cc11.2233") == bytes.fromhex("aabbcc112233")


def test_parse_mac_bare_hex():
    from core.wake_on_lan import parse_mac
    assert parse_mac("AABBCC112233") == bytes.fromhex("aabbcc112233")


def test_parse_mac_rejects_short():
    from core.wake_on_lan import parse_mac
    with pytest.raises(ValueError):
        parse_mac("AA:BB:CC:11:22")


def test_parse_mac_rejects_non_hex():
    from core.wake_on_lan import parse_mac
    with pytest.raises(ValueError):
        parse_mac("AA:BB:CC:11:22:ZZ")


def test_parse_mac_rejects_non_string():
    from core.wake_on_lan import parse_mac
    with pytest.raises(ValueError):
        parse_mac(112233445566)  # type: ignore[arg-type]


def test_magic_packet_shape():
    from core.wake_on_lan import build_magic_packet

    pkt = build_magic_packet("AA:BB:CC:11:22:33")
    assert len(pkt) == 102
    assert pkt[:6] == b"\xff" * 6
    # Each of the 16 repetitions equals the MAC.
    mac = bytes.fromhex("aabbcc112233")
    for i in range(16):
        start = 6 + i * 6
        assert pkt[start:start + 6] == mac


def test_send_magic_packet_uses_broadcast_socket():
    """Verify the socket gets SO_BROADCAST and the right destination."""
    from core.wake_on_lan import send_magic_packet

    with patch("core.wake_on_lan.socket.socket") as sock_factory:
        sock_instance = sock_factory.return_value.__enter__.return_value
        send_magic_packet("AA:BB:CC:11:22:33", broadcast_address="192.168.1.255", port=9)
        sock_instance.setsockopt.assert_called_once_with(
            socket.SOL_SOCKET, socket.SO_BROADCAST, 1
        )
        args, _ = sock_instance.sendto.call_args
        packet, dest = args
        assert len(packet) == 102
        assert dest == ("192.168.1.255", 9)

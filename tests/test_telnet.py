"""In-process Telnet backend: IAC negotiation, stream cleaning, and a real
loopback round-trip. No GUI needed."""

import socket
import threading

import pytest

from core.telnet_backend import (
    DO, DONT, IAC, OPT_ECHO, OPT_NAWS, OPT_SGA, SB, SE, WILL, WONT,
    TelnetBackend,
)


@pytest.fixture
def backend():
    b = TelnetBackend("example.invalid", 23)
    sent = []
    b._send_raw = sent.append  # capture negotiation replies
    b._sent = sent
    return b


def test_plain_data_passes_through(backend):
    assert backend._process_incoming(b"hello world") == b"hello world"
    assert backend._sent == []


def test_escaped_iac_unescapes(backend):
    assert backend._process_incoming(bytes([65, IAC, IAC, 66])) == bytes([65, 255, 66])


def test_will_echo_and_sga_accepted_others_refused(backend):
    backend._process_incoming(bytes([IAC, WILL, OPT_ECHO, IAC, WILL, OPT_SGA, IAC, WILL, 42]))
    assert bytes([IAC, DO, OPT_ECHO]) in backend._sent
    assert bytes([IAC, DO, OPT_SGA]) in backend._sent
    assert bytes([IAC, DONT, 42]) in backend._sent


def test_do_naws_enables_and_sends_winsize(backend):
    backend.set_winsize(24, 80)
    backend._process_incoming(bytes([IAC, DO, OPT_NAWS]))
    assert bytes([IAC, WILL, OPT_NAWS]) in backend._sent
    naws = bytes([IAC, SB, OPT_NAWS]) + (80).to_bytes(2, "big") + (24).to_bytes(2, "big") + bytes([IAC, SE])
    assert naws in backend._sent
    assert backend._naws_enabled


def test_do_unknown_option_refused(backend):
    backend._process_incoming(bytes([IAC, DO, 42]))
    assert bytes([IAC, WONT, 42]) in backend._sent


def test_subnegotiation_is_stripped(backend):
    data = b"ab" + bytes([IAC, SB, OPT_NAWS, 1, 2, IAC, SE]) + b"cd"
    assert backend._process_incoming(data) == b"abcd"


def test_split_iac_sequence_across_chunks(backend):
    # IAC arrives at the end of one chunk, the command completes in the next.
    assert backend._process_incoming(b"ab" + bytes([IAC])) == b"ab"
    assert backend._process_incoming(bytes([WILL, OPT_ECHO]) + b"cd") == b"cd"
    assert bytes([IAC, DO, OPT_ECHO]) in backend._sent


def test_negotiation_replies_are_not_repeated(backend):
    backend._process_incoming(bytes([IAC, WILL, OPT_ECHO]))
    backend._process_incoming(bytes([IAC, WILL, OPT_ECHO]))
    assert backend._sent.count(bytes([IAC, DO, OPT_ECHO])) == 1


def test_write_escapes_iac_and_maps_cr():
    b = TelnetBackend("example.invalid", 23)
    sent = []
    b._send_raw = sent.append
    b._sock = object()  # write() requires a socket; _send_raw is stubbed
    b.write(b"\xff")
    assert sent[-1] == b"\xff\xff"
    b.write("ls\r")
    assert sent[-1] == b"ls\r\n"
    b.write("a\r\nb")  # pre-normalized CRLF must not double
    assert sent[-1] == b"a\r\nb"


def test_loopback_round_trip():
    """Full connect/read/write against a real socket server."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(1)
    port = server.getsockname()[1]
    received = {}

    def serve():
        conn, _ = server.accept()
        # Negotiate NAWS, then greet.
        conn.sendall(bytes([IAC, DO, OPT_NAWS]) + b"login: ")
        # Negotiation replies and the login arrive in separate segments;
        # accumulate until the login shows up (or the peer hangs up).
        buf = b""
        while b"guest\r\n" not in buf:
            chunk = conn.recv(1024)
            if not chunk:
                break
            buf += chunk
        received["client_bytes"] = buf
        conn.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()

    b = TelnetBackend("127.0.0.1", port, connect_timeout=5)
    b.start()
    assert b._ready.wait(timeout=5)
    assert b._connect_error is None

    # Negotiation bytes are stripped; the greeting comes through.
    data = b.read()
    assert data == b"login: "
    assert b._naws_enabled

    b.write("guest\r")
    t.join(timeout=5)
    # The reply contains our WILL NAWS + winsize subnegotiation + the login.
    assert received["client_bytes"].endswith(b"guest\r\n")
    assert bytes([IAC, WILL, OPT_NAWS]) in received["client_bytes"]

    b.close()
    server.close()


def test_connect_failure_renders_in_terminal():
    # Port 1 on localhost should refuse instantly.
    b = TelnetBackend("127.0.0.1", 1, connect_timeout=2)
    b.start()
    assert b._ready.wait(timeout=10)
    assert b._connect_error is not None
    out = b.read()
    assert b"connection failed" in out
    # After the error is emitted once, read() reports EOF so the reader stops.
    assert b.read() == b""
    b.close()

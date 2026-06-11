"""In-process Telnet backend.

Same public surface as `core.terminal_backend.TerminalBackend` so
`TerminalReader` and `TerminalWidget` can use it interchangeably — replaces
the old shell-out to the system `telnet` binary.

Connection lifecycle mirrors ParamikoBackend: start() connects on a worker
thread, a connect failure is converted into bytes that read() returns so the
error renders in the terminal, and close() shuts the socket down which
unblocks any in-flight recv().

Speaks just enough NVT (RFC 854/855): option negotiation accepts ECHO and
SGA from the server plus NAWS (window size) for the client and refuses
everything else; IAC sequences are stripped from the data stream; outgoing
CR is sent as CR LF and literal 0xFF bytes are escaped.
"""

from __future__ import annotations

import logging
import socket
import threading
from typing import Optional

log = logging.getLogger(__name__)

# Telnet command bytes (RFC 854).
IAC = 255
DONT = 254
DO = 253
WONT = 252
WILL = 251
SB = 250
SE = 240

# Options we understand.
OPT_ECHO = 1
OPT_SGA = 3
OPT_NAWS = 31


class TelnetBackend:
    """Telnet backend with the same surface as TerminalBackend."""

    def __init__(self, host: str, port: int = 23, connect_timeout: float = 10.0):
        self.host = host
        self.port = int(port)
        self.connect_timeout = connect_timeout

        self._sock: Optional[socket.socket] = None
        self._ready = threading.Event()
        self._connect_error: Optional[BaseException] = None
        self._error_emitted = False
        self._closed = False
        self._pending = b""          # partial IAC sequence split across recv()s
        self._naws_enabled = False
        self._winsize = (24, 80)     # (rows, cols)
        # Option state for negotiation loop avoidance (RFC 854): we only reply
        # to a request when it changes our state, so re-requests for the
        # current state are ignored but legitimate renegotiation still works
        # (e.g. servers toggling ECHO off and back on around password prompts).
        self._remote_on: set[int] = set()  # options we've acked the server enabling
        self._local_on: set[int] = set()   # options we've enabled on our side

    # ----- lifecycle -----

    def start(self):
        threading.Thread(target=self._connect, name="telnet-connect", daemon=True).start()

    def _connect(self):
        try:
            sock = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
            sock.settimeout(None)
            self._sock = sock
        except BaseException as e:
            log.warning("Telnet connect to %s:%s failed: %s", self.host, self.port, e)
            self._connect_error = e
        finally:
            self._ready.set()

    # ----- io -----

    def read(self, size: int = 4096) -> bytes:
        if self._closed:
            return b""

        if not self._ready.is_set():
            self._ready.wait(timeout=0.25)
            if not self._ready.is_set():
                return f"Connecting to {self.host}:{self.port}...\r\n".encode()

        if self._connect_error is not None and not self._error_emitted:
            self._error_emitted = True
            return f"\r\n\x1b[31m[connection failed: {self._connect_error}]\x1b[0m\r\n".encode()

        sock = self._sock
        if sock is None:
            return b""

        # Loop (not recurse) past negotiation-only chunks: servers can send
        # bare IAC traffic indefinitely (e.g. IAC NOP keepalives on an idle
        # session), and each one must not consume a stack frame.
        while not self._closed:
            try:
                data = sock.recv(size)
            except OSError as e:
                log.debug("telnet recv failed: %s", e)
                return b""
            if not data:
                return b""
            cleaned = self._process_incoming(data)
            if cleaned:
                return cleaned
            # All bytes were negotiation traffic; don't return b"" (the
            # reader treats that as EOF) — wait for the next chunk.
        return b""

    def write(self, data) -> None:
        if self._closed or self._sock is None:
            return
        if isinstance(data, str):
            data = data.encode()
        # Escape literal IAC bytes, then normalize line endings to NVT CR LF.
        data = data.replace(bytes([IAC]), bytes([IAC, IAC]))
        data = data.replace(b"\r\n", b"\r").replace(b"\r", b"\r\n")
        self._send_raw(data)

    def set_winsize(self, rows: int, cols: int) -> None:
        self._winsize = (rows, cols)
        if self._naws_enabled:
            self._send_naws()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    # ----- telnet protocol -----

    def _send_raw(self, data: bytes) -> None:
        sock = self._sock
        if sock is None:
            return
        try:
            sock.sendall(data)
        except OSError:
            log.debug("telnet send failed", exc_info=True)

    def _process_incoming(self, data: bytes) -> bytes:
        """Strip and answer IAC sequences; return the remaining user data."""
        if self._pending:
            data = self._pending + data
            self._pending = b""
        out = bytearray()
        i = 0
        n = len(data)
        while i < n:
            byte = data[i]
            if byte != IAC:
                out.append(byte)
                i += 1
                continue
            if i + 1 >= n:
                self._pending = data[i:]
                break
            cmd = data[i + 1]
            if cmd == IAC:  # escaped literal 0xFF
                out.append(IAC)
                i += 2
            elif cmd in (DO, DONT, WILL, WONT):
                if i + 2 >= n:
                    self._pending = data[i:]
                    break
                self._negotiate(cmd, data[i + 2])
                i += 3
            elif cmd == SB:
                # Find the terminating IAC SE, treating IAC IAC as an escaped
                # data byte (a plain find() would false-match an escaped 0xFF
                # followed by a 0xF0 data byte and desync the stream).
                j = i + 2
                end = -1
                while j < n:
                    if data[j] != IAC:
                        j += 1
                    elif j + 1 >= n:
                        break  # IAC at chunk end; sequence incomplete
                    elif data[j + 1] == SE:
                        end = j
                        break
                    else:
                        j += 2  # IAC IAC escape (or stray command): skip pair
                if end == -1:
                    self._pending = data[i:]
                    break
                i = end + 2  # we don't act on any subnegotiation
            else:  # NOP, GA, AYT, ... — two-byte commands we ignore
                i += 2
        return bytes(out)

    def _negotiate(self, cmd: int, opt: int) -> None:
        if cmd == WILL:
            # Server offers an option: accept remote ECHO and SGA, refuse the rest.
            if opt in self._remote_on:
                return  # already enabled; re-acking would risk a reply loop
            if opt in (OPT_ECHO, OPT_SGA):
                self._remote_on.add(opt)
                self._send_raw(bytes([IAC, DO, opt]))
            else:
                self._send_raw(bytes([IAC, DONT, opt]))
        elif cmd == WONT:
            if opt in self._remote_on:
                self._remote_on.discard(opt)
                self._send_raw(bytes([IAC, DONT, opt]))
        elif cmd == DO:
            # Server asks us to enable an option: we can do NAWS and SGA.
            if opt in self._local_on:
                return  # already enabled
            if opt == OPT_NAWS:
                self._naws_enabled = True
                self._local_on.add(opt)
                self._send_raw(bytes([IAC, WILL, OPT_NAWS]))
                self._send_naws()
            elif opt == OPT_SGA:
                self._local_on.add(opt)
                self._send_raw(bytes([IAC, WILL, OPT_SGA]))
            else:
                self._send_raw(bytes([IAC, WONT, opt]))
        elif cmd == DONT:
            if opt == OPT_NAWS:
                self._naws_enabled = False
            if opt in self._local_on:
                self._local_on.discard(opt)
                self._send_raw(bytes([IAC, WONT, opt]))

    def _send_naws(self) -> None:
        rows, cols = self._winsize
        payload = cols.to_bytes(2, "big") + rows.to_bytes(2, "big")
        payload = payload.replace(bytes([IAC]), bytes([IAC, IAC]))
        self._send_raw(bytes([IAC, SB, OPT_NAWS]) + payload + bytes([IAC, SE]))

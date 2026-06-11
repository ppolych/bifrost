"""In-process VNC (RFB) client.

Protocol-only — no Qt. `VncClient` runs the connection on a daemon thread and
reports through plain callbacks invoked *from that thread*; the widget layer
(`widgets/vnc_viewer.py`) bridges them onto the GUI thread with signals.

Supported: RFB 3.3/3.7/3.8 handshakes, security types None and VNC
Authentication (DES challenge-response), Raw and CopyRect encodings, and the
DesktopSize pseudo-encoding. The pixel format is pinned to 32-bit true colour
with red/green/blue in ascending memory bytes, which maps 1:1 onto
QImage.Format_RGBX8888 so the widget can wrap the framebuffer without
conversion.
"""

from __future__ import annotations

import logging
import socket
import struct
import threading
from typing import Callable, Optional

log = logging.getLogger(__name__)

SEC_INVALID = 0
SEC_NONE = 1
SEC_VNC_AUTH = 2

ENC_RAW = 0
ENC_COPY_RECT = 1
ENC_DESKTOP_SIZE = -223

_BPP = 4  # bytes per pixel of our negotiated format


class VncError(Exception):
    pass


def _reverse_bits(byte: int) -> int:
    out = 0
    for i in range(8):
        out = (out << 1) | ((byte >> i) & 1)
    return out


def vnc_auth_response(password: str, challenge: bytes) -> bytes:
    """DES-encrypt the 16-byte challenge with the bit-reversed password key.

    VNC's quirk: the 8-byte DES key is the password (truncated/zero-padded)
    with the *bits of each byte reversed*. Single DES == 3DES with K1=K2=K3,
    which lets us use the cryptography package instead of shipping DES.
    """
    from cryptography.hazmat.primitives.ciphers import Cipher, modes
    try:  # cryptography >= 48 moved 3DES to the decrepit module
        from cryptography.hazmat.decrepit.ciphers.algorithms import TripleDES
    except ImportError:  # pragma: no cover - older cryptography
        from cryptography.hazmat.primitives.ciphers.algorithms import TripleDES

    key = password.encode("latin-1", "replace")[:8].ljust(8, b"\0")
    key = bytes(_reverse_bits(b) for b in key)
    encryptor = Cipher(TripleDES(key * 3), modes.ECB()).encryptor()
    return encryptor.update(challenge) + encryptor.finalize()


class VncClient:
    """RFB client; all callbacks fire on the worker thread."""

    def __init__(
        self,
        host: str,
        port: int = 5900,
        password: Optional[str] = None,
        connect_timeout: float = 10.0,
        on_connected: Optional[Callable[[str], None]] = None,
        on_resize: Optional[Callable[[int, int], None]] = None,
        on_frame: Optional[Callable[[], None]] = None,
        on_error: Optional[Callable[[str], None]] = None,
        on_closed: Optional[Callable[[], None]] = None,
    ):
        self.host = host
        self.port = int(port)
        self.password = password
        self.connect_timeout = connect_timeout
        self.name = ""

        self._on_connected = on_connected
        self._on_resize = on_resize
        self._on_frame = on_frame
        self._on_error = on_error
        self._on_closed = on_closed

        self._sock: Optional[socket.socket] = None
        self._send_lock = threading.Lock()
        self._fb_lock = threading.Lock()
        self._fb = bytearray(0)
        self._fb_w = 0
        self._fb_h = 0
        self._closed = False
        self._thread: Optional[threading.Thread] = None

    # ----- lifecycle -----

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="vnc-client", daemon=True)
        self._thread.start()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass

    def join(self, timeout: float | None = None) -> None:
        """Wait for the worker thread to finish. Call after close() when the
        callback target is about to be destroyed — a callback firing into a
        deleted QObject crashes."""
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout)

    def snapshot(self):
        """Return (framebuffer-bytes, width, height) for painting."""
        with self._fb_lock:
            return self._fb, self._fb_w, self._fb_h

    # ----- input (called from the GUI thread) -----

    def send_pointer(self, x: int, y: int, button_mask: int) -> None:
        self._send(struct.pack(">BBHH", 5, button_mask & 0xFF, max(0, x), max(0, y)))

    def send_key(self, keysym: int, down: bool) -> None:
        self._send(struct.pack(">BBxxI", 4, 1 if down else 0, keysym))

    # ----- worker -----

    def _run(self) -> None:
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.connect_timeout)
            self._sock.settimeout(None)
            self._handshake()
            self._init()
            if self._on_connected:
                self._on_connected(self.name)
            self._request_update(incremental=False)
            self._message_loop()
        except VncError as e:
            if not self._closed and self._on_error:
                self._on_error(str(e))
        except OSError as e:
            if not self._closed and self._on_error:
                self._on_error(str(e))
        except Exception as e:  # protocol bug — log it, still tell the UI
            log.exception("VNC client crashed")
            if not self._closed and self._on_error:
                self._on_error(f"internal error: {e}")
        finally:
            self.close()
            if self._on_closed:
                self._on_closed()

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            chunk = self._sock.recv(n - len(buf))
            if not chunk:
                raise VncError("connection closed by server")
            buf += chunk
        return buf

    def _send(self, data: bytes) -> None:
        sock = self._sock
        if sock is None or self._closed:
            return
        try:
            with self._send_lock:
                sock.sendall(data)
        except OSError:
            log.debug("vnc send failed", exc_info=True)

    def _read_reason(self) -> str:
        (length,) = struct.unpack(">I", self._recv_exact(4))
        return self._recv_exact(min(length, 4096)).decode("utf-8", errors="replace")

    def _handshake(self) -> None:
        banner = self._recv_exact(12)
        if not banner.startswith(b"RFB "):
            raise VncError(f"not an RFB server: {banner!r}")
        try:
            major = int(banner[4:7])
            minor = int(banner[8:11])
        except ValueError as e:
            raise VncError(f"bad RFB version banner: {banner!r}") from e

        if (major, minor) >= (3, 8):
            proto = 38
            self._send(b"RFB 003.008\n")
        elif (major, minor) >= (3, 7):
            proto = 37
            self._send(b"RFB 003.007\n")
        else:
            proto = 33
            self._send(b"RFB 003.003\n")
        self._proto = proto

        if proto == 33:
            (sectype,) = struct.unpack(">I", self._recv_exact(4))
            if sectype == SEC_INVALID:
                raise VncError(self._read_reason() or "server refused the connection")
        else:
            (count,) = struct.unpack(">B", self._recv_exact(1))
            if count == 0:
                raise VncError(self._read_reason() or "server offered no security types")
            offered = list(self._recv_exact(count))
            sectype = self._pick_security(offered)
            self._send(bytes([sectype]))

        if sectype == SEC_VNC_AUTH:
            if not self.password:
                raise VncError("server requires a VNC password")
            challenge = self._recv_exact(16)
            self._send(vnc_auth_response(self.password, challenge))
            self._check_security_result()
        elif sectype == SEC_NONE:
            if proto == 38:
                self._check_security_result()
        else:
            raise VncError(f"unsupported security type {sectype}")

    def _pick_security(self, offered: list[int]) -> int:
        if SEC_NONE in offered and not self.password:
            return SEC_NONE
        if SEC_VNC_AUTH in offered and self.password:
            return SEC_VNC_AUTH
        if SEC_NONE in offered:
            return SEC_NONE
        if SEC_VNC_AUTH in offered:
            return SEC_VNC_AUTH
        raise VncError(f"no supported security type (server offered {offered})")

    def _check_security_result(self) -> None:
        (result,) = struct.unpack(">I", self._recv_exact(4))
        if result != 0:
            if self._proto == 38:
                raise VncError(self._read_reason() or "authentication failed")
            raise VncError("authentication failed")

    def _init(self) -> None:
        self._send(b"\x01")  # ClientInit: shared session
        head = self._recv_exact(24)
        width, height = struct.unpack(">HH", head[:4])
        (name_len,) = struct.unpack(">I", head[20:24])
        self.name = self._recv_exact(name_len).decode("utf-8", errors="replace")
        self._resize_fb(width, height)

        # SetPixelFormat: 32bpp depth-24 little-endian true colour,
        # shifts r=0 g=8 b=16 → memory bytes R,G,B,X (QImage Format_RGBX8888).
        pixfmt = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 0, 8, 16)
        self._send(struct.pack(">Bxxx", 0) + pixfmt)

        encodings = (ENC_COPY_RECT, ENC_RAW, ENC_DESKTOP_SIZE)
        self._send(struct.pack(">BxH", 2, len(encodings)) + b"".join(
            struct.pack(">i", e) for e in encodings
        ))

    def _resize_fb(self, width: int, height: int) -> None:
        with self._fb_lock:
            self._fb = bytearray(width * height * _BPP)
            self._fb_w = width
            self._fb_h = height
        if self._on_resize:
            self._on_resize(width, height)

    def _request_update(self, incremental: bool = True) -> None:
        self._send(struct.pack(
            ">BBHHHH", 3, 1 if incremental else 0, 0, 0, self._fb_w, self._fb_h
        ))

    def _message_loop(self) -> None:
        while not self._closed:
            msg_type = self._recv_exact(1)[0]
            if msg_type == 0:
                self._read_framebuffer_update()
                if self._on_frame:
                    self._on_frame()
                self._request_update(incremental=True)
            elif msg_type == 1:  # SetColourMapEntries — true colour, skip
                self._recv_exact(1)
                _first, count = struct.unpack(">HH", self._recv_exact(4))
                self._recv_exact(count * 6)
            elif msg_type == 2:  # Bell
                pass
            elif msg_type == 3:  # ServerCutText
                self._recv_exact(3)
                (length,) = struct.unpack(">I", self._recv_exact(4))
                self._recv_exact(length)
            else:
                raise VncError(f"unknown server message type {msg_type}")

    def _read_framebuffer_update(self) -> None:
        self._recv_exact(1)  # padding
        (nrects,) = struct.unpack(">H", self._recv_exact(2))
        for _ in range(nrects):
            x, y, w, h, enc = struct.unpack(">HHHHi", self._recv_exact(12))
            if enc == ENC_RAW:
                data = self._recv_exact(w * h * _BPP)
                self._blit(x, y, w, h, data)
            elif enc == ENC_COPY_RECT:
                src_x, src_y = struct.unpack(">HH", self._recv_exact(4))
                self._copy_rect(src_x, src_y, x, y, w, h)
            elif enc == ENC_DESKTOP_SIZE:
                self._resize_fb(w, h)
            else:
                raise VncError(f"server sent unrequested encoding {enc}")

    def _blit(self, x: int, y: int, w: int, h: int, data: bytes) -> None:
        with self._fb_lock:
            fb_w = self._fb_w
            row_bytes = w * _BPP
            for row in range(h):
                dst = ((y + row) * fb_w + x) * _BPP
                src = row * row_bytes
                self._fb[dst:dst + row_bytes] = data[src:src + row_bytes]

    def _copy_rect(self, src_x: int, src_y: int, x: int, y: int, w: int, h: int) -> None:
        with self._fb_lock:
            fb_w = self._fb_w
            row_bytes = w * _BPP
            # Read the whole source region first so overlapping moves are safe.
            rows = [
                bytes(self._fb[((src_y + r) * fb_w + src_x) * _BPP:
                               ((src_y + r) * fb_w + src_x) * _BPP + row_bytes])
                for r in range(h)
            ]
            for r, chunk in enumerate(rows):
                dst = ((y + r) * fb_w + x) * _BPP
                self._fb[dst:dst + row_bytes] = chunk

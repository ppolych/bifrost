"""VNC client: RFB handshake, auth, framebuffer decoding, and input events,
exercised against a scripted fake RFB server on a real socket."""

import io
import socket
import struct
import threading
import time

import pytest

from core.vnc_client import (
    ENC_COPY_RECT, ENC_DESKTOP_SIZE, ENC_RAW, SEC_NONE, SEC_VNC_AUTH,
    VncClient, _reverse_bits, vnc_auth_response,
)


class FakeRfbServer(threading.Thread):
    """Single-connection RFB 3.8 server: None or VNC auth, one raw frame,
    then records every client message it receives."""

    def __init__(self, password=None, width=8, height=4, fill=(10, 20, 30), name="fake-vnc"):
        super().__init__(daemon=True)
        self.password = password
        self.width, self.height = width, height
        self.fill = fill
        self.display_name = name
        self.pointer_events = []
        self.key_events = []
        self.update_requests = 0
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.port = self.sock.getsockname()[1]

    def _recv(self, conn, n):
        buf = b""
        while len(buf) < n:
            chunk = conn.recv(n - len(buf))
            if not chunk:
                raise ConnectionError("client gone")
            buf += chunk
        return buf

    def run(self):
        conn, _ = self.sock.accept()
        try:
            conn.sendall(b"RFB 003.008\n")
            assert self._recv(conn, 12) == b"RFB 003.008\n"

            sectype = SEC_VNC_AUTH if self.password else SEC_NONE
            conn.sendall(bytes([1, sectype]))
            chosen = self._recv(conn, 1)[0]
            assert chosen == sectype
            if sectype == SEC_VNC_AUTH:
                challenge = bytes(range(16))
                conn.sendall(challenge)
                response = self._recv(conn, 16)
                ok = response == vnc_auth_response(self.password, challenge)
                if not ok:
                    reason = b"wrong password"
                    conn.sendall(struct.pack(">I", 1) + struct.pack(">I", len(reason)) + reason)
                    return
                conn.sendall(struct.pack(">I", 0))
            else:
                conn.sendall(struct.pack(">I", 0))

            self._recv(conn, 1)  # ClientInit
            pixfmt = struct.pack(">BBBBHHHBBBxxx", 32, 24, 0, 1, 255, 255, 255, 0, 8, 16)
            name = self.display_name.encode()
            conn.sendall(
                struct.pack(">HH", self.width, self.height) + pixfmt
                + struct.pack(">I", len(name)) + name
            )

            while True:
                msg = self._recv(conn, 1)[0]
                if msg == 0:  # SetPixelFormat
                    self._recv(conn, 19)
                elif msg == 2:  # SetEncodings
                    self._recv(conn, 1)
                    (count,) = struct.unpack(">H", self._recv(conn, 2))
                    self._recv(conn, 4 * count)
                elif msg == 3:  # FramebufferUpdateRequest
                    self._recv(conn, 9)
                    self.update_requests += 1
                    if self.update_requests == 1:
                        r, g, b = self.fill
                        pixel = bytes([r, g, b, 0])
                        data = pixel * (self.width * self.height)
                        conn.sendall(
                            struct.pack(">BxH", 0, 1)
                            + struct.pack(">HHHHi", 0, 0, self.width, self.height, ENC_RAW)
                            + data
                        )
                elif msg == 5:  # PointerEvent
                    mask, x, y = struct.unpack(">BHH", self._recv(conn, 5))
                    self.pointer_events.append((mask, x, y))
                elif msg == 4:  # KeyEvent
                    down, _, keysym = struct.unpack(">BHI", self._recv(conn, 7))
                    self.key_events.append((down, keysym))
                else:
                    return
        except (ConnectionError, AssertionError, OSError):
            pass
        finally:
            conn.close()
            self.sock.close()


class Events:
    def __init__(self):
        self.connected = threading.Event()
        self.frame = threading.Event()
        self.closed = threading.Event()
        self.name = None
        self.error = None

    def bind(self, **kw):
        return dict(
            on_connected=lambda n: (setattr(self, "name", n), self.connected.set()),
            on_frame=self.frame.set,
            on_error=lambda m: setattr(self, "error", m),
            on_closed=self.closed.set,
            **kw,
        )


def _connect(server, password=None):
    ev = Events()
    client = VncClient("127.0.0.1", server.port, password, **ev.bind())
    client.start()
    return client, ev


def test_handshake_frame_and_name():
    server = FakeRfbServer(fill=(1, 2, 3))
    server.start()
    client, ev = _connect(server)
    assert ev.connected.wait(timeout=5)
    assert ev.name == "fake-vnc"
    assert ev.frame.wait(timeout=5)
    fb, w, h = client.snapshot()
    assert (w, h) == (8, 4)
    assert bytes(fb[:4]) == bytes([1, 2, 3, 0])
    assert bytes(fb[-4:]) == bytes([1, 2, 3, 0])
    client.close()


def test_vnc_auth_success():
    server = FakeRfbServer(password="s3cret")
    server.start()
    client, ev = _connect(server, password="s3cret")
    assert ev.connected.wait(timeout=5)
    assert ev.error is None
    client.close()


def test_vnc_auth_failure_reports_reason():
    server = FakeRfbServer(password="right")
    server.start()
    client, ev = _connect(server, password="wrong")
    assert ev.closed.wait(timeout=5)
    assert ev.error is not None
    assert "wrong password" in ev.error
    client.close()


def test_missing_password_fails_cleanly():
    server = FakeRfbServer(password="needed")
    server.start()
    client, ev = _connect(server, password=None)
    assert ev.closed.wait(timeout=5)
    assert "password" in (ev.error or "")
    client.close()


def test_pointer_and_key_events_reach_server():
    server = FakeRfbServer()
    server.start()
    client, ev = _connect(server)
    assert ev.frame.wait(timeout=5)
    client.send_pointer(3, 2, 1)
    client.send_key(0xFF0D, True)
    client.send_key(0xFF0D, False)
    deadline = time.time() + 5
    while time.time() < deadline and not (server.pointer_events and len(server.key_events) == 2):
        time.sleep(0.02)
    assert server.pointer_events == [(1, 3, 2)]
    assert server.key_events == [(1, 0xFF0D), (0, 0xFF0D)]
    client.close()


# ----- decoder unit tests (no network) -----

def _client_with_stream(payload: bytes, width: int, height: int) -> VncClient:
    c = VncClient("unused")
    c._resize_fb(width, height)
    stream = io.BytesIO(payload)

    def recv_exact(n):
        data = stream.read(n)
        assert len(data) == n, "decoder over-read"
        return data

    c._recv_exact = recv_exact
    return c


def test_raw_and_copyrect_decoding():
    # 4x2 fb. Rect 1: raw 2x1 at (0,0) = red,green. Rect 2: copyrect that
    # copies those two pixels to (2,1).
    red, green = bytes([255, 0, 0, 0]), bytes([0, 255, 0, 0])
    payload = (
        struct.pack(">xH", 2)
        + struct.pack(">HHHHi", 0, 0, 2, 1, ENC_RAW) + red + green
        + struct.pack(">HHHHi", 2, 1, 2, 1, ENC_COPY_RECT) + struct.pack(">HH", 0, 0)
    )
    c = _client_with_stream(payload, 4, 2)
    c._read_framebuffer_update()
    fb, w, h = c.snapshot()
    px = lambda x, y: bytes(fb[(y * w + x) * 4:(y * w + x) * 4 + 4])
    assert px(0, 0) == red and px(1, 0) == green
    assert px(2, 1) == red and px(3, 1) == green


def test_desktop_size_resizes_framebuffer():
    payload = struct.pack(">xH", 1) + struct.pack(">HHHHi", 0, 0, 16, 9, ENC_DESKTOP_SIZE)
    c = _client_with_stream(payload, 4, 2)
    c._read_framebuffer_update()
    _, w, h = c.snapshot()
    assert (w, h) == (16, 9)


def test_out_of_bounds_rect_is_rejected():
    from core.vnc_client import VncError

    # 2x2 raw rect at (3,1) on a 4x2 framebuffer: x+w and y+h both overflow.
    data = bytes(2 * 2 * 4)
    payload = struct.pack(">xH", 1) + struct.pack(">HHHHi", 3, 1, 2, 2, ENC_RAW) + data
    c = _client_with_stream(payload, 4, 2)
    with pytest.raises(VncError):
        c._read_framebuffer_update()
    # The framebuffer must not have been grown or corrupted.
    fb, w, h = c.snapshot()
    assert len(fb) == w * h * 4


def test_snapshot_returns_consistent_copy():
    c = VncClient("unused")
    c._resize_fb(2, 2)
    fb, w, h = c.snapshot()
    assert isinstance(fb, bytes)
    # Mutating the live framebuffer afterwards must not affect the snapshot.
    c._blit(0, 0, 1, 1, bytes([255, 0, 0, 0]))
    assert fb == bytes(2 * 2 * 4)


# ----- auth primitive -----

def test_reverse_bits():
    assert _reverse_bits(0b00000001) == 0b10000000
    assert _reverse_bits(0b10110000) == 0b00001101
    assert _reverse_bits(0xFF) == 0xFF


def test_auth_response_shape_and_truncation():
    challenge = bytes(range(16))
    r1 = vnc_auth_response("password", challenge)
    assert len(r1) == 16
    # VNC keys are exactly 8 bytes: a longer password is truncated.
    assert vnc_auth_response("passwordEXTRA", challenge) == r1
    assert vnc_auth_response("different", challenge) != r1


# ----- widget layer -----

class FakeKeyEvent:
    def __init__(self, key, text="", modifiers=None):
        from PyQt6.QtCore import Qt

        self._key, self._text = key, text
        self._modifiers = Qt.KeyboardModifier.NoModifier if modifiers is None else modifiers

    def key(self):
        return self._key

    def text(self):
        return self._text

    def modifiers(self):
        return self._modifiers


def test_qt_event_to_keysym(qapp):
    from PyQt6.QtCore import Qt
    from widgets.vnc_viewer import qt_event_to_keysym

    assert qt_event_to_keysym(FakeKeyEvent(Qt.Key.Key_Return)) == 0xFF0D
    assert qt_event_to_keysym(FakeKeyEvent(Qt.Key.Key_A, "a")) == ord("a")
    assert qt_event_to_keysym(FakeKeyEvent(Qt.Key.Key_A, "A")) == ord("A")
    assert qt_event_to_keysym(FakeKeyEvent(0, "€")) == 0x01000000 + ord("€")
    assert qt_event_to_keysym(FakeKeyEvent(0, "")) is None
    # Shift+Tab arrives as Backtab; it must still produce the Tab keysym.
    assert qt_event_to_keysym(FakeKeyEvent(Qt.Key.Key_Backtab)) == 0xFF09


def test_qt_event_to_keysym_ctrl_combinations(qapp):
    """Qt reports Ctrl+letter as a control character ("\\x01" for Ctrl+A);
    the server wants the plain letter keysym next to the Control press."""
    from PyQt6.QtCore import Qt
    from widgets.vnc_viewer import qt_event_to_keysym

    ctrl = Qt.KeyboardModifier.ControlModifier
    assert qt_event_to_keysym(FakeKeyEvent(Qt.Key.Key_A, "\x01", ctrl)) == ord("a")
    assert qt_event_to_keysym(FakeKeyEvent(Qt.Key.Key_C, "\x03", ctrl)) == ord("c")
    shifted = ctrl | Qt.KeyboardModifier.ShiftModifier
    assert qt_event_to_keysym(FakeKeyEvent(Qt.Key.Key_A, "\x01", shifted)) == ord("A")
    # Ctrl+digit can report empty text but still carries an ASCII key code.
    assert qt_event_to_keysym(FakeKeyEvent(Qt.Key.Key_2, "", ctrl)) == ord("2")


def test_viewer_connects_and_paints(qapp):
    from PyQt6.QtWidgets import QApplication
    from widgets.vnc_viewer import VncViewer

    server = FakeRfbServer(fill=(9, 8, 7))
    server.start()
    viewer = VncViewer("127.0.0.1", server.port)
    deadline = time.time() + 5
    while time.time() < deadline and viewer._status is not None:
        QApplication.processEvents()
        time.sleep(0.01)
    assert viewer._status is None, f"viewer never connected: {viewer._status}"
    fb, w, h = viewer.client.snapshot()
    assert (w, h) == (8, 4)
    viewer.resize(400, 300)
    viewer.repaint()  # exercise paintEvent offscreen
    viewer.shutdown()


def test_session_dialog_vnc_round_trip(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog()
    dlg.proto_tabs.setCurrentWidget(dlg.vnc_tab)
    dlg.vnc_host_input.setText("view.example.com")
    dlg.vnc_port_input.setText("5901")
    data = dlg.get_data()
    assert data["type"] == "VNC"
    assert data["host"] == "view.example.com"
    assert data["port"] == "5901"

    dlg2 = SessionDialog(session=data)
    assert dlg2.proto_tabs.currentWidget() is dlg2.vnc_tab
    assert dlg2.vnc_host_input.text() == "view.example.com"
    assert dlg2.vnc_port_input.text() == "5901"


def test_session_activation_routes_vnc(qapp):
    from bifrost_app import BifrostApp

    app = BifrostApp.__new__(BifrostApp)
    received = {}
    app.open_vnc_session = lambda session: received.update(session)
    BifrostApp.on_session_activated(
        app, {"name": "viewer", "type": "VNC", "host": "h", "port": "5901"},
    )
    assert received["host"] == "h"
    assert received["port"] == "5901"


def test_tab_is_live_counts_vnc_viewer(qapp):
    from bifrost_app import BifrostApp
    from widgets.vnc_viewer import VncViewer

    server = FakeRfbServer()
    server.start()
    app = BifrostApp.__new__(BifrostApp)
    viewer = VncViewer("127.0.0.1", server.port)
    # Live while connecting/connected → close confirmation and the quit
    # session count must include it.
    assert BifrostApp._tab_is_live(app, viewer)
    viewer.shutdown()
    assert not BifrostApp._tab_is_live(app, viewer)


def test_quick_connect_vnc_routes(qapp):
    from bifrost_app import BifrostApp

    app = BifrostApp.__new__(BifrostApp)
    received = {}
    app.open_vnc_session = lambda session: received.update(session)
    BifrostApp.on_quick_connect(app, "VNC", "host.example.com:5901")
    assert received["host"] == "host.example.com"
    assert received["port"] == "5901"

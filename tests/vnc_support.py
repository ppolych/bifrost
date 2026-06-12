import socket
import struct
import threading

from core.vnc_client import ENC_RAW, SEC_NONE, SEC_VNC_AUTH, VncClient, vnc_auth_response


class FakeRfbServer(threading.Thread):
    """Single-connection RFB 3.8 server used by VNC tests."""

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
                if msg == 0:
                    self._recv(conn, 19)
                elif msg == 2:
                    self._recv(conn, 1)
                    (count,) = struct.unpack(">H", self._recv(conn, 2))
                    self._recv(conn, 4 * count)
                elif msg == 3:
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
                elif msg == 5:
                    mask, x, y = struct.unpack(">BHH", self._recv(conn, 5))
                    self.pointer_events.append((mask, x, y))
                elif msg == 4:
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


def connect(server, password=None):
    ev = Events()
    client = VncClient("127.0.0.1", server.port, password, **ev.bind())
    client.start()
    return client, ev

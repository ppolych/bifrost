"""Serial-port terminal backend (pyserial).

Same public surface as `core.terminal_backend.TerminalBackend` so
`TerminalReader` and `TerminalWidget` can use it interchangeably.

pyserial is an optional dependency (like pywinpty on Windows): it is imported
lazily in the connect thread, and a missing install surfaces as a connect
error rendered in the terminal rather than an import crash at startup.
"""

from __future__ import annotations

import logging
import threading
from typing import Optional

log = logging.getLogger(__name__)


class SerialBackend:
    """Serial backend with the same surface as TerminalBackend."""

    def __init__(self, device: str, baudrate: int = 115200):
        self.device = device
        self.baudrate = int(baudrate)

        self._ser = None
        self._ready = threading.Event()
        self._connect_error: Optional[BaseException] = None
        self._error_emitted = False
        self._closed = False

    # ----- lifecycle -----

    def start(self):
        threading.Thread(target=self._connect, name="serial-connect", daemon=True).start()

    def _connect(self):
        try:
            try:
                import serial
            except ImportError as e:
                raise RuntimeError(
                    "pyserial is required for Serial sessions. Install it with `pip install pyserial`."
                ) from e
            # timeout=None: read() blocks until at least one byte arrives,
            # which is what TerminalReader expects (b"" means EOF).
            self._ser = serial.Serial(self.device, self.baudrate, timeout=None)
        except BaseException as e:
            log.warning("Serial open %s @%s failed: %s", self.device, self.baudrate, e)
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
                return f"Opening {self.device} @{self.baudrate}...\r\n".encode()

        if self._connect_error is not None and not self._error_emitted:
            self._error_emitted = True
            return f"\r\n\x1b[31m[connection failed: {self._connect_error}]\x1b[0m\r\n".encode()

        ser = self._ser
        if ser is None:
            return b""

        try:
            # Block for the first byte, then drain whatever else is buffered.
            data = ser.read(1)
            waiting = getattr(ser, "in_waiting", 0)
            if data and waiting:
                data += ser.read(min(waiting, size - 1))
        except Exception as e:  # serial.SerialException, OSError on close
            log.debug("serial read failed: %s", e)
            return b""
        return data or b""

    def write(self, data) -> None:
        if self._closed or self._ser is None:
            return
        if isinstance(data, str):
            data = data.encode()
        try:
            self._ser.write(data)
        except Exception:
            log.debug("serial write failed", exc_info=True)

    def set_winsize(self, rows: int, cols: int) -> None:
        # Serial lines have no window-size concept.
        pass

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        ser = self._ser
        self._ser = None
        if ser is not None:
            try:
                # Unblock a reader stuck in read(1) before closing.
                cancel = getattr(ser, "cancel_read", None)
                if cancel is not None:
                    cancel()
                ser.close()
            except Exception:
                log.debug("serial close failed", exc_info=True)

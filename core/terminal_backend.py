import os
import subprocess
import sys

from PyQt6.QtCore import QThread, pyqtSignal

IS_WINDOWS = sys.platform == "win32"


class TerminalBackend:
    """PTY abstraction.

    POSIX: pty.fork() + os.read/os.write on the master fd.
    Windows: pywinpty (ConPTY). Install with `pip install pywinpty`.

    Use TerminalReader to consume output asynchronously; do not call read() from
    the GUI thread.
    """

    def __init__(self, command=None):
        self.command = self._normalize_command(command)
        self.fd = None
        self.pid = None
        self._winpty = None
        self._closed = False

    def _get_default_shell(self):
        if IS_WINDOWS:
            return ["cmd.exe"]
        return [os.environ.get("SHELL", "/bin/bash")]

    def _normalize_command(self, command) -> list[str] | str:
        if command is None:
            return self._get_default_shell()
        if isinstance(command, str):
            return command if IS_WINDOWS else [command]
        return [str(part) for part in command]

    def _windows_cmdline(self) -> str:
        if isinstance(self.command, str):
            return self.command
        return subprocess.list2cmdline(self.command)

    def start(self):
        if not IS_WINDOWS:
            import pty
            self.pid, self.fd = pty.fork()
            if self.pid == 0:
                os.environ["TERM"] = "xterm-256color"
                try:
                    os.execvp(self.command[0], self.command)
                except FileNotFoundError:
                    os.write(2, f"bifrost: command not found: {self.command[0]}\r\n".encode())
                    os._exit(127)
                except Exception as e:
                    os.write(2, f"bifrost: failed to exec {self.command[0]}: {e}\r\n".encode())
                    os._exit(126)
        else:
            try:
                from winpty import PtyProcess
            except ImportError as e:
                raise RuntimeError(
                    "pywinpty is required on Windows. Install it with `pip install pywinpty`."
                ) from e
            self._winpty = PtyProcess.spawn(self._windows_cmdline())
            self.pid = self._winpty.pid

    def read(self, size=4096):
        if self._closed:
            return b""
        if not IS_WINDOWS:
            return os.read(self.fd, size)
        try:
            chunk = self._winpty.read(size)
        except EOFError:
            return b""
        if chunk is None:
            return b""
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8", errors="replace")
        return chunk

    def write(self, data):
        if self._closed:
            return
        if not IS_WINDOWS:
            os.write(self.fd, data)
        else:
            if self._winpty is None:
                return
            if isinstance(data, bytes):
                data = data.decode("utf-8", errors="replace")
            self._winpty.write(data)

    def set_winsize(self, rows, cols):
        if not IS_WINDOWS:
            if self.fd is None:
                return
            import fcntl
            import termios
            import struct
            s = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.fd, termios.TIOCSWINSZ, s)
        elif self._winpty is not None:
            try:
                self._winpty.setwinsize(rows, cols)
            except Exception:
                pass

    def close(self):
        if self._closed:
            return
        self._closed = True
        try:
            if not IS_WINDOWS:
                if self.fd is not None:
                    os.close(self.fd)
            elif self._winpty is not None:
                self._winpty.terminate(force=True)
        except OSError:
            pass


class TerminalReader(QThread):
    """Reads bytes from a TerminalBackend off the GUI thread and emits them.

    Uniform across platforms — replaces QSocketNotifier, which can't watch
    pipe HANDLEs on Windows.
    """

    data_received = pyqtSignal(bytes)
    closed = pyqtSignal()

    def __init__(self, backend, parent=None):
        super().__init__(parent)
        self.backend = backend
        self._stop = False

    def run(self):
        while not self._stop:
            try:
                data = self.backend.read(4096)
            except OSError:
                break
            if not data:
                break
            self.data_received.emit(data)
        self.closed.emit()

    def stop(self):
        self._stop = True
        self.backend.close()
        self.wait(1000)

"""A silent POSIX descriptor must not keep terminal shutdown blocked."""

import os
import threading

import pytest

from core.terminal_backend import IS_WINDOWS, TerminalBackend, TerminalReader


@pytest.mark.skipif(IS_WINDOWS, reason="POSIX descriptor read")
def test_stop_reader_while_descriptor_is_silent(qapp, monkeypatch):
    backend = TerminalBackend()
    backend.fd, writer = os.pipe()
    entered = threading.Event()
    original_read = backend.read

    def read(size):
        entered.set()
        return original_read(size)

    monkeypatch.setattr(backend, "read", read)
    reader = TerminalReader(backend)
    reader.start()
    try:
        assert entered.wait(1)
        assert not reader.wait(100)  # allow the read to block on the silent pipe
        reader.stop()
        assert not reader.isRunning()
    finally:
        # Also unblock the old implementation when this regression fails.
        os.close(writer)
        backend.close()
        reader.wait(2000)

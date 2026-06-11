"""Serial backend: lifecycle with a fake pyserial, and session-dialog/routing
integration. pyserial itself is not required to run these."""

import sys
import threading
import types

import pytest

from core.serial_backend import SerialBackend


class FakeSerial:
    """Stands in for serial.Serial: scripted reads, recorded writes."""

    def __init__(self, device, baudrate, timeout=None):
        self.device = device
        self.baudrate = baudrate
        self.written = []
        self.closed = False
        self._chunks = [b"BIOS v1.0\r\n"]
        self._data_ready = threading.Event()
        self._data_ready.set()
        self.in_waiting = 0

    def read(self, size):
        if self.closed:
            raise OSError("port closed")
        if self._chunks:
            chunk = self._chunks.pop(0)
            return chunk[:size] if size > 1 else chunk[:1] + self._stash(chunk[1:])
        raise OSError("no more data")

    def _stash(self, rest):
        if rest:
            self._chunks.insert(0, rest)
            self.in_waiting = len(rest)
        return b""

    def write(self, data):
        self.written.append(data)

    def close(self):
        self.closed = True


@pytest.fixture
def fake_serial_module(monkeypatch):
    mod = types.ModuleType("serial")
    mod.Serial = FakeSerial
    monkeypatch.setitem(sys.modules, "serial", mod)
    return mod


def test_open_read_write_close(fake_serial_module):
    b = SerialBackend("/dev/ttyUSB0", 9600)
    b.start()
    assert b._ready.wait(timeout=5)
    assert b._connect_error is None
    assert b._ser.device == "/dev/ttyUSB0"
    assert b._ser.baudrate == 9600

    out = b.read()
    assert out.startswith(b"B")  # first blocking byte
    b.write("reboot\r")
    assert b._ser.written == [b"reboot\r"]

    ser = b._ser
    b.close()
    assert ser.closed
    assert b.read() == b""


def test_missing_pyserial_renders_in_terminal(monkeypatch):
    monkeypatch.setitem(sys.modules, "serial", None)  # force ImportError
    b = SerialBackend("/dev/ttyUSB0")
    b.start()
    assert b._ready.wait(timeout=5)
    assert b._connect_error is not None
    out = b.read()
    assert b"connection failed" in out
    assert b"pyserial" in out
    assert b.read() == b""


def test_open_failure_renders_in_terminal(fake_serial_module):
    def boom(*a, **k):
        raise OSError("could not open port")

    fake_serial_module.Serial = boom
    b = SerialBackend("/dev/nope")
    b.start()
    assert b._ready.wait(timeout=5)
    assert b"could not open port" in b.read()


def test_session_dialog_serial_round_trip(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog()
    dlg.proto_tabs.setCurrentWidget(dlg.serial_tab)
    dlg.serial_device_input.setText("/dev/ttyUSB1")
    dlg.serial_baud_combo.setCurrentText("57600")
    data = dlg.get_data()
    assert data["type"] == "Serial"
    assert data["device"] == "/dev/ttyUSB1"
    assert data["baudrate"] == "57600"
    assert data["name"] == "/dev/ttyUSB1 @57600"

    # And back: editing the saved session restores the fields.
    dlg2 = SessionDialog(session=data)
    assert dlg2.proto_tabs.currentWidget() is dlg2.serial_tab
    assert dlg2.serial_device_input.text() == "/dev/ttyUSB1"
    assert dlg2.serial_baud_combo.currentText() == "57600"


def test_session_activation_routes_serial(qapp):
    from bifrost_app import BifrostApp

    app = BifrostApp.__new__(BifrostApp)
    received = {}
    app.new_terminal_tab = lambda name, **k: received.update(k, name=name)
    BifrostApp.on_session_activated(
        app, {"name": "console", "type": "Serial", "device": "/dev/ttyS0", "baudrate": "9600"},
    )
    assert received["kind"] == "Serial"
    assert received["device"] == "/dev/ttyS0"
    assert received["baud"] == 9600


def test_session_dialog_telnet_round_trip(qapp):
    from widgets.session_dialog import SessionDialog

    dlg = SessionDialog()
    dlg.proto_tabs.setCurrentWidget(dlg.telnet_tab)
    dlg.telnet_host_input.setText("bbs.example.com")
    dlg.telnet_port_input.setText("2323")
    data = dlg.get_data()
    assert data["type"] == "Telnet"
    assert data["host"] == "bbs.example.com"
    assert data["port"] == "2323"

    dlg2 = SessionDialog(session=data)
    assert dlg2.proto_tabs.currentWidget() is dlg2.telnet_tab
    assert dlg2.telnet_host_input.text() == "bbs.example.com"
    assert dlg2.telnet_port_input.text() == "2323"

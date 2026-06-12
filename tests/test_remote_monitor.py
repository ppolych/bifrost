from core.remote_monitor import (
    format_bytes,
    format_rate,
    format_remote_monitor_details,
    parse_remote_monitor_output,
)


def test_parse_remote_monitor_output():
    parsed = parse_remote_monitor_output(
        "\n".join(
            [
                "host=prod",
                "cpu=12%",
                "mem=0.91/7.56 GB",
                "uptime=up 36 hours",
                "disk=/:89%",
                "disk=/tmp:2%",
                "net=1000 2000",
            ]
        )
    )

    assert parsed["host"] == "prod"
    assert parsed["cpu"] == "12%"
    assert parsed["mem"] == "0.91/7.56 GB"
    assert parsed["disk"] == ["/:89%", "/tmp:2%"]
    assert parsed["net"] == (1000, 2000)


def test_format_rate():
    assert format_rate(0) == "0 B/s"
    assert format_rate(1024) == "1.00 KB/s"
    assert format_rate(1024 * 1024) == "1.00 MB/s"


def test_format_bytes():
    assert format_bytes(0) == "0 B"
    assert format_bytes(1024) == "1.00 KB"
    assert format_bytes(1024 * 1024) == "1.00 MB"


def test_format_remote_monitor_details():
    details = format_remote_monitor_details(
        {
            "host": "prod",
            "cpu": "12%",
            "mem": "0.91/7.56 GB",
            "uptime": "up 36 hours",
            "disk": ["/:89%", "/tmp:2%"],
        },
        down_rate=2048,
        up_rate=1024,
    )

    assert "Host: prod" in details
    assert "Network down: 2.00 KB/s" in details
    assert "Network up: 1.00 KB/s" in details
    assert "Uptime: 36 hours" in details
    assert "  /:89%" in details


def test_remote_monitor_health_helpers():
    from core.remote_monitor_health import (
        disk_worst_percent,
        freshness_text,
        health_color,
        is_stale,
        percent_value,
    )

    assert percent_value("CPU 96%") == 96
    assert disk_worst_percent(["/:70%", "/var:91%"]) == 91
    assert health_color(96) == "#ef4444"
    assert health_color(81) == "#f59e0b"
    assert freshness_text(10, now=13) == "updated 3s ago"
    assert is_stale(0, 5000, now=11) is True


def test_remote_monitor_widget_details_and_pause(qapp):
    from widgets.remote_monitor import RemoteMonitorWidget

    widget = RemoteMonitorWidget()
    class Backend:
        def wait_ready(self, timeout=0):
            return False

    backend = Backend()
    widget.set_backend(backend)
    widget._apply_metrics(backend, {
        "host": "prod",
        "cpu": "96%",
        "mem": "81%",
        "uptime": "up 1 hour",
        "disk": ["/:70%"],
    })

    assert "Host: prod" in widget.details_text()
    assert widget.cpu_label.styleSheet().find("#ef4444") >= 0
    assert widget.mem_label.styleSheet().find("#f59e0b") >= 0

    widget.toggle_pause()

    assert widget.paused is True
    assert "paused" in widget.fresh_label.text()


def test_remote_monitor_context_signal(qapp):
    from widgets.remote_monitor import RemoteMonitorWidget

    widget = RemoteMonitorWidget()
    received = []
    widget.remote_ops_requested.connect(lambda: received.append(True))

    widget.remote_ops_requested.emit()

    assert received == [True]

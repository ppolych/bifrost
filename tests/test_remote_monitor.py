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

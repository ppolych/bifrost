from core.remote_monitor import format_rate, parse_remote_monitor_output


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

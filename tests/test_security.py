import logging


def test_sanitize_for_export_removes_nested_secret_fields():
    from core.security import sanitize_for_export

    data = {
        "group": [
            {
                "name": "prod",
                "host": "h",
                "password": "secret",
                "nested": {"token": "secret", "keep": "yes"},
            }
        ]
    }

    cleaned = sanitize_for_export(data)
    session = cleaned["group"][0]
    assert session["host"] == "h"
    assert "password" not in session
    assert "token" not in session["nested"]
    assert session["nested"]["keep"] == "yes"


def test_redacting_formatter_masks_secret_values():
    from core.logging_setup import RedactingFormatter

    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "password=%s port=%d",
        ("supersecret", 22),
        None,
    )
    formatter = RedactingFormatter("%(message)s")

    assert formatter.format(record) == "password=<redacted> port=22"

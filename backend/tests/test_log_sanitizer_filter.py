import logging

from security.log_sanitizer import SanitizedLogFilter


def test_parameterized_sensitive_field_is_rendered_and_redacted_safely():
    record = logging.LogRecord(
        name="test",
        level=logging.WARNING,
        pathname=__file__,
        lineno=1,
        msg="tenant mismatch: user=%s jwt=%s doc=%s",
        args=("user-1", "tenant-forged", "tenant-real"),
        exc_info=None,
    )

    assert SanitizedLogFilter().filter(record) is True
    assert record.args == ()
    assert "user-1" not in record.getMessage()
    assert record.getMessage() == (
        "tenant mismatch: user=***REDACTED*** jwt=tenant-forged doc=tenant-real"
    )

from datetime import UTC, datetime, timedelta

from tests.integration.test_nilvera_create_return_reconciliation_v2 import (
    _extract_creation_time,
    _select_exact_write_window_match,
)


def test_extract_creation_time_reads_nested_provider_creation_field():
    payload = {"Metadata": {"CreatedAt": "2026-08-13T07:20:43Z"}}

    assert _extract_creation_time(payload) == datetime(2026, 8, 13, 7, 20, 43, tzinfo=UTC)


def test_exact_write_window_selects_only_recent_matching_return():
    write_time = datetime(2026, 8, 13, 7, 20, 43, tzinfo=UTC)
    matches = [
        (
            "11111111-1111-1111-1111-111111111111",
            {"InvoiceType": "IADE"},
            {"CreatedAt": "2026-08-12T10:00:00Z"},
        ),
        (
            "22222222-2222-2222-2222-222222222222",
            {"InvoiceType": "IADE"},
            {"CreatedAt": "2026-08-13T07:20:45Z"},
        ),
    ]

    selected = _select_exact_write_window_match(matches, write_time=write_time)

    assert selected == ("22222222-2222-2222-2222-222222222222", {"InvoiceType": "IADE"})


def test_exact_write_window_fails_closed_when_two_matches_are_recent():
    write_time = datetime(2026, 8, 13, 7, 20, 43, tzinfo=UTC)
    matches = [
        (
            "11111111-1111-1111-1111-111111111111",
            {"InvoiceType": "IADE"},
            {"CreatedAt": "2026-08-13T07:20:40Z"},
        ),
        (
            "22222222-2222-2222-2222-222222222222",
            {"InvoiceType": "IADE"},
            {"CreatedAt": "2026-08-13T07:20:45Z"},
        ),
    ]

    assert _select_exact_write_window_match(matches, write_time=write_time) is None


def test_exact_write_window_fails_closed_without_creation_timestamp():
    write_time = datetime(2026, 8, 13, 7, 20, 43, tzinfo=UTC)
    matches = [
        (
            "11111111-1111-1111-1111-111111111111",
            {"InvoiceType": "IADE"},
            {"IssueDate": "2026-08-13T07:20:43Z"},
        )
    ]

    assert _select_exact_write_window_match(
        matches,
        write_time=write_time,
        tolerance=timedelta(minutes=10),
    ) is None

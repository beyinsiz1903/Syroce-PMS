from datetime import UTC, date, datetime

from routers.reservation_detail import _reservation_calendar_date


def test_reservation_calendar_date_accepts_provider_and_legacy_formats():
    assert _reservation_calendar_date("2026-08-26T14:00:00Z") == date(2026, 8, 26)
    assert _reservation_calendar_date("2026-08-26") == date(2026, 8, 26)
    assert _reservation_calendar_date(datetime(2026, 8, 26, 14, tzinfo=UTC)) == date(2026, 8, 26)
    assert _reservation_calendar_date(date(2026, 8, 26)) == date(2026, 8, 26)


def test_reservation_calendar_date_rejects_bad_legacy_values_without_raising():
    assert _reservation_calendar_date("not-a-date") is None
    assert _reservation_calendar_date(12345) is None
    assert _reservation_calendar_date("") is None
    assert _reservation_calendar_date(None) is None

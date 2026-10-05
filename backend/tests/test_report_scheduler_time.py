from datetime import UTC, datetime

from routers.report_scheduler import _compute_next_run


def test_daily_schedule_uses_hotel_local_time():
    now = datetime(2026, 9, 24, 4, 0, tzinfo=UTC)  # 07:00 Europe/Istanbul

    assert _compute_next_run("daily", "08:00", None, None, now_utc=now) == "2026-09-24T05:00:00+00:00"


def test_weekly_schedule_can_still_run_later_on_the_same_local_day():
    now = datetime(2026, 9, 24, 4, 0, tzinfo=UTC)  # Thursday, 07:00 local

    assert _compute_next_run("weekly", "08:00", "thursday", None, now_utc=now) == "2026-09-24T05:00:00+00:00"


def test_weekly_schedule_moves_to_next_week_after_local_send_time():
    now = datetime(2026, 9, 24, 6, 0, tzinfo=UTC)  # Thursday, 09:00 local

    assert _compute_next_run("weekly", "08:00", "thursday", None, now_utc=now) == "2026-10-01T05:00:00+00:00"

from types import SimpleNamespace

import pytest

from routers.departments import reports


class _Cursor:
    def __init__(self):
        self.limits = []

    async def to_list(self, limit):
        self.limits.append(limit)
        return []


@pytest.mark.asyncio
async def test_market_segment_report_does_not_truncate_booking_history(monkeypatch):
    cursor = _Cursor()
    monkeypatch.setattr(reports, "db", SimpleNamespace(bookings=SimpleNamespace(find=lambda *_args, **_kwargs: cursor)))

    result = await reports.get_market_segment_report(
        "2026-09-01",
        "2026-09-30",
        current_user=SimpleNamespace(tenant_id="tenant-a"),
        _perm=None,
        _nocache=True,
    )

    assert cursor.limits == [None]
    assert result["total_bookings"] == 0

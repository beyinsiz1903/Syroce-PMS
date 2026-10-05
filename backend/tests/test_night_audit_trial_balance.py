import os

os.environ.setdefault("JWT_SECRET", "test-secret-key-that-is-long-enough-for-tests")

from domains.pms.night_audit_router import _daily_revenue_summary


def test_daily_revenue_uses_accrual_before_room_posting():
    result = _daily_revenue_summary(
        [{"date": "2026-10-01", "occupied_rooms": 5, "sold_rooms": 5, "total_rooms": 17, "revenue": 5000}],
        [{"_id": "fnb", "total": 750}],
    )

    assert result["rooms"] == 5000
    assert result["fnb"] == 750
    assert result["total"] == 5750
    assert result["adr"] == 1000
    assert result["revpar"] == 294.12
    assert result["room_revenue_source"] == "accrued"
    assert result["posting_pending"] is True


def test_daily_revenue_prefers_posted_rooms_after_night_audit():
    result = _daily_revenue_summary(
        [{"date": "2026-10-01", "occupied_rooms": 2, "sold_rooms": 2, "total_rooms": 10, "revenue": 4800}],
        [
            {"_id": "room", "total": 5000},
            {"_id": "beverage", "total": 300},
        ],
    )

    assert result["rooms"] == 5000
    assert result["fnb"] == 300
    assert result["total"] == 5300
    assert result["adr"] == 2500
    assert result["revpar"] == 500
    assert result["by_category"] == {"beverage": 300}
    assert result["room_revenue_source"] == "posted"
    assert result["posting_pending"] is False


def test_daily_revenue_does_not_duplicate_room_category_rows():
    result = _daily_revenue_summary(
        [],
        [{"_id": "rooms", "total": 1000}, {"_id": "spa", "total": 200}],
    )

    assert result["rooms"] == 1000
    assert result["other"] == 200
    assert result["by_category"] == {"spa": 200}


def test_daily_revenue_excludes_complimentary_rooms_from_adr_denominator():
    result = _daily_revenue_summary(
        [{"date": "2026-10-01", "occupied_rooms": 6, "sold_rooms": 3, "total_rooms": 17, "revenue": 9500}],
        [],
    )

    assert result["adr"] == 3166.67
    assert result["revpar"] == 558.82

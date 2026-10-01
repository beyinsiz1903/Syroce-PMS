from domains.revenue.rms_router.pricing_strategy import (
    _active_pending_query,
    _dedupe_recommendations,
)


def test_active_pending_query_excludes_historical_dates():
    assert _active_pending_query("tenant-1", "2026-10-01") == {
        "tenant_id": "tenant-1",
        "status": "pending",
        "date": {"$gte": "2026-10-01"},
    }


def test_dedupe_recommendations_keeps_newest_per_date_and_room_type():
    recommendations = [
        {"id": "old", "date": "2026-10-02", "room_type": "Standard", "generated_at": "2026-10-01T08:00:00Z"},
        {"id": "suite", "date": "2026-10-02", "room_type": "Suite", "generated_at": "2026-10-01T08:30:00Z"},
        {"id": "new", "date": "2026-10-02", "room_type": "Standard", "generated_at": "2026-10-01T09:00:00Z"},
    ]

    result = _dedupe_recommendations(recommendations)

    assert [item["id"] for item in result] == ["new", "suite"]

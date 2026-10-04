from datetime import UTC, datetime, timedelta

from domains.channel_manager.channel_connections_router import build_channel_operational_status

NOW = datetime(2026, 10, 4, 12, 0, tzinfo=UTC)


def _provider(**overrides):
    provider = {
        "connected": True,
        "room_mappings_count": 2,
        "auto_sync_reservations": True,
        "sync_interval_minutes": 15,
        "environment": "production",
    }
    provider.update(overrides)
    return provider


def test_channel_lifecycle_requires_real_production_evidence():
    assert build_channel_operational_status({"connected": False}, now=NOW)["key"] == "setup_pending"
    assert build_channel_operational_status(_provider(room_mappings_count=0), now=NOW)["key"] == "mapping_required"
    assert build_channel_operational_status(_provider(auto_sync_reservations=False), now=NOW)["key"] == "paused"
    assert build_channel_operational_status(_provider(), now=NOW)["key"] == "first_sync_pending"


def test_channel_lifecycle_distinguishes_fresh_stale_and_failed_syncs():
    fresh = (NOW - timedelta(minutes=10)).isoformat()
    stale = (NOW - timedelta(minutes=61)).isoformat()
    failed = (NOW - timedelta(minutes=2)).isoformat()

    production = build_channel_operational_status(_provider(last_successful_sync=fresh), now=NOW)
    assert production["key"] == "production"
    assert production["production_ready"] is True
    sandbox = build_channel_operational_status(
        _provider(last_successful_sync=fresh, environment="sandbox"), now=NOW
    )
    assert sandbox["key"] == "sandbox"
    assert sandbox["production_ready"] is False
    assert build_channel_operational_status(_provider(last_successful_sync=stale), now=NOW)["key"] == "stale"
    assert build_channel_operational_status(
        _provider(last_successful_sync=fresh, last_error="HTTP 500", last_error_at=failed), now=NOW
    )["key"] == "error"

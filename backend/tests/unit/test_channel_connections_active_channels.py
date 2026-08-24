from types import SimpleNamespace

import pytest

from domains.channel_manager import channel_connections_router as connections
from domains.channel_manager.providers.hotelrunner import factory


class _UpdateCollection:
    def __init__(self):
        self.calls = []

    async def update_one(self, query, update):
        self.calls.append((query, update))


def test_normalize_active_channels_filters_catalog_and_inactive_records():
    channels = [
        "HotelRunner catalogue entry",
        {"code": "booking", "name": "Booking.com", "status": "active"},
        {"code": "expedia", "name": "Expedia", "status": "enabled"},
        {"code": "agoda", "name": "Agoda", "status": "connected"},
        {"code": "hrs", "name": "HRS", "status": "inactive"},
        {"code": "booking", "name": "Booking duplicate", "active": True},
    ]

    result = connections.normalize_active_hotelrunner_channels(channels)

    assert result == [
        {"code": "booking", "name": "Booking.com", "status": "active"},
        {"code": "expedia", "name": "Expedia", "status": "enabled"},
    ]


def test_normalize_active_channels_supports_nested_provider_flags():
    channels = [
        {"raw": {"code": "ets", "name": "Etstur", "is_active": True}},
        {"raw": {"code": "otelz", "name": "Otelz", "state": "live"}},
        {"raw": {"code": "airbnb", "name": "Airbnb", "state": "disabled"}},
    ]

    assert connections.normalize_active_hotelrunner_channels(channels) == [
        {"code": "ets", "name": "Etstur", "status": "active"},
        {"code": "otelz", "name": "Otelz", "status": "live"},
    ]


@pytest.mark.asyncio
async def test_active_channels_refresh_uses_connected_endpoint_and_caches_verified_list(monkeypatch):
    class _Provider:
        async def get_connected_channels(self):
            return {
                "success": True,
                "data": {
                    "connected_channels": [
                        # The documented HotelRunner connected-channel payload
                        # has no status field; endpoint membership is the proof.
                        {"code": "booking", "name": "Booking.com"},
                        {"code": "airbnb", "name": "Airbnb", "status": "inactive"},
                    ]
                },
            }

    async def _get_provider(_tenant_id):
        return _Provider(), {}

    collection = _UpdateCollection()
    monkeypatch.setattr(factory, "get_provider", _get_provider)
    monkeypatch.setattr(connections, "db", SimpleNamespace(hotelrunner_connections=collection))

    active, stale, refreshed_at = await connections._load_active_hotelrunner_channels(
        "tenant-1",
        {"is_active": True, "channels": ["full catalogue"]},
    )

    assert active == [{"code": "booking", "name": "Booking.com", "status": "active"}]
    assert stale is False
    assert refreshed_at
    cached = collection.calls[0][1]["$set"]["connected_channels"]
    assert cached == active


@pytest.mark.asyncio
async def test_active_channels_refresh_failure_never_falls_back_to_catalog(monkeypatch):
    async def _get_provider(_tenant_id):
        raise RuntimeError("provider unavailable")

    monkeypatch.setattr(factory, "get_provider", _get_provider)

    active, stale, refreshed_at = await connections._load_active_hotelrunner_channels(
        "tenant-1",
        {
            "is_active": True,
            "channels": ["Booking.com", "Expedia", "all catalogue entries"],
            "connected_channels": [
                {"code": "booking", "name": "Booking.com", "status": "active"},
                {"code": "airbnb", "name": "Airbnb", "status": "inactive"},
            ],
            "connected_channels_refreshed_at": "2026-08-24T10:00:00+00:00",
        },
    )

    assert active == [{"code": "booking", "name": "Booking.com", "status": "active"}]
    assert stale is True
    assert refreshed_at == "2026-08-24T10:00:00+00:00"

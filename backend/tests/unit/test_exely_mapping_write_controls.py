from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from domains.channel_manager import unified_rate_manager_router as unified
from domains.channel_manager.ari import outbound_service
from domains.channel_manager.providers.exely.exely_router import (
    ExelyConnectionSetup,
    ExelyRoomMapping,
    _connection_endpoint,
    update_room_mapping,
)
from domains.channel_manager.providers.exely.security import (
    EXELY_PRODUCTION_ENDPOINT_URL,
    EXELY_TEST_ENDPOINT_URL,
)
from domains.channel_manager.rate_manager_router import RateUpdateRequest, _mapping_values


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _length):
        return self.rows


class _Collection:
    def __init__(self, *, row=None, rows=None):
        self.find_one = AsyncMock(return_value=row)
        self.rows = rows or []

    def find(self, *_args, **_kwargs):
        return _Cursor(self.rows)


def test_exely_connection_environment_is_explicit_and_preserves_production_api_default():
    base = {
        "username": "synthetic-user",
        "password": "synthetic-password",
        "hotel_code": "501694",
    }

    assert ExelyConnectionSetup(**base).mode == "production"
    assert ExelyConnectionSetup(**base, mode="sandbox").mode == "sandbox"


@pytest.mark.asyncio
async def test_mapping_edit_preserves_identity_and_separates_inbound_api_codes(monkeypatch):
    existing = {"id": "mapping-1", "tenant_id": "tenant-1", "pms_room_type": "Standard",
                "exely_room_code": "5001574", "exely_rate_plan_code": "10003870"}
    collection = SimpleNamespace(
        find_one=AsyncMock(side_effect=[existing, None, None]),
        update_one=AsyncMock(),
    )
    monkeypatch.setattr("domains.channel_manager.providers.exely.exely_router.db",
                        SimpleNamespace(exely_room_mappings=collection))
    payload = ExelyRoomMapping(
        pms_room_type="Standard", exely_room_code="5003299", exely_rate_plan_code="10009740",
        exely_room_name="Standart", pms_api_room_code="5001574", pms_api_rate_plan_code="10003870",
        sync_availability=True, sync_price=True, sync_restrictions=True,
    )

    result = await update_room_mapping("mapping-1", payload,
                                       current_user=SimpleNamespace(tenant_id="tenant-1", name="Operator"), _perm=True)

    assert result["mapping"]["id"] == "mapping-1"
    fields = collection.update_one.await_args.args[1]["$set"]
    assert fields["exely_room_code"] == "5003299"
    assert fields["pms_api_room_code"] == "5001574"
    assert fields["exely_rate_plan_code"] == "10009740"
    assert fields["pms_api_rate_plan_code"] == "10003870"


@pytest.mark.asyncio
async def test_exely_rate_grid_uses_verified_ari_ids_not_discovered_api_aliases(monkeypatch):
    mapping = {
        "pms_room_type": "Standard", "exely_room_code": "5003299",
        "exely_rate_plan_code": "10009740", "exely_room_name": "Standart",
        "pms_api_room_code": "5001574", "pms_api_rate_plan_code": "10003870",
    }
    monkeypatch.setattr(unified, "db", SimpleNamespace(
        exely_room_mappings=_Collection(rows=[mapping]),
        rate_calendar=_Collection(rows=[]),
        pricing_settings=_Collection(rows=[]),
    ))
    monkeypatch.setattr(unified, "_get_room_counts", AsyncMock(return_value=({"Standard": {"total": 8, "available": 8}}, {"Standard": []})))
    monkeypatch.setattr(unified, "_get_active_bookings", AsyncMock(return_value=[]))
    connection = {
        "currency": "USD",
        "room_types": [{"code": "5001574", "name": "Standart"}],
        "rate_plans": [{"code": "10003870", "name": "Base rate USD"}],
    }
    result = await unified._build_exely_grid("tenant-1", connection, "2026-11-10", "2026-11-11")
    assert [row["room_type_code"] for row in result["grid"]] == ["5003299"]
    assert [row["rate_plan_code"] for row in result["grid"]] == ["10009740"]
    assert result["grid"][0]["rate_plan_name"] == "Base rate USD"


def test_exely_connection_environment_selects_a_safe_default_endpoint():
    assert _connection_endpoint("sandbox", None) == EXELY_TEST_ENDPOINT_URL
    assert _connection_endpoint("production", None) == EXELY_PRODUCTION_ENDPOINT_URL
    assert _connection_endpoint("sandbox", "https://custom.example.test") == "https://custom.example.test"


def test_legacy_rate_screen_respects_suite_mapping_controls():
    update = RateUpdateRequest(
        room_type_code="5003301",
        rate_plan_code="10009740",
        start_date="2026-11-10",
        end_date="2026-11-11",
        availability=1,
        rate=125.0,
        stop_sell=True,
    )

    values = _mapping_values(
        {
            "sync_availability": False,
            "sync_price": True,
            "sync_restrictions": True,
        },
        update,
    )

    assert values["availability"] is None
    assert values["rate"] == 125.0
    assert values["stop_sell"] is True
    assert _mapping_values(None, update) == {}


@pytest.mark.asyncio
async def test_inactive_connections_are_not_selected_as_ari_providers(monkeypatch):
    fake_db = SimpleNamespace(
        hotelrunner_connections=_Collection(row=None),
        exely_connections=_Collection(row=None),
    )
    monkeypatch.setattr("core.database.db", fake_db)
    outbound_service._ACTIVE_PROVIDERS.clear()

    assert await outbound_service.get_active_providers_async("tenant-1") == []
    fake_db.hotelrunner_connections.find_one.assert_awaited_once_with(
        {"tenant_id": "tenant-1", "is_active": True},
        {"_id": 1},
    )
    fake_db.exely_connections.find_one.assert_awaited_once_with(
        {"tenant_id": "tenant-1", "is_active": True},
        {"_id": 1},
    )


@pytest.mark.asyncio
async def test_auto_detected_provider_state_is_not_cached_after_disconnect(monkeypatch):
    fake_db = SimpleNamespace(
        hotelrunner_connections=_Collection(),
        exely_connections=_Collection(),
    )
    fake_db.hotelrunner_connections.find_one.side_effect = [{"id": "active"}, None]
    fake_db.exely_connections.find_one.side_effect = [None, None]
    monkeypatch.setattr("core.database.db", fake_db)
    outbound_service._ACTIVE_PROVIDERS.clear()

    assert await outbound_service.get_active_providers_async("tenant-1") == ["hotelrunner"]
    assert await outbound_service.get_active_providers_async("tenant-1") == []


@pytest.mark.asyncio
async def test_suite_mapping_can_disable_availability_without_disabling_rate(monkeypatch):
    mapping = {
        "pms_room_type": "Junior Suite",
        "exely_room_code": "5003301",
        "exely_rate_plan_code": "10009740",
        "sync_availability": False,
        "sync_price": True,
        "sync_restrictions": True,
    }
    fake_db = SimpleNamespace(
        hotelrunner_connections=_Collection(row=None),
        room_mappings=_Collection(rows=[]),
        exely_room_mappings=_Collection(rows=[mapping]),
    )
    monkeypatch.setattr(unified, "db", fake_db)
    monkeypatch.setattr(unified, "get_tenant_currency", AsyncMock(return_value=("USD", None)))

    request = SimpleNamespace(
        start_date="2026-11-10",
        end_date="2026-11-11",
        availability=1,
        rate=125.0,
        stop_sell=None,
        min_stay=None,
        min_los_arrival=None,
        max_stay=None,
        cta=None,
        ctd=None,
    )
    connection = {
        "hotel_code": "501694",
        "currency": "USD",
        "room_types": [{"code": "5003301", "name": "Suite"}],
        "rate_plans": [{"code": "10009740", "name": "Base rate USD"}],
    }

    with patch(
        "domains.channel_manager.providers.exely.ari_delivery.deliver_exely_ari",
        new=AsyncMock(
            return_value=SimpleNamespace(
                success=True,
                provider_write_count=1,
                error_code="",
                state="confirmed",
            )
        ),
    ) as deliver:
        result = await unified._push_to_exely(
            "tenant-1",
            connection,
            request,
            [("5003301", "10009740")],
            {},
            {"availability", "rate"},
            None,
        )

    assert result["provider_verified"] is True
    assert result["task_count"] == 1
    deliver.assert_awaited_once()
    assert deliver.await_args.args[1] == "rate_batch"
    assert deliver.await_args.args[2]["value"] == [
        {
            "room_type_code": "5003301",
            "rate_plan_code": "10009740",
            "start_date": "2026-11-10",
            "end_date": "2026-11-11",
            "rate_amount": 125.0,
            "currency": "USD",
        }
    ]


@pytest.mark.asyncio
async def test_explicit_mapping_rate_plan_is_usable_when_discovery_cache_is_stale(monkeypatch):
    """A saved Exely mapping must outrank an older room-discovery cache."""
    mapping = {
        "pms_room_type": "Standard",
        "exely_room_code": "5003299",
        "exely_rate_plan_code": "10009740",
        "sync_availability": True,
        "sync_price": True,
        "sync_restrictions": True,
    }
    fake_db = SimpleNamespace(
        hotelrunner_connections=_Collection(row=None),
        room_mappings=_Collection(rows=[]),
        exely_room_mappings=_Collection(rows=[mapping]),
    )
    monkeypatch.setattr(unified, "db", fake_db)
    monkeypatch.setattr(unified, "get_tenant_currency", AsyncMock(return_value=("USD", None)))
    request = SimpleNamespace(
        start_date="2026-11-10", end_date="2026-11-11", availability=None,
        rate=125.0, stop_sell=None, min_stay=None, min_los_arrival=None,
        max_stay=None, cta=None, ctd=None,
    )
    connection = {
        "hotel_code": "501694", "currency": "USD",
        "room_types": [{"code": "5003299", "name": "Standard"}],
        # This is deliberately an old discovery result.  It must not block the
        # live mapping above.
        "rate_plans": [{"code": "10003870", "name": "Old base rate"}],
    }
    with patch(
        "domains.channel_manager.providers.exely.ari_delivery.deliver_exely_ari",
        new=AsyncMock(return_value=SimpleNamespace(success=True, provider_write_count=1, error_code="", state="confirmed")),
    ) as deliver:
        result = await unified._push_to_exely(
            "tenant-1", connection, request, [("5003299", "10009740")], {}, {"rate"}, None
        )

    assert result["provider_verified"] is True
    assert deliver.await_args.args[2]["value"][0]["rate_plan_code"] == "10009740"


@pytest.mark.asyncio
async def test_discovered_but_unmapped_exely_pair_is_not_written(monkeypatch):
    fake_db = SimpleNamespace(
        hotelrunner_connections=_Collection(row=None),
        room_mappings=_Collection(rows=[]),
        exely_room_mappings=_Collection(rows=[]),
    )
    monkeypatch.setattr(unified, "db", fake_db)
    monkeypatch.setattr(unified, "get_tenant_currency", AsyncMock(return_value=("USD", None)))
    request = SimpleNamespace(
        start_date="2026-11-10",
        end_date="2026-11-11",
        availability=7,
        rate=None,
        stop_sell=None,
        min_stay=None,
        min_los_arrival=None,
        max_stay=None,
        cta=None,
        ctd=None,
    )
    connection = {
        "hotel_code": "501694",
        "currency": "USD",
        "room_types": [{"code": "5003299", "name": "Standard"}],
        "rate_plans": [{"code": "10009740", "name": "Base rate USD"}],
    }

    with patch(
        "domains.channel_manager.providers.exely.ari_delivery.deliver_exely_ari",
        new=AsyncMock(),
    ) as deliver:
        result = await unified._push_to_exely(
            "tenant-1",
            connection,
            request,
            [("5003299", "10009740")],
            {},
            {"availability"},
            None,
        )

    assert result["delivery_state"] == "NOT_SENT"
    assert result["provider_verified"] is False
    deliver.assert_not_awaited()

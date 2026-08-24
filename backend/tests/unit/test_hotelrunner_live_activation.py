from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from channel_manager.connectors.hotelrunner_v2 import router as hrv2_router


class _Cursor:
    def __init__(self, rows):
        self.rows = rows

    async def to_list(self, _limit):
        return self.rows


class _Collection:
    def __init__(self, *, one=None, rows=None, distinct=None, count=0):
        self.one = one
        self.rows = rows or []
        self.distinct_values = distinct or []
        self.count = count
        self.update_one = AsyncMock()

    async def find_one(self, *_args, **_kwargs):
        return self.one

    def find(self, *_args, **_kwargs):
        return _Cursor(self.rows)

    async def distinct(self, *_args, **_kwargs):
        return self.distinct_values

    async def count_documents(self, *_args, **_kwargs):
        return self.count


@pytest.mark.asyncio
async def test_activation_snapshot_accepts_two_rate_plans_for_one_inventory(monkeypatch):
    mappings = [
        {
            "pms_room_type": "standard",
            "hr_inv_code": "HR:1",
            "sync_availability": True,
            "sync_price": True,
            "sync_restrictions": True,
        },
        {
            "pms_room_type": "standard",
            "hr_inv_code": "HR:1",
            "sync_availability": True,
            "sync_price": True,
            "sync_restrictions": True,
        },
    ]
    fake_db = SimpleNamespace(
        hotelrunner_connections=_Collection(one={"environment": "production", "property_name": "Hotel"}),
        hotelrunner_room_mappings=_Collection(rows=mappings),
        rooms=_Collection(distinct=["standard"]),
        outbox_events=_Collection(count=0),
    )
    monkeypatch.setattr("core.database.db", fake_db)
    monkeypatch.setattr(
        "channel_manager.connectors.hotelrunner_v2.dry_run.check_write_enable_criteria",
        AsyncMock(return_value={"all_criteria_met": True, "met_count": 6, "total_criteria": 6}),
    )
    monkeypatch.setattr(
        "channel_manager.connectors.hotelrunner_v2.feature_flags.get_flags",
        AsyncMock(return_value={"connector_enabled": False, "shadow_mode": True, "write_enabled": False}),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.production_safety.safe_runtime_state",
        lambda: {"ari_write_allowed": True},
    )

    result = await hrv2_router._live_activation_snapshot("tenant-1")

    assert result["mapping_ready"] is True
    assert result["ready_to_activate"] is True
    assert result["ambiguous_room_types"] == []


@pytest.mark.asyncio
async def test_activation_snapshot_fails_closed_for_ambiguous_inventory(monkeypatch):
    mappings = [
        {
            "pms_room_type": "standard",
            "hr_inv_code": "HR:1",
            "sync_availability": True,
            "sync_price": True,
            "sync_restrictions": True,
        },
        {
            "pms_room_type": "standard",
            "hr_inv_code": "HR:2",
            "sync_availability": True,
            "sync_price": True,
            "sync_restrictions": True,
        },
    ]
    fake_db = SimpleNamespace(
        hotelrunner_connections=_Collection(one={"environment": "production"}),
        hotelrunner_room_mappings=_Collection(rows=mappings),
        rooms=_Collection(distinct=["standard"]),
        outbox_events=_Collection(count=0),
    )
    monkeypatch.setattr("core.database.db", fake_db)
    monkeypatch.setattr(
        "channel_manager.connectors.hotelrunner_v2.dry_run.check_write_enable_criteria",
        AsyncMock(return_value={"all_criteria_met": True}),
    )
    monkeypatch.setattr(
        "channel_manager.connectors.hotelrunner_v2.feature_flags.get_flags",
        AsyncMock(return_value={}),
    )
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.production_safety.safe_runtime_state",
        lambda: {"ari_write_allowed": True},
    )

    result = await hrv2_router._live_activation_snapshot("tenant-1")

    assert result["mapping_ready"] is False
    assert result["ready_to_activate"] is False
    assert result["ambiguous_room_types"] == ["standard"]


@pytest.mark.asyncio
async def test_enable_live_ari_requires_exact_confirmation():
    with pytest.raises(HTTPException) as exc:
        await hrv2_router.enable_live_ari(
            tenant_id="tenant-1",
            body={"confirmation": "yes"},
            current_user=SimpleNamespace(id="u1", name="Admin"),
            _perm=None,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "LIVE_ARI_CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_enable_live_ari_sets_both_flag_collections_and_audits(monkeypatch):
    monkeypatch.setattr(
        hrv2_router,
        "_live_activation_snapshot",
        AsyncMock(
            return_value={
                "ready_to_activate": True,
                "mapping_count": 10,
                "write_criteria": {"met_count": 6},
            }
        ),
    )
    provider = SimpleNamespace(test_connection=AsyncMock(return_value=SimpleNamespace(success=True)))
    monkeypatch.setattr(
        "domains.channel_manager.providers.hotelrunner.factory.get_provider",
        AsyncMock(return_value=(provider, {})),
    )
    get_flags = AsyncMock(return_value={"connector_enabled": False, "shadow_mode": True, "write_enabled": False})
    set_flags = AsyncMock(return_value={"connector_enabled": True, "shadow_mode": False, "write_enabled": True})
    monkeypatch.setattr("channel_manager.connectors.hotelrunner_v2.feature_flags.get_flags", get_flags)
    monkeypatch.setattr("channel_manager.connectors.hotelrunner_v2.feature_flags.set_flags", set_flags)
    connector_flags = _Collection()
    monkeypatch.setattr("core.database.db", SimpleNamespace(connector_flags=connector_flags))
    audit = AsyncMock()
    monkeypatch.setattr("shared_kernel.audit_helper.audit_log", audit)

    result = await hrv2_router.enable_live_ari(
        tenant_id="tenant-1",
        body={"confirmation": "ENABLE_HOTELRUNNER_ARI_WRITE"},
        current_user=SimpleNamespace(id="u1", name="Admin"),
        _perm=None,
    )

    assert result["enabled"] is True
    assert result["provider_write_count"] == 0
    provider.test_connection.assert_awaited_once()
    set_flags.assert_awaited_once()
    connector_flags.update_one.assert_awaited_once()
    audit.assert_awaited_once()


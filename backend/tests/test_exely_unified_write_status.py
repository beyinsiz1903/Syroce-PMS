"""The editor's status/preflight must use its native Exely delivery gate."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from domains.channel_manager import unified_rate_manager_router as router


@pytest.mark.parametrize("enabled,global_reason,expected", [
    (True, "", ""),
    (False, "", "EXELY_ARI_WRITE_DISABLED"),
    (None, "", "EXELY_ARI_WRITE_DISABLED"),
    (True, "EXELY_RUNTIME_OFF", "EXELY_RUNTIME_OFF"),
])
def test_native_write_gate(monkeypatch, enabled, global_reason, expected):
    monkeypatch.setattr(router, "exely_ari_write_block_reason", lambda: global_reason)
    assert router._ari_write_block_for_targets([{
        "provider": "exely", "connection": {"ari_write_enabled": enabled},
    }]) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("enabled,flags_mode,expected", [(False, "live", "read_only"), (True, "shadow", "live")])
async def test_badge_ignores_unrelated_v2_flags(monkeypatch, enabled, flags_mode, expected):
    database = SimpleNamespace(
        hotelrunner_connections=SimpleNamespace(find_one=AsyncMock(return_value=None)),
        exely_connections=SimpleNamespace(find_one=AsyncMock(return_value={"ari_write_enabled": enabled})),
        connector_flags=SimpleNamespace(find_one=AsyncMock(return_value={"shadow_mode": flags_mode == "shadow"})),
        agencies=SimpleNamespace(count_documents=AsyncMock(return_value=0)),
    )
    monkeypatch.setattr(router, "db", database)
    monkeypatch.setattr(router, "_tenant_configured_provider", AsyncMock(return_value="exely"))
    monkeypatch.setattr(router, "exely_ari_write_block_reason", lambda: "")
    result = await router.get_push_providers(SimpleNamespace(tenant_id="tenant-a"))
    assert result["providers"][0]["mode"] == expected
    assert result["providers"][0]["write_enabled"] is enabled
    assert result["providers"][0]["settings_path"] == "/exely"


@pytest.mark.asyncio
async def test_closed_tenant_gate_rejects_before_local_calendar_save(monkeypatch):
    database = MagicMock()
    calendar_save = AsyncMock()
    database.__getitem__.return_value.bulk_write = calendar_save
    monkeypatch.setattr(router, "db", database)
    monkeypatch.setattr(router, "_detect_active_provider", AsyncMock(return_value={
        "provider": "exely", "connection": {"ari_write_enabled": False},
    }))
    monkeypatch.setattr(router, "require_tenant_module", AsyncMock())
    monkeypatch.setattr(router, "exely_ari_write_block_reason", lambda: "")
    push = AsyncMock()
    monkeypatch.setattr(router, "_push_to_exely", push)
    request = router.UnifiedBulkUpdateRequest(
        room_type_codes=["5003299"], rate_plan_codes=["10009740"],
        start_date="2026-11-02", end_date="2026-11-09", availability=8,
        update_fields=["availability"],
    )
    with pytest.raises(HTTPException) as exc:
        await router.unified_bulk_grid_update(request, SimpleNamespace(tenant_id="tenant-a", id="operator"), None)
    assert exc.value.detail["error_code"] == "EXELY_ARI_WRITE_DISABLED"
    calendar_save.assert_not_awaited()
    push.assert_not_awaited()

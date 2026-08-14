from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from domains.pms import operations_router


@pytest.mark.asyncio
async def test_guest_preferences_accepts_public_id_with_tenant_scope(monkeypatch):
    guests = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1)),
    )
    audit = SimpleNamespace(insert_one=AsyncMock())
    monkeypatch.setattr(
        operations_router,
        "db",
        SimpleNamespace(guests=guests, kvkk_audit_log=audit),
    )

    result = await operations_router.update_guest_preferences(
        "guest-public-id",
        {"preferences": {"pillow_type": "firm"}},
        current_user=SimpleNamespace(tenant_id="tenant-a", email="operator@example.invalid"),
    )

    query = guests.update_one.await_args.args[0]
    assert query == {
        "tenant_id": "tenant-a",
        "$or": [{"id": "guest-public-id"}, {"_id": "guest-public-id"}],
    }
    assert result == {"id": "guest-public-id", "status": "updated"}
    audit.insert_one.assert_awaited_once()


@pytest.mark.asyncio
async def test_guest_preferences_not_found_remains_fail_closed(monkeypatch):
    guests = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=0)),
    )
    monkeypatch.setattr(
        operations_router,
        "db",
        SimpleNamespace(guests=guests, kvkk_audit_log=SimpleNamespace(insert_one=AsyncMock())),
    )

    with pytest.raises(operations_router.HTTPException) as exc_info:
        await operations_router.update_guest_preferences(
            "missing",
            {"preferences": {}},
            current_user=SimpleNamespace(tenant_id="tenant-a", email="operator@example.invalid"),
        )

    assert exc_info.value.status_code == 404

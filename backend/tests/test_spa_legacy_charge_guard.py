"""The legacy POS SPA stub must never acknowledge a nonexistent folio posting."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from domains.pms.pos_fnb_router import spa_gym


def actor(role="admin", tenant_id="hotel-a"):
    return SimpleNamespace(id="cashier", tenant_id=tenant_id, name="Synthetic operator", role=role, is_super_admin=False)


@pytest.fixture
def source(monkeypatch):
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value={"id": "legacy", "tenant_id": "hotel-a", "status": "confirmed"})
    collection.update_one = AsyncMock()
    collection.find_one_and_update = AsyncMock()
    database = SimpleNamespace(pos_spa_reservations=collection)
    monkeypatch.setattr(spa_gym, "db", database)
    return collection


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["confirmed", "in_progress", "completed", "cancelled", "no_show"])
async def test_legacy_charge_fails_closed_without_completing_or_marking_charged(source, status):
    source.find_one.return_value["status"] = status
    with pytest.raises(HTTPException) as error:
        await spa_gym.charge_spa_reservation("legacy", folio_id="some-folio", current_user=actor())
    assert error.value.status_code == 410
    assert "/spa-wellness" in str(error.value.detail)
    source.update_one.assert_not_awaited()
    source.find_one_and_update.assert_not_awaited()
    source.find_one.assert_awaited_once_with({"tenant_id": "hotel-a", "id": "legacy"})


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["staff", "housekeeping", "sales", "procurement"])
async def test_nonfinancial_roles_cannot_use_legacy_charge(source, role):
    with pytest.raises(HTTPException) as error:
        await spa_gym.charge_spa_reservation("legacy", folio_id="some-folio", current_user=actor(role))
    assert error.value.status_code == 403
    source.find_one.assert_not_awaited()
    source.update_one.assert_not_awaited()


@pytest.mark.asyncio
async def test_foreign_or_missing_source_stays_404_and_untouched(source):
    source.find_one.return_value = None
    with pytest.raises(HTTPException) as error:
        await spa_gym.charge_spa_reservation("foreign", folio_id="some-folio", current_user=actor())
    assert error.value.status_code == 404
    source.find_one.assert_awaited_once_with({"tenant_id": "hotel-a", "id": "foreign"})
    source.update_one.assert_not_awaited()

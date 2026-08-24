from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import ValidationError

from domains.revenue.pricing_router import rates


def _user():
    return SimpleNamespace(tenant_id="tenant-a", id="user-a", email="admin@example.com")


def test_percentage_and_promotional_rate_guards():
    with pytest.raises(ValidationError):
        rates.DiscountCodeCreate(
            code="SUMMER",
            discount_type="percentage",
            discount_value=101,
            starts_on=date(2026, 6, 1),
            ends_on=date(2026, 6, 30),
        )

    with pytest.raises(ValidationError):
        rates.PromotionalRateCreate(
            room_type="Deluxe",
            regular_rate=100,
            promo_rate=120,
            starts_on=date(2026, 6, 1),
            ends_on=date(2026, 6, 30),
        )


@pytest.mark.asyncio
async def test_discount_code_is_tenant_scoped_and_persisted():
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value=None)
    collection.insert_one = AsyncMock()
    fake_db = MagicMock(discount_codes=collection)
    payload = rates.DiscountCodeCreate(
        code=" summer26 ",
        description="Yaz kampanyası",
        discount_type="percentage",
        discount_value=15,
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 8, 31),
        usage_limit=250,
    )

    with patch.object(rates, "db", fake_db), patch.object(
        rates, "_audit_rate_mutation", new=AsyncMock()
    ), patch.object(rates, "_ensure_pricing_catalog_indexes", new=AsyncMock()):
        result = await rates.create_discount_code(payload, _user())

    query = collection.find_one.await_args.args[0]
    assert query == {"tenant_id": "tenant-a", "code": "SUMMER26"}
    inserted = collection.insert_one.await_args.args[0]
    assert inserted["tenant_id"] == "tenant-a"
    assert inserted["usage_count"] == 0
    assert result["code"] == "SUMMER26"
    assert "tenant_id" not in result


@pytest.mark.asyncio
async def test_duplicate_discount_code_is_rejected():
    collection = MagicMock()
    collection.find_one = AsyncMock(return_value={"_id": "existing"})
    collection.insert_one = AsyncMock()
    fake_db = MagicMock(discount_codes=collection)
    payload = rates.DiscountCodeCreate(
        code="SUMMER26",
        discount_value=15,
        starts_on=date(2026, 6, 1),
        ends_on=date(2026, 8, 31),
    )

    with patch.object(rates, "db", fake_db), patch.object(
        rates, "_ensure_pricing_catalog_indexes", new=AsyncMock()
    ):
        with pytest.raises(Exception) as exc:
            await rates.create_discount_code(payload, _user())

    assert getattr(exc.value, "status_code", None) == 409
    collection.insert_one.assert_not_awaited()

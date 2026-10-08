from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from domains.sales import router as sales_router


class _Collection:
    def __init__(self):
        self.inserted = []

    async def insert_one(self, document):
        self.inserted.append(document)


class _Attributions(_Collection):
    def __init__(self, existing=None):
        super().__init__()
        self.existing = existing

    async def find_one(self, query, projection=None):
        return self.existing


class _FindOneCollection:
    def __init__(self, result):
        self.result = result

    async def find_one(self, query, projection=None):
        return self.result


@pytest.mark.asyncio
async def test_create_campaign_normalizes_required_fields_and_audits(monkeypatch):
    campaigns = _Collection()
    audit = AsyncMock()
    monkeypatch.setattr(sales_router, "db", SimpleNamespace(marketing_campaigns=campaigns))
    monkeypatch.setattr(sales_router, "create_audit_log", audit)
    user = SimpleNamespace(tenant_id="tenant-a", id="user-a")

    result = await sales_router.create_campaign(
        {"name": "  Sonbahar  ", "subject": "  Teklif  ", "message": "  Merhaba  ", "segment": "vip"},
        current_user=user,
        _perm=None,
    )

    assert result["success"] is True
    campaign = campaigns.inserted[0]
    assert campaign["name"] == "Sonbahar"
    assert campaign["subject"] == "Teklif"
    assert campaign["message"] == "Merhaba"
    assert campaign["status"] == "draft"
    assert campaign["created_at"] == campaign["updated_at"]
    audit.assert_awaited_once_with(
        "tenant-a",
        user,
        "marketing_campaign_created",
        "marketing_campaign",
        campaign["id"],
        {"segment": "vip"},
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("payload", [{}, {"name": "K", "subject": "S", "message": "   "}])
async def test_create_campaign_rejects_missing_required_text(monkeypatch, payload):
    campaigns = _Collection()
    monkeypatch.setattr(sales_router, "db", SimpleNamespace(marketing_campaigns=campaigns))
    monkeypatch.setattr(sales_router, "create_audit_log", AsyncMock())

    with pytest.raises(HTTPException) as exc:
        await sales_router.create_campaign(
            payload,
            current_user=SimpleNamespace(tenant_id="tenant-a", id="user-a"),
            _perm=None,
        )

    assert exc.value.status_code == 400
    assert campaigns.inserted == []


@pytest.mark.asyncio
async def test_campaign_attribution_is_tenant_scoped_and_idempotent(monkeypatch):
    existing = {"campaign_id": "c1", "booking_id": "b1", "net_revenue": 900}
    attributions = _Attributions(existing=existing)
    db = SimpleNamespace(
        marketing_campaigns=_FindOneCollection({"id": "c1"}),
        bookings=_FindOneCollection({"id": "b1", "total_amount": 1000}),
        marketing_attributions=attributions,
    )
    audit = AsyncMock()
    monkeypatch.setattr(sales_router, "db", db)
    monkeypatch.setattr(sales_router, "create_audit_log", audit)

    result = await sales_router.record_campaign_attribution(
        "c1", {"booking_id": "b1"},
        current_user=SimpleNamespace(tenant_id="tenant-a", id="user-a"), _perm=None,
    )

    assert result == {"success": True, "created": False, "attribution": existing}
    assert attributions.inserted == []
    audit.assert_not_awaited()


@pytest.mark.asyncio
async def test_campaign_attribution_calculates_net_revenue_once(monkeypatch):
    attributions = _Attributions()
    db = SimpleNamespace(
        marketing_campaigns=_FindOneCollection({"id": "c1"}),
        bookings=_FindOneCollection({"id": "b1", "total_amount": 1000, "commission_amount": 120, "payment_fee": 30}),
        marketing_attributions=attributions,
    )
    audit = AsyncMock()
    monkeypatch.setattr(sales_router, "db", db)
    monkeypatch.setattr(sales_router, "create_audit_log", audit)

    result = await sales_router.record_campaign_attribution(
        "c1", {"booking_id": "b1"},
        current_user=SimpleNamespace(tenant_id="tenant-a", id="user-a"), _perm=None,
    )

    assert result["created"] is True
    assert result["attribution"]["gross_revenue"] == 1000
    assert result["attribution"]["net_revenue"] == 850
    audit.assert_awaited_once()

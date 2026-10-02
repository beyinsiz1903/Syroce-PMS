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

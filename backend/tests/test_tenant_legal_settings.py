from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from domains.admin.router import hotel as hotel_router
from domains.admin.schemas import UpdateHotelInfoRequest
from models.enums import UserRole
from routers.hotel_services_pkg.invoices import _format_document_date, _merge_hotel_document_branding
from routers.regulatory import _normalize_tenant_legal_profile


class _TenantCollection:
    def __init__(self, tenant: dict):
        self.tenant = dict(tenant)

    async def find_one(self, query, _projection=None):
        if query.get("id") != self.tenant.get("id"):
            return None
        return dict(self.tenant)

    async def update_one(self, query, update):
        if query.get("id") != self.tenant.get("id"):
            return SimpleNamespace(matched_count=0, modified_count=0)
        self.tenant.update(update.get("$set", {}))
        return SimpleNamespace(matched_count=1, modified_count=1)


@pytest.mark.asyncio
async def test_hotel_admin_can_update_legal_fields_and_aliases(monkeypatch):
    tenants = _TenantCollection({"id": "tenant-1", "subscription_tier": "enterprise"})
    monkeypatch.setattr(hotel_router, "db", SimpleNamespace(tenants=tenants))
    monkeypatch.setattr(hotel_router, "_cache_mgr", None)

    result = await hotel_router.update_hotel_info(
        UpdateHotelInfoRequest(
            property_name="The Canyon Kartepe",
            tax_number="1234567890",
            license_number="TGA-2026-001",
            license_expires_at="2027-08-29",
            star_rating=4,
        ),
        SimpleNamespace(tenant_id="tenant-1", role=UserRole.ADMIN),
    )

    tenant = result["tenant"]
    assert tenant["property_name"] == "The Canyon Kartepe"
    assert tenant["hotel_name"] == "The Canyon Kartepe"
    assert tenant["tax_number"] == "1234567890"
    assert tenant["tax_no"] == "1234567890"
    assert tenant["license_number"] == "TGA-2026-001"
    assert tenant["license_expires_at"] == "2027-08-29"
    assert tenant["star_rating"] == 4


@pytest.mark.asyncio
async def test_legal_update_rejects_invalid_tax_number(monkeypatch):
    tenants = _TenantCollection({"id": "tenant-1", "subscription_tier": "enterprise"})
    monkeypatch.setattr(hotel_router, "db", SimpleNamespace(tenants=tenants))
    monkeypatch.setattr(hotel_router, "_cache_mgr", None)

    with pytest.raises(HTTPException) as exc:
        await hotel_router.update_hotel_info(
            UpdateHotelInfoRequest(tax_number="12345"),
            SimpleNamespace(tenant_id="tenant-1", role=UserRole.ADMIN),
        )

    assert exc.value.status_code == 422
    assert "VKN" in exc.value.detail


def test_regulatory_profile_accepts_current_tenant_field_names():
    normalized = _normalize_tenant_legal_profile(
        {
            "property_name": "The Canyon Kartepe",
            "tax_number": "1234567890",
            "contact_phone": "+905551112233",
        }
    )

    assert normalized["hotel_name"] == "The Canyon Kartepe"
    assert normalized["tax_no"] == "1234567890"
    assert normalized["phone"] == "+905551112233"


def test_voucher_branding_prefers_real_tenant_name_and_keeps_uploaded_logo():
    branding = _merge_hotel_document_branding(
        {"hotel_name": "Hotel", "logo_data": "data:image/png;base64,AAAA", "hotel_email": "info@example.com"},
        {"property_name": "The Canyon Kartepe", "address": "Kartepe", "phone": "+905551112233"},
    )

    assert branding["hotel_name"] == "The Canyon Kartepe"
    assert branding["logo_data"] == "data:image/png;base64,AAAA"
    assert branding["hotel_address"] == "Kartepe"
    assert branding["hotel_phone"] == "+905551112233"
    assert _format_document_date("2026-08-29T14:00:00Z") == "29.08.2026"

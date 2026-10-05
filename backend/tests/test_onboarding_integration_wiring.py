from __future__ import annotations

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

os.environ.setdefault("JWT_SECRET", "unit-test-secret-key-at-least-32-chars!!")

from routers import onboarding


def _collection():
    return SimpleNamespace(update_one=AsyncMock())


def test_hotel_info_normalizes_property_type_and_validates_fiscal_identity():
    payload = onboarding.HotelInfoIn(
        property_type="boutique",
        timezone="Europe/Istanbul",
        tax_number="1234567890",
        mersis_no="1234567890123456",
    )

    assert payload.property_type == "boutique_hotel"
    assert payload.country == "TR"

    with pytest.raises(ValidationError):
        onboarding.HotelInfoIn(tax_number="123")
    with pytest.raises(ValidationError):
        onboarding.HotelInfoIn(mersis_no="123")
    with pytest.raises(ValidationError):
        onboarding.HotelInfoIn(timezone="Europe/Does-Not-Exist")


def test_compose_address_uses_structured_legal_fields():
    assert onboarding._compose_address(
        {
            "street": "Atatürk Caddesi",
            "building_no": "12/A",
            "neighborhood": "Merkez Mahallesi",
            "district": "Pamukkale",
            "city": "Denizli",
            "postal_code": "20000",
        }
    ) == "Atatürk Caddesi 12/A, Merkez Mahallesi / Pamukkale / Denizli, 20000"


@pytest.mark.asyncio
async def test_hotel_info_syncs_currency_tax_timezone_and_fiscal_targets(monkeypatch):
    fake_db = SimpleNamespace(
        tenants=_collection(),
        hotel_settings=_collection(),
        tenant_settings=_collection(),
        city_tax_rules=_collection(),
    )
    monkeypatch.setattr(onboarding, "_db", lambda: fake_db)
    tenant = {
        "property_name": "Denizli Oteli",
        "contact_phone": "+902582120001",
        "contact_email": "denizli@syroce.com",
        "city": "Denizli",
        "district": "Pamukkale",
        "neighborhood": "Merkez",
        "street": "Atatürk Caddesi",
        "building_no": "12/A",
        "postal_code": "20000",
        "tax_number": "1234567890",
        "tax_office": "Pamukkale",
        "country": "TR",
        "currency": "EUR",
        "timezone": "Europe/Istanbul",
        "default_language": "tr",
        "vat_rate": 8,
        "accommodation_tax_exempt": True,
    }

    targets = await onboarding._sync_hotel_info_dependencies(
        "tenant-1",
        tenant,
        {
            "city",
            "district",
            "street",
            "building_no",
            "currency",
            "timezone",
            "vat_rate",
            "accommodation_tax_exempt",
        },
    )

    assert targets == ["hotel_settings", "tenant_settings", "accommodation_tax", "nilvera_seller"]
    hotel_update = fake_db.hotel_settings.update_one.await_args.args[1]["$set"]
    assert hotel_update["currency"] == "EUR"
    assert hotel_update["currency_symbol"] == "€"
    assert hotel_update["default_accommodation_vat_rate"] == 8.0
    assert "Pamukkale / Denizli" in hotel_update["hotel_address"]

    tenant_settings_calls = fake_db.tenant_settings.update_one.await_args_list
    assert tenant_settings_calls[0].args[1]["$set"]["timezone"] == "Europe/Istanbul"
    assert tenant_settings_calls[1].args[1]["$set"]["nilvera.seller"]["vkn"] == "1234567890"
    tax_update = fake_db.city_tax_rules.update_one.await_args.args[1]
    assert tax_update["$set"]["active"] is False
    tenant_aliases = fake_db.tenants.update_one.await_args.args[1]["$set"]
    assert tenant_aliases["tax_no"] == "1234567890"


@pytest.mark.asyncio
async def test_hotel_info_does_not_claim_incomplete_einvoice_setup(monkeypatch):
    fake_db = SimpleNamespace(
        tenants=_collection(),
        hotel_settings=_collection(),
        tenant_settings=_collection(),
        city_tax_rules=_collection(),
    )
    monkeypatch.setattr(onboarding, "_db", lambda: fake_db)

    targets = await onboarding._sync_hotel_info_dependencies(
        "tenant-2",
        {"property_name": "Eksik Otel", "currency": "TRY", "timezone": "Europe/Istanbul"},
        {"property_name"},
    )

    assert "nilvera_seller" not in targets
    assert fake_db.tenant_settings.update_one.await_count == 1
    fake_db.city_tax_rules.update_one.assert_not_awaited()

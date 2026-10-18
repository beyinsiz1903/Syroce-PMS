from datetime import UTC, datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core import provider_credential_vault
from domains.admin.router.tenants import _build_commercial_quote, _validate_provider_credentials, router
from models.schemas.identity import TenantRegister


def _tenant_payload(**overrides):
    payload = {
        "property_name": "Test Hotel",
        "email": "manager@example.com",
        "password": "safe-password",
        "name": "Hotel Manager",
        "phone": "+90 555 000 00 00",
        "address": "Test Address",
    }
    payload.update(overrides)
    return payload


def test_tenant_register_defaults_to_standalone_chain():
    tenant = TenantRegister(**_tenant_payload())
    assert tenant.chain_mode == "standalone"
    assert tenant.chain_id is None
    assert tenant.chain_name is None


def test_tenant_register_accepts_explicit_chain_and_provider():
    tenant = TenantRegister(
        **_tenant_payload(
            chain_mode="existing_chain",
            chain_id="chain-1",
            channel_manager_provider="exely",
        )
    )
    assert tenant.chain_id == "chain-1"
    assert tenant.channel_manager_provider == "exely"


def test_tenant_register_rejects_unknown_provider():
    with pytest.raises(ValidationError):
        TenantRegister(**_tenant_payload(channel_manager_provider="unknown"))


def _quote(**overrides):
    quote = {
        "pricing_version": "2026-08-23", "currency": "EUR", "plan_key": "basic",
        "plan_label": "Basic", "base_monthly": 79, "addon_monthly": 49,
        "list_monthly_total": 128, "list_setup_total": 0,
        "final_monthly_total": 128, "final_setup_total": 0,
        "override_reason": None,
        "line_items": [{"module_key": "ai_chatbot", "label": "AI Chatbot", "monthly": 49, "setup": 0, "included": False}],
    }
    quote.update(overrides)
    return quote


def test_commercial_quote_requires_reason_for_override():
    with pytest.raises(ValidationError, match="Fiyat değişikliği nedeni zorunludur"):
        TenantRegister(**_tenant_payload(commercial_quote=_quote(final_monthly_total=99)))


def test_backend_recalculates_quote_and_sets_audit_fields():
    payload = TenantRegister(**_tenant_payload(commercial_quote=_quote()))
    quoted = _build_commercial_quote(payload.commercial_quote, {"ai_chatbot": True}, "basic", "super-1", datetime(2026, 8, 23, tzinfo=UTC))
    assert quoted["list_monthly_total"] == 128
    assert quoted["line_items"][0]["module_key"] == "ai_chatbot"
    assert quoted["quoted_by"] == "super-1"


def test_backend_rejects_tampered_list_totals():
    payload = TenantRegister(**_tenant_payload(commercial_quote=_quote(addon_monthly=0, list_monthly_total=79, final_monthly_total=79)))
    with pytest.raises(HTTPException, match="fiyat kataloğuyla eşleşmiyor"):
        _build_commercial_quote(payload.commercial_quote, {"ai_chatbot": True}, "basic", "super-1", datetime.now(UTC))


@pytest.mark.parametrize("key", ["hr", "parking"])
def test_unpriced_addon_cannot_be_granted_without_an_explicit_quote(key):
    payload = TenantRegister(**_tenant_payload(commercial_quote=_quote(addon_monthly=0, list_monthly_total=79, final_monthly_total=79)))
    with pytest.raises(HTTPException, match="fiyat gerekçesi zorunludur") as error:
        _build_commercial_quote(payload.commercial_quote, {key: True}, "basic", "super-1", datetime.now(UTC))
    assert error.value.status_code == 400


def test_negotiated_addons_are_recalculated_and_audited_in_eur():
    agreed = {
        "hr": {"monthly": 25, "setup": 0, "reason": "  Tesis ile onaylanan teklif  "},
        "parking": {"monthly": 15, "setup": 30, "reason": "Otopark anlaşması"},
    }
    payload = TenantRegister(**_tenant_payload(commercial_quote=_quote(
        addon_monthly=40, list_monthly_total=119, list_setup_total=30,
        final_monthly_total=119, final_setup_total=30, negotiated_addon_prices=agreed,
    )))
    quote = _build_commercial_quote(payload.commercial_quote, {"hr": True, "parking": True}, "basic", "super-1", datetime.now(UTC))
    assert quote["currency"] == "EUR"
    assert quote["list_monthly_total"] == 119
    assert quote["list_setup_total"] == 30
    assert quote["quoted_by"] == "super-1"
    assert quote["negotiated_addon_prices"]["hr"]["reason"] == "Tesis ile onaylanan teklif"
    rows = {row["module_key"]: row for row in quote["line_items"]}
    assert set(rows) == {"hr", "parking"}  # Ignore the client's stale/fake line_items.
    assert rows["hr"]["monthly"] == 25
    assert rows["parking"]["setup"] == 30
    assert all(row["pricing_source"] == "negotiated_eur" and row["pricing_reason"] for row in rows.values())


@pytest.mark.parametrize("price", [
    {"monthly": -1, "setup": 0, "reason": "agreement"},
    {"monthly": float("nan"), "setup": 0, "reason": "agreement"},
    {"monthly": 1, "setup": float("inf"), "reason": "agreement"},
    {"monthly": 1, "setup": 0, "reason": "   "},
    {"monthly": 1.001, "setup": 0, "reason": "agreement"},
    {"monthly": 1, "reason": "agreement"},
])
def test_negotiated_price_rejects_invalid_missing_or_unaudited_values(price):
    with pytest.raises(ValidationError):
        TenantRegister(**_tenant_payload(commercial_quote=_quote(negotiated_addon_prices={"hr": price})))


def test_negotiated_price_does_not_override_fixed_catalogue_addons():
    with pytest.raises(ValidationError):
        TenantRegister(**_tenant_payload(commercial_quote=_quote(negotiated_addon_prices={
            "spa": {"monthly": 1, "setup": 0, "reason": "cannot bypass catalogue"},
        })))


def test_negotiated_addon_rejects_tampered_totals_and_unselected_modules():
    payload = TenantRegister(**_tenant_payload(commercial_quote=_quote(
        addon_monthly=0, list_monthly_total=79, final_monthly_total=79,
        negotiated_addon_prices={"hr": {"monthly": 25, "setup": 0, "reason": "agreement"}},
    )))
    with pytest.raises(HTTPException, match="fiyat kataloğuyla eşleşmiyor"):
        _build_commercial_quote(payload.commercial_quote, {"hr": True}, "basic", "super-1", datetime.now(UTC))
    with pytest.raises(HTTPException, match="yalnız seçili modül"):
        _build_commercial_quote(payload.commercial_quote, {"hr": False}, "basic", "super-1", datetime.now(UTC))


def test_intentional_free_addon_still_has_audited_price_line():
    payload = TenantRegister(**_tenant_payload(commercial_quote=_quote(
        addon_monthly=0, list_monthly_total=79, final_monthly_total=79,
        negotiated_addon_prices={"hr": {"monthly": 0, "setup": 0, "reason": "Pilot dönemi ücretsiz kullanım onayı"}},
    )))
    quote = _build_commercial_quote(payload.commercial_quote, {"hr": True}, "basic", "super-1", datetime.now(UTC))
    assert quote["list_monthly_total"] == 79
    assert quote["line_items"][0]["module_key"] == "hr"
    assert quote["line_items"][0]["monthly"] == 0
    assert quote["line_items"][0]["pricing_reason"] == "Pilot dönemi ücretsiz kullanım onayı"


def test_negotiated_amounts_preserve_cents_in_totals():
    payload = TenantRegister(**_tenant_payload(commercial_quote=_quote(
        addon_monthly=35.79, list_monthly_total=114.79, list_setup_total=30.1,
        final_monthly_total=114.79, final_setup_total=30.1,
        negotiated_addon_prices={
            "hr": {"monthly": 12.34, "setup": 0, "reason": "agreement"},
            "parking": {"monthly": 23.45, "setup": 30.1, "reason": "agreement"},
        },
    )))
    quote = _build_commercial_quote(payload.commercial_quote, {"hr": True, "parking": True}, "basic", "super-1", datetime.now(UTC))
    assert quote["addon_monthly"] == 35.79
    assert quote["list_monthly_total"] == 114.79
    assert quote["list_setup_total"] == 30.1


def test_provider_credentials_are_allowlisted_and_trimmed():
    credentials = _validate_provider_credentials(
        "hotelrunner",
        {"token": " token ", "hr_id": " hotel-id ", "unexpected": "discard"},
    )
    assert credentials == {"token": "token", "hr_id": "hotel-id"}


def test_provider_credentials_require_all_mandatory_fields():
    with pytest.raises(HTTPException) as exc:
        _validate_provider_credentials("exely", {"username": "user"})
    assert exc.value.status_code == 400
    assert "SOAP Password" in exc.value.detail
    assert "Hotel Code" in exc.value.detail


def test_admin_provisioning_routes_are_registered_without_provider_test_route():
    routes = {(route.path, method) for route in router.routes for method in route.methods}
    assert ("/api/admin/chains", "GET") in routes
    assert ("/api/admin/chains", "POST") in routes
    assert ("/api/admin/tenants/{tenant_id}/provisioning", "GET") in routes
    assert ("/api/admin/tenants/{tenant_id}/provisioning", "PATCH") in routes
    assert ("/api/admin/tenants/{tenant_id}/integrations/{provider}/credentials", "POST") in routes
    assert ("/api/admin/tenants/{tenant_id}/integrations/nilvera", "PUT") in routes
    assert ("/api/admin/tenants/{tenant_id}/integrations/nilvera-accounting", "PUT") in routes
    assert all("test-connection" not in path and "validate" not in path for path, _ in routes)


def test_admin_uses_domain_neutral_encrypted_provider_vault():
    assert callable(provider_credential_vault.store_secret)
    assert callable(provider_credential_vault.get_masked_credentials)

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from core import provider_credential_vault
from domains.admin.router.tenants import _validate_provider_credentials, router
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
    assert all("test-connection" not in path and "validate" not in path for path, _ in routes)


def test_admin_uses_domain_neutral_encrypted_provider_vault():
    assert callable(provider_credential_vault.store_secret)
    assert callable(provider_credential_vault.get_masked_credentials)

"""
Security Hardening Router - API endpoints for multi-tenant security.
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, Query

from core.cache import cached
from modules.security_hardening.audit_completeness import audit_completeness
from modules.security_hardening.credential_vault import credential_vault
from modules.security_hardening.data_masking import data_masking
from modules.security_hardening.property_permissions import property_permissions
from modules.security_hardening.tenant_scoped_queries import tenant_query_guard
from shared_kernel.tenancy_context import TenantContext, get_current_tenant

router = APIRouter(prefix="/api/security-hardening", tags=["security-hardening"])


# --- Tenant Scope ---

@router.get("/tenant-scope/check")
@cached(ttl=60, key_prefix="tenant_scope_check")
async def check_tenant_isolation(tenant: TenantContext = Depends(get_current_tenant)):
    return await tenant_query_guard.check_isolation(tenant.tenant_id)


@router.get("/tenant-scope/violations")
async def get_violations(
    limit: int = Query(50, le=200),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return tenant_query_guard.get_violations(limit)


# --- Property Permissions ---

@router.get("/property-permissions")
async def get_property_permissions(
    property_id: str | None = None,
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await property_permissions.get_property_permissions(tenant.tenant_id, property_id)


@router.post("/property-permissions/check")
async def check_permission(
    user_id: str = Query(...),
    role: str = Query(...),
    property_id: str = Query(...),
    action: str = Query(...),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await property_permissions.check_permission(
        tenant.tenant_id, user_id, role, property_id, action
    )


@router.get("/property-permissions/roles")
async def get_role_permissions(tenant: TenantContext = Depends(get_current_tenant)):
    return property_permissions.get_role_permissions()


# --- Credential Vault ---

@router.get("/vault/status")
async def get_vault_status(tenant: TenantContext = Depends(get_current_tenant)):
    return await credential_vault.get_vault_status(tenant.tenant_id)


@router.post("/vault/store")
async def store_credential(
    credential_type: str = Query(...),
    credential_key: str = Query(...),
    credential_value: str = Query(...),
    description: str = Query(""),
    rotation_days: int = Query(90),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await credential_vault.store_credential(
        tenant.tenant_id, credential_type, credential_key,
        credential_value, description, rotation_days,
    )


@router.post("/vault/{credential_id}/rotate")
async def rotate_credential(
    credential_id: str,
    new_value: str = Query(...),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await credential_vault.rotate_credential(tenant.tenant_id, credential_id, new_value)


@router.get("/vault/leakage-check")
async def check_leakage(tenant: TenantContext = Depends(get_current_tenant)):
    return await credential_vault.check_leakage(tenant.tenant_id)


# --- Data Masking ---

@router.post("/masking-preview")
async def preview_masking(
    data: dict[str, Any] = Body(...),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return data_masking.preview_masking(data)


@router.post("/masking-coverage")
async def check_masking_coverage(
    data: dict[str, Any] = Body(...),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return data_masking.get_masking_coverage(data)


# --- Audit Completeness ---

@router.get("/audit-completeness")
async def check_audit_completeness(
    hours: int = Query(24, le=168),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await audit_completeness.check_completeness(tenant.tenant_id, hours)


@router.get("/audit-gaps")
async def get_audit_gaps(
    hours: int = Query(24, le=168),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await audit_completeness.get_audit_gaps(tenant.tenant_id, hours)


@router.get("/audit-summary")
async def get_audit_summary(
    hours: int = Query(24, le=168),
    tenant: TenantContext = Depends(get_current_tenant),
):
    return await audit_completeness.get_audit_summary(tenant.tenant_id, hours)

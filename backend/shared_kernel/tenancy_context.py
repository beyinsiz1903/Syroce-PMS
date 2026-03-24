from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException, Request, status

from core.security import get_current_user


@dataclass(frozen=True)
class TenantContext:
    tenant_id: str
    user_id: Optional[str] = None
    role: Optional[str] = None
    correlation_id: Optional[str] = None


@dataclass(frozen=True)
class PropertyContext:
    property_id: Optional[str] = None


def build_tenant_context(current_user, request: Optional[Request] = None) -> TenantContext:
    tenant_id = getattr(current_user, "tenant_id", None)
    if not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Tenant context required",
        )

    role = getattr(current_user, "role", None)
    role_value = role.value if hasattr(role, "value") else str(role) if role else None
    correlation_id = request.headers.get("x-correlation-id") if request else None

    return TenantContext(
        tenant_id=tenant_id,
        user_id=getattr(current_user, "id", None),
        role=role_value,
        correlation_id=correlation_id,
    )


def build_property_context(current_user, request: Optional[Request] = None) -> PropertyContext:
    property_id = None
    if request:
        property_id = request.headers.get("x-property-id")

    property_id = property_id or getattr(current_user, "property_id", None)
    property_id = property_id or getattr(current_user, "selected_property_id", None)
    return PropertyContext(property_id=property_id)


async def get_current_tenant(
    request: Request,
    current_user=Depends(get_current_user),
) -> TenantContext:
    return build_tenant_context(current_user, request)


async def get_current_property(
    request: Request,
    current_user=Depends(get_current_user),
) -> PropertyContext:
    return build_property_context(current_user, request)

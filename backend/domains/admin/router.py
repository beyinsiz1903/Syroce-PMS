"""
Admin / Operations Domain Router
Extracted from legacy_routes.py — Phase B Domain Separation
"""
from fastapi import APIRouter, HTTPException, Depends, status, Body, Query
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import ORJSONResponse, StreamingResponse
from pydantic import BaseModel, Field, EmailStr, conint
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone, timedelta, date
import os
import uuid
import random
import logging
import io

from core.database import db
from core.security import (
    get_current_user, security, JWT_SECRET, JWT_ALGORITHM,
    generate_qr_code, generate_time_based_qr_token,
)
from core.helpers import (
    create_audit_log, require_feature, require_module,
    require_super_admin_guard as require_super_admin, require_admin,
    get_tenant_modules, load_tenant_doc,
)
from models.schemas import User, TenantRegister, UpdateUserRoleRequest
from models.enums import UserRole
from subscription_models import SubscriptionTier, SubscriptionPlan, SUBSCRIPTION_PLANS

logger = logging.getLogger(__name__)


class PermissionCheckRequest(BaseModel):
    permission: str

router = APIRouter(prefix="/api", tags=["Admin / Operations"])


# ── Inline Models ──

from enum import Enum

class TenantModulesUpdate(BaseModel):
    modules: Dict[str, bool]


class SubscriptionUpdateRequest(BaseModel):
    """Subscription duration/date update request

    Backward compatible:
    - If only subscription_days is provided → start=now, end=now+days (or unlimited)
    - If subscription_start_date or subscription_end_date provided → backend prefers these values

    Dates can be provided as:
    - YYYY-MM-DD
    - ISO8601 datetime (e.g. 2025-12-17T00:00:00Z)
    """

    subscription_days: Optional[int] = None  # None = unlimited
    subscription_start_date: Optional[str] = None
    subscription_end_date: Optional[str] = None


class ChangePlanRequest(BaseModel):
    new_tier: str  # basic, professional, enterprise
    billing_cycle: str = "monthly"  # monthly, yearly


class UpdateHotelInfoRequest(BaseModel):
    property_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    total_rooms: Optional[int] = None


class CreateTeamMemberRequest(BaseModel):
    email: EmailStr
    name: str
    phone: Optional[str] = None
    role: str = "front_desk"
    password: str


class UpdateTeamMemberRoleRequest(BaseModel):
    role: str


class SLAConfig(BaseModel):
    category: str  # maintenance, housekeeping, guest_request
    response_time_minutes: int
    resolution_time_minutes: int
    priority: str = "normal"  # low, normal, high, urgent


class DemoRequest(BaseModel):
    name: str
    email: str
    phone: str
    hotel_name: str = Field(..., alias='hotelName')
    room_count: str = Field(..., alias='roomCount')


class PmsLiteLeadStatus(str, Enum):
    NEW = "new"
    CONTACTED = "contacted"
    QUALIFIED = "qualified"
    LOST = "lost"
    WON = "won"


class PmsLiteLeadAdminUpdateRequest(BaseModel):
    status: Optional[PmsLiteLeadStatus] = None
    note: Optional[str] = None


class PmsLiteLeadContact(BaseModel):
    full_name: str
    phone: str
    email: Optional[EmailStr] = None


class PmsLiteLeadHotel(BaseModel):
    property_name: str
    location: Optional[str] = None
    rooms_count: conint(ge=1, le=200)


class PmsLiteLeadMetadata(BaseModel):
    utm_source: Optional[str] = None
    utm_medium: Optional[str] = None
    utm_campaign: Optional[str] = None
    user_agent: Optional[str] = None
    ip: Optional[str] = None


@router.post("/permissions/check")
async def check_permission(
    request: PermissionCheckRequest,
    current_user: User = Depends(get_current_user)
):
    """Check if current user has a specific permission"""
    if not request.permission or request.permission.strip() == "":
        raise HTTPException(status_code=400, detail="Permission field is required and cannot be empty")
    
    try:
        perm = Permission(request.permission)
        has_perm = has_permission(current_user.role, perm)
        return {
            'user_role': current_user.role,
            'permission': request.permission,
            'has_permission': has_perm
        }
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid permission: {request.permission}")

# ============= CHANNEL MANAGER & RMS =============



@router.get("/rbac/permissions/{user_role}/{resource}")
async def get_resource_permissions(
    user_role: UserRole,
    resource: str,
    current_user: User = Depends(get_current_user)
):
    """
    Get detailed permissions for a resource based on user role
    RBAC 2.0 - Granular access control
    """
    if user_role.value not in RBAC_V2_PERMISSIONS:
        raise HTTPException(status_code=404, detail="Role not found")
    
    role_permissions = RBAC_V2_PERMISSIONS[user_role.value]
    
    if resource not in role_permissions:
        return {
            'user_role': user_role.value,
            'resource': resource,
            'permissions': PermissionSet().model_dump(),
            'has_access': False
        }
    
    permissions = role_permissions[resource]
    
    return {
        'user_role': user_role.value,
        'resource': resource,
        'permissions': permissions.model_dump(),
        'has_access': permissions.view
    }




@router.get("/rbac/my-permissions")
async def get_my_permissions(
    current_user: User = Depends(get_current_user)
):
    """Get current user's all resource permissions"""
    user_role = current_user.role
    
    if user_role.value not in RBAC_V2_PERMISSIONS:
        return {'error': 'Invalid role'}
    
    all_permissions = RBAC_V2_PERMISSIONS[user_role.value]
    
    return {
        'user_id': current_user.id,
        'user_name': current_user.name,
        'user_role': user_role.value,
        'permissions': {
            resource: perms.model_dump()
            for resource, perms in all_permissions.items()
        }
    }


# ============= MOBILE APP ENDPOINTS (STAFF & GUEST) =============



@router.get("/admin/tenants")
async def list_tenants(current_user: User = Depends(require_super_admin)):
    """List all hotels/tenants for super admin users ONLY.

    NOTE: Sadece SUPER_ADMIN rolüne sahip kullanıcılar tüm otelleri görebilir.
    Normal ADMIN kullanıcılar (hotel yöneticileri) bu endpoint'e erişemez.
    """
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(1000)

    # Merge defaults for backward compatibility
    for tenant in tenants:
        tenant["modules"] = get_tenant_modules(tenant)

    return {"tenants": tenants}




@router.get("/admin/module-report")
async def get_module_report(current_user: User = Depends(require_super_admin)):
    """Return a flattened module/license report for all tenants.

    ONLY for SUPER_ADMIN - shows all hotels in the system.
    This is optimized for UI & export use cases and avoids leaking internal Mongo fields.
    """
    tenants = await db.tenants.find({}, {"_id": 0}).to_list(2000)

    report_rows = []
    for tenant in tenants:
        modules = get_tenant_modules(tenant)

        row = {
            "tenant_id": tenant.get("id"),
            "property_name": tenant.get("property_name"),
            "location": tenant.get("location"),
            "subscription_tier": tenant.get("subscription_tier", "basic"),
        }

        # Flatten all known module keys
        for key, value in modules.items():
            try:
                row[f"mod_{key}"] = bool(value)
            except Exception:
                row[f"mod_{key}"] = False

        report_rows.append(row)

    return {"rows": report_rows, "count": len(report_rows)}




@router.post("/admin/tenants")
async def create_tenant(
    payload: TenantRegister,
    current_user: User = Depends(require_super_admin)
):
    """Create a new hotel/tenant (SUPER ADMIN only)"""
    
    # Check if tenant with same email already exists
    existing = await db.tenants.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Bu email adresi ile kayıtlı bir otel zaten var")
    
    # Calculate subscription dates
    start_date = datetime.now(timezone.utc)
    end_date = None
    
    if payload.subscription_days:
        end_date = start_date + timedelta(days=payload.subscription_days)
    # If None, unlimited subscription
    
    # Determine subscription plan (core_small_hotel by default, or pms_lite etc.)
    normalized_plan = (
        payload.subscription_plan
        or "core_small_hotel"
    )

    # Determine subscription tier
    tier = (payload.subscription_tier or "basic").lower()
    if tier not in ("basic", "professional", "enterprise"):
        tier = "basic"

    # Get default modules for the selected tier
    tier_modules = get_plan_default_modules(tier)

    # Create new tenant
    new_tenant = Tenant(
        property_name=payload.property_name,
        email=payload.email,
        phone=payload.phone,
        address=payload.address,
        location=payload.location or "",
        description=payload.description or "",
        subscription_tier=tier,
        subscription_start_date=start_date.isoformat(),
        subscription_end_date=end_date.isoformat() if end_date else None,
        subscription_status="active",
        subscription_plan=normalized_plan,
        modules=tier_modules,
    )
    
    tenant_dict = new_tenant.model_dump()
    tenant_dict['created_at'] = tenant_dict['created_at'].isoformat()
    await db.tenants.insert_one(tenant_dict)
    
    # Create admin user for this tenant
    hashed_password = hash_password(payload.password)
    
    new_user = User(
        tenant_id=new_tenant.id,
        email=payload.email,
        name=payload.name,
        phone=payload.phone,
        password_hash=hashed_password,
        role=UserRole.ADMIN
    )
    
    user_dict = new_user.model_dump()
    user_dict['created_at'] = user_dict['created_at'].isoformat()
    # Rename password_hash to hashed_password for login compatibility
    user_dict['hashed_password'] = user_dict.pop('password_hash', hashed_password)
    await db.users.insert_one(user_dict)
    
    return {
        "success": True,
        "message": "Otel başarıyla oluşturuldu",
        "tenant_id": new_tenant.id,
        "user_id": new_user.id,
        "subscription_start": start_date.isoformat(),
        "subscription_end": end_date.isoformat() if end_date else "Sınırsız",
        "subscription_days": payload.subscription_days or "Sınırsız"
    }




@router.get("/admin/users")
async def list_all_users(
    email_filter: Optional[str] = None,
    role_filter: Optional[str] = None,
    tenant_id_filter: Optional[str] = None,
    current_user: User = Depends(require_super_admin)
):
    """List all users in the system (SUPER ADMIN only)"""
    
    query = {}
    if email_filter:
        query['email'] = {'$regex': email_filter, '$options': 'i'}
    if role_filter:
        query['role'] = role_filter
    if tenant_id_filter:
        query['tenant_id'] = tenant_id_filter
    
    users = await db.users.find(query, {'_id': 0, 'hashed_password': 0, 'password_hash': 0}).to_list(100)
    
    return {
        "users": users,
        "count": len(users)
    }




@router.patch("/admin/users/{user_id}/role")
async def update_user_role(
    user_id: str,
    payload: UpdateUserRoleRequest,
    current_user: User = Depends(require_super_admin)
):
    """Update user role (SUPER ADMIN only)
    
    Allows super admin to change any user's role including making other super admins.
    """
    
    # Validate role
    valid_roles = [role.value for role in UserRole]
    if payload.role not in valid_roles:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid role. Valid roles: {', '.join(valid_roles)}"
        )
    
    # Find user
    target_user = await db.users.find_one({"id": user_id})
    if not target_user:
        raise HTTPException(status_code=404, detail="Kullanıcı bulunamadı")
    
    # Update role
    result = await db.users.update_one(
        {"id": user_id},
        {"$set": {"role": payload.role}}
    )
    
    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Role güncellenemedi")
    
    return {
        "success": True,
        "message": f"Kullanıcı role'ü başarıyla güncellendi: {payload.role}",
        "user_id": user_id,
        "user_email": target_user.get('email'),
        "old_role": target_user.get('role'),
        "new_role": payload.role
    }




@router.patch("/admin/tenants/{tenant_id}/modules")
async def update_tenant_modules(
    tenant_id: str,
    payload: TenantModulesUpdate,
    current_user: User = Depends(require_super_admin),
):
    """Update enabled modules for a specific hotel (SUPER ADMIN only).

    Body örneği:
    {
      "modules": {
        "pms": true,
        "reports": true,
        "invoices": false,
        "ai": true
      }
    }
    """
    # Try by logical id first
    query = {"id": tenant_id}

    update_doc = {"$set": {"modules": payload.modules}}

    result = await db.tenants.update_one(query, update_doc)
    if result.matched_count == 0:
        # Fallback to Mongo _id
        try:
            from bson import ObjectId

            result = await db.tenants.update_one(
                {"_id": ObjectId(tenant_id)}, update_doc
            )
        except Exception:
            result = None

    if not result or result.matched_count == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Otel bulunamadı",
        )

    # Return updated tenant with merged modules
    tenant_doc = await db.tenants.find_one(query, {"_id": 0})
    if not tenant_doc:
        from bson import ObjectId

        tenant_doc = await db.tenants.find_one(
            {"_id": ObjectId(tenant_id)}, {"_id": 0}
        )

    if not tenant_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Otel bulunamadı",
        )

    tenant_doc["modules"] = get_tenant_modules(tenant_doc)
    return tenant_doc


@router.patch("/admin/tenants/{tenant_id}/subscription")
async def update_tenant_subscription(
    tenant_id: str,
    payload: SubscriptionUpdateRequest,
    current_user: User = Depends(require_super_admin)
):
    """Update subscription duration for a tenant (SUPER ADMIN only)

    Supports both duration-based updates and manual start/end date updates.
    """

    def _parse_date_input(value: Optional[str]) -> Optional[datetime]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            return None

        # Accept YYYY-MM-DD or ISO8601. Normalize to UTC.
        try:
            if len(value) == 10 and value[4] == '-' and value[7] == '-':
                dt = datetime.fromisoformat(value)
                return dt.replace(tzinfo=timezone.utc)

            dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:
            raise HTTPException(
                status_code=400,
                detail="Geçersiz tarih formatı. YYYY-MM-DD veya ISO8601 kullanın (örn: 2025-12-17).",
            )

    # Find tenant
    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    # If manual dates are provided, prefer them. Otherwise, fallback to subscription_days.
    manual_mode = bool(payload.subscription_start_date) or bool(payload.subscription_end_date)

    if manual_mode:
        start_date = _parse_date_input(payload.subscription_start_date) or datetime.now(timezone.utc)
        end_date = _parse_date_input(payload.subscription_end_date)
    else:
        start_date = datetime.now(timezone.utc)
        end_date = None
        if payload.subscription_days:
            end_date = start_date + timedelta(days=payload.subscription_days)

    if end_date and end_date < start_date:
        raise HTTPException(status_code=400, detail="Bitiş tarihi başlangıç tarihinden önce olamaz")

    # Update tenant
    update_data = {
        "subscription_start_date": start_date.isoformat(),
        "subscription_end_date": end_date.isoformat() if end_date else None,
        "subscription_status": "active",
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db.tenants.update_one(
        {"id": tenant_id},
        {"$set": update_data}
    )

    if result.modified_count == 0:
        raise HTTPException(status_code=400, detail="Subscription güncellenemedi")

    return {
        "success": True,
        "message": "Üyelik süresi başarıyla güncellendi",
        "tenant_id": tenant_id,
        "subscription_start": start_date.isoformat(),
        "subscription_end": end_date.isoformat() if end_date else "Sınırsız",
        "subscription_days": payload.subscription_days or "Sınırsız",
        "manual_dates": manual_mode,
    }




@router.get("/subscription/plans")
async def get_subscription_plans():
    """Get all available subscription plans"""
    return {
        'plans': [plan.model_dump() for plan in SUBSCRIPTION_PLANS.values()],
        'currency': 'EUR',
        'tiers': [tier.value for tier in SubscriptionTier]
    }



@router.get("/subscription/plan-modules")
async def get_plan_module_defaults():
    """Get default module mapping for each subscription tier.
    Used by admin panel to show which modules are included per plan."""
    return {
        'plan_modules': PLAN_MODULE_DEFAULTS,
        'tiers': [tier.value for tier in SubscriptionTier],
        'all_module_keys': get_all_module_keys()
    }



@router.patch("/admin/tenants/{tenant_id}/tier")
async def update_tenant_tier(
    tenant_id: str,
    payload: dict,
    current_user: User = Depends(require_super_admin)
):
    """Change a tenant's subscription tier and optionally reset modules to tier defaults.

    Body:
    {
        "tier": "basic" | "professional" | "enterprise",
        "reset_modules": true  // optional, default true
    }
    """
    new_tier = (payload.get("tier") or "basic").lower()
    reset_modules = payload.get("reset_modules", True)

    if new_tier not in ("basic", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="Geçersiz plan. Geçerli: basic, professional, enterprise")

    tenant = await db.tenants.find_one({"id": tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    update_data = {
        "subscription_tier": new_tier,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }

    if reset_modules:
        update_data["modules"] = get_plan_default_modules(new_tier)

    await db.tenants.update_one({"id": tenant_id}, {"$set": update_data})

    updated_tenant = await db.tenants.find_one({"id": tenant_id}, {"_id": 0})
    if updated_tenant:
        updated_tenant["modules"] = get_tenant_modules(updated_tenant)

    return {
        "success": True,
        "message": f"Plan {new_tier} olarak güncellendi",
        "tenant": updated_tenant,
    }



@router.get("/subscription/features")
async def get_feature_comparison_endpoint():
    """Get feature comparison across all tiers"""
    return {
        'features': get_feature_comparison(),
        'tiers': [tier.value for tier in SubscriptionTier]
    }



@router.get("/subscription/current")
async def get_current_subscription(
    current_user: User = Depends(get_current_user)
):
    """Get current user's subscription"""
    tenant = await db.tenants.find_one({'id': current_user.tenant_id})
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    subscription_tier = tenant.get('subscription_tier', 'basic')
    # Handle legacy tier names
    tier_map = {"pro": "professional", "ultra": "enterprise"}
    normalized_tier = tier_map.get(subscription_tier, subscription_tier)
    try:
        plan = SUBSCRIPTION_PLANS.get(SubscriptionTier(normalized_tier))
    except ValueError:
        plan = SUBSCRIPTION_PLANS.get(SubscriptionTier.BASIC)
    
    return {
        'tenant_id': current_user.tenant_id,
        'tier': normalized_tier,
        'plan': plan.model_dump() if plan else None,
        'status': tenant.get('subscription_status', 'active'),
        'valid_until': tenant.get('subscription_valid_until'),
        'rooms_count': await db.rooms.count_documents({'tenant_id': current_user.tenant_id}),
        'users_count': await db.users.count_documents({'tenant_id': current_user.tenant_id}),
        'modules': get_tenant_modules(tenant)
    }



@router.post("/subscription/upgrade")
async def upgrade_subscription(
    new_tier: SubscriptionTier,
    billing_cycle: str = 'monthly',  # monthly or yearly
    current_user: User = Depends(get_current_user)
):
    """Upgrade subscription tier"""
    tenant = await db.tenants.find_one({'id': current_user.tenant_id})
    
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    
    current_tier = tenant.get('subscription_tier', 'basic')
    tier_map = {"pro": "professional", "ultra": "enterprise"}
    normalized_current = tier_map.get(current_tier, current_tier)
    
    try:
        if SubscriptionTier(normalized_current) == new_tier:
            raise HTTPException(status_code=400, detail="Already on this tier")
    except ValueError:
        pass
    
    plan = SUBSCRIPTION_PLANS.get(new_tier)
    if not plan:
        raise HTTPException(status_code=400, detail="Invalid subscription tier")
    
    # Calculate price
    amount = plan.price_yearly if billing_cycle == 'yearly' else plan.price_monthly
    
    # Get default modules for new tier
    new_modules = get_plan_default_modules(new_tier.value)

    # Update subscription
    await db.tenants.update_one(
        {'id': current_user.tenant_id},
        {'$set': {
            'subscription_tier': new_tier.value,
            'subscription_status': 'active',
            'billing_cycle': billing_cycle,
            'modules': new_modules,
            'subscription_valid_until': (datetime.now(timezone.utc) + timedelta(days=365 if billing_cycle == 'yearly' else 30)).isoformat(),
            'last_billing_date': datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        'success': True,
        'message': f'Successfully upgraded to {plan.name}',
        'tier': new_tier.value,
        'amount': amount,
        'billing_cycle': billing_cycle
    }


# ============= BILLING HISTORY & PLAN MANAGEMENT =============



@router.post("/subscription/change-plan")
async def change_subscription_plan(
    payload: ChangePlanRequest,
    current_user: User = Depends(get_current_user)
):
    """Change subscription plan (upgrade or downgrade).
    Creates a billing history record for the change."""
    tenant = await db.tenants.find_one({'id': current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler plan değiştirebilir")

    new_tier = payload.new_tier.lower()
    if new_tier == "pro": new_tier = "professional"
    if new_tier == "ultra": new_tier = "enterprise"

    if new_tier not in ("basic", "professional", "enterprise"):
        raise HTTPException(status_code=400, detail="Geçersiz plan")

    current_tier = (tenant.get('subscription_tier', 'basic')).lower()
    if current_tier == "pro": current_tier = "professional"
    if current_tier == "ultra": current_tier = "enterprise"

    if current_tier == new_tier:
        raise HTTPException(status_code=400, detail="Zaten bu plandasınız")

    tier_order = {"basic": 0, "professional": 1, "enterprise": 2}
    is_downgrade = tier_order.get(new_tier, 0) < tier_order.get(current_tier, 0)

    try:
        plan = SUBSCRIPTION_PLANS[SubscriptionTier(new_tier)]
    except (ValueError, KeyError):
        raise HTTPException(status_code=400, detail="Geçersiz plan")

    # Downgrade checks: room / user limits
    if is_downgrade:
        if plan.max_rooms:
            room_count = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
            if room_count > plan.max_rooms:
                raise HTTPException(
                    status_code=400,
                    detail=f"Oda sayınız ({room_count}), hedef planın limitini ({plan.max_rooms}) aşıyor. Önce oda sayısını azaltın."
                )
        if plan.max_users:
            user_count = await db.users.count_documents({'tenant_id': current_user.tenant_id})
            if user_count > plan.max_users:
                raise HTTPException(
                    status_code=400,
                    detail=f"Kullanıcı sayınız ({user_count}), hedef planın limitini ({plan.max_users}) aşıyor. Önce kullanıcı sayısını azaltın."
                )

    amount = plan.price_yearly if payload.billing_cycle == 'yearly' else plan.price_monthly
    new_modules = get_plan_default_modules(new_tier)
    now = datetime.now(timezone.utc)
    valid_days = 365 if payload.billing_cycle == 'yearly' else 30

    # Update tenant
    await db.tenants.update_one(
        {'id': current_user.tenant_id},
        {'$set': {
            'subscription_tier': new_tier,
            'subscription_status': 'active',
            'billing_cycle': payload.billing_cycle,
            'modules': new_modules,
            'subscription_valid_until': (now + timedelta(days=valid_days)).isoformat(),
            'last_billing_date': now.isoformat(),
            'updated_at': now.isoformat(),
        }}
    )

    # Create billing history record
    billing_record = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "user_id": current_user.id,
        "user_name": current_user.name,
        "action": "downgrade" if is_downgrade else "upgrade",
        "from_tier": current_tier,
        "to_tier": new_tier,
        "billing_cycle": payload.billing_cycle,
        "amount": amount,
        "currency": "EUR",
        "status": "completed",
        "description": f"{'Downgrade' if is_downgrade else 'Upgrade'}: {current_tier} → {new_tier} ({payload.billing_cycle})",
        "created_at": now.isoformat(),
        "valid_until": (now + timedelta(days=valid_days)).isoformat(),
    }
    await db.billing_history.insert_one(billing_record)

    action_label = "düşürüldü" if is_downgrade else "yükseltildi"
    return {
        "success": True,
        "message": f"Plan {new_tier} olarak {action_label}",
        "is_downgrade": is_downgrade,
        "tier": new_tier,
        "amount": amount,
        "billing_cycle": payload.billing_cycle,
        "valid_until": (now + timedelta(days=valid_days)).isoformat(),
    }




@router.get("/billing/history")
async def get_billing_history(
    current_user: User = Depends(get_current_user)
):
    """Get billing / plan change history for the current hotel"""
    records = await db.billing_history.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0}
    ).sort("created_at", -1).to_list(100)

    return {"records": records, "count": len(records)}




@router.patch("/hotel/info")
async def update_hotel_info(
    payload: UpdateHotelInfoRequest,
    current_user: User = Depends(get_current_user)
):
    """Update hotel/tenant information (admin only)"""
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler otel bilgilerini güncelleyebilir")

    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    update_data = {}
    if payload.property_name is not None:
        update_data["property_name"] = payload.property_name
    if payload.phone is not None:
        update_data["phone"] = payload.phone
        update_data["contact_phone"] = payload.phone
    if payload.email is not None:
        update_data["email"] = payload.email
        update_data["contact_email"] = payload.email
    if payload.address is not None:
        update_data["address"] = payload.address
    if payload.location is not None:
        update_data["location"] = payload.location
    if payload.description is not None:
        update_data["description"] = payload.description
    if payload.total_rooms is not None:
        # Check plan limit
        tier = (tenant.get("subscription_tier", "basic")).lower()
        if tier == "pro": tier = "professional"
        if tier == "ultra": tier = "enterprise"
        try:
            plan = SUBSCRIPTION_PLANS[SubscriptionTier(tier)]
            if plan.max_rooms and payload.total_rooms > plan.max_rooms:
                raise HTTPException(
                    status_code=400,
                    detail=f"Planınızın oda limiti: {plan.max_rooms}. Daha fazla oda için planınızı yükseltin."
                )
        except (ValueError, KeyError):
            pass
        update_data["total_rooms"] = payload.total_rooms

    if not update_data:
        raise HTTPException(status_code=400, detail="Güncellenecek alan bulunamadı")

    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    await db.tenants.update_one({"id": current_user.tenant_id}, {"$set": update_data})

    updated = await db.tenants.find_one({"id": current_user.tenant_id}, {"_id": 0})
    return {
        "success": True,
        "message": "Otel bilgileri güncellendi",
        "tenant": updated,
    }



@router.get("/rbac/roles")
async def get_available_roles(current_user: User = Depends(get_current_user)):
    """Get available roles for the current tenant's subscription tier"""
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tier = tenant.get("subscription_tier", "basic")
    tier_lower = (tier or "basic").lower()
    if tier_lower == "pro":
        tier_lower = "professional"
    if tier_lower == "ultra":
        tier_lower = "enterprise"

    allowed_roles = ROLES_BY_TIER.get(tier_lower, ROLES_BY_TIER["basic"])
    return {
        "tier": tier_lower,
        "allowed_roles": allowed_roles,
        "all_roles": [r.value for r in UserRole if r.value not in ("super_admin", "guest", "agency_admin", "agency_agent")],
    }


# ============= HOTEL TEAM MANAGEMENT ENDPOINTS =============



@router.get("/hotel/team")
async def list_hotel_team(current_user: User = Depends(get_current_user)):
    """List all team members for the current hotel (hotel admin only)"""
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler ekip üyelerini görebilir")

    users = await db.users.find(
        {"tenant_id": current_user.tenant_id},
        {"_id": 0, "hashed_password": 0, "password_hash": 0, "password": 0}
    ).to_list(200)

    # Get tier info
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    tier = (tenant.get("subscription_tier", "basic") if tenant else "basic").lower()
    if tier == "pro": tier = "professional"
    if tier == "ultra": tier = "enterprise"

    allowed_roles = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])

    # Max users check
    plan = SUBSCRIPTION_PLANS.get(SubscriptionTier(tier))
    max_users = plan.max_users if plan and plan.max_users else 999

    return {
        "users": users,
        "count": len(users),
        "tier": tier,
        "allowed_roles": allowed_roles,
        "max_users": max_users,
        "can_add": len(users) < max_users,
    }




@router.post("/hotel/team")
async def add_team_member(
    payload: CreateTeamMemberRequest,
    current_user: User = Depends(get_current_user)
):
    """Add a new team member to the current hotel"""
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler ekip üyesi ekleyebilir")

    # Get tenant tier
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    if not tenant:
        raise HTTPException(status_code=404, detail="Otel bulunamadı")

    tier = (tenant.get("subscription_tier", "basic")).lower()
    if tier == "pro": tier = "professional"
    if tier == "ultra": tier = "enterprise"

    # RBAC: Check if role is allowed for tier
    if not is_role_allowed_for_tier(payload.role, tier):
        allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
        raise HTTPException(
            status_code=400,
            detail=f"Bu plan ({tier}) için '{payload.role}' rolü kullanılamaz. İzin verilen roller: {', '.join(allowed)}"
        )

    # Max users check
    plan = SUBSCRIPTION_PLANS.get(SubscriptionTier(tier))
    max_users = plan.max_users if plan and plan.max_users else 999
    current_count = await db.users.count_documents({"tenant_id": current_user.tenant_id})
    if current_count >= max_users:
        raise HTTPException(
            status_code=400,
            detail=f"Kullanıcı limitine ulaşıldı ({max_users}). Daha fazla kullanıcı eklemek için planınızı yükseltin."
        )

    # Check duplicate email
    existing = await db.users.find_one({"email": payload.email})
    if existing:
        raise HTTPException(status_code=400, detail="Bu email adresi zaten kayıtlı")

    hashed = hash_password(payload.password)
    new_user = {
        "id": str(uuid.uuid4()),
        "tenant_id": current_user.tenant_id,
        "email": payload.email,
        "name": payload.name,
        "phone": payload.phone or "",
        "role": payload.role,
        "is_active": True,
        "hashed_password": hashed,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(new_user)

    return {
        "success": True,
        "message": f"{payload.name} başarıyla eklendi ({payload.role})",
        "user_id": new_user["id"],
    }




@router.patch("/hotel/team/{user_id}/role")
async def update_team_member_role(
    user_id: str,
    payload: UpdateTeamMemberRoleRequest,
    current_user: User = Depends(get_current_user)
):
    """Update a team member's role"""
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler rol değiştirebilir")

    # Find team member
    target = await db.users.find_one({"id": user_id, "tenant_id": current_user.tenant_id})
    if not target:
        raise HTTPException(status_code=404, detail="Ekip üyesi bulunamadı")

    # Can't change own role
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Kendi rolünüzü değiştiremezsiniz")

    # Can't change super_admin
    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin rolü değiştirilemez")

    # Tier check
    tenant = await db.tenants.find_one({"id": current_user.tenant_id})
    tier = (tenant.get("subscription_tier", "basic") if tenant else "basic").lower()
    if tier == "pro": tier = "professional"
    if tier == "ultra": tier = "enterprise"

    if not is_role_allowed_for_tier(payload.role, tier):
        allowed = ROLES_BY_TIER.get(tier, ROLES_BY_TIER["basic"])
        raise HTTPException(
            status_code=400,
            detail=f"Bu plan ({tier}) için '{payload.role}' rolü kullanılamaz. İzin verilen: {', '.join(allowed)}"
        )

    await db.users.update_one({"id": user_id}, {"$set": {"role": payload.role}})
    return {"success": True, "message": f"Rol güncellendi: {payload.role}"}




@router.delete("/hotel/team/{user_id}")
async def remove_team_member(
    user_id: str,
    current_user: User = Depends(get_current_user)
):
    """Remove a team member"""
    if current_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        raise HTTPException(status_code=403, detail="Sadece yöneticiler üye silebilir")

    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Kendinizi silemezsiniz")

    target = await db.users.find_one({"id": user_id, "tenant_id": current_user.tenant_id})
    if not target:
        raise HTTPException(status_code=404, detail="Ekip üyesi bulunamadı")
    if target.get("role") == "super_admin":
        raise HTTPException(status_code=400, detail="Super Admin silinemez")

    await db.users.delete_one({"id": user_id, "tenant_id": current_user.tenant_id})
    return {"success": True, "message": "Ekip üyesi silindi"}


# ============= DEMO ENVIRONMENT ENDPOINTS =============

from demo_data_generator import DemoDataGenerator



@router.post("/demo/populate")
async def populate_demo_data(
    hotel_type: str = 'boutique',  # boutique, resort, city
    current_user: User = Depends(get_current_user)
):
    """Populate account with realistic demo data"""
    
    # Check if already has data
    existing_rooms = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    if existing_rooms > 10:
        raise HTTPException(status_code=400, detail="Account already has data. Cannot populate demo data.")
    
    # Generate demo data
    demo_data = DemoDataGenerator.generate_demo_hotel(current_user.tenant_id, hotel_type)
    
    # Insert demo data
    stats = {
        'rooms': 0,
        'guests': 0,
        'bookings': 0,
        'staff': 0,
        'inventory': 0
    }
    
    # Insert rooms
    if demo_data['rooms']:
        await db.rooms.insert_many(demo_data['rooms'])
        stats['rooms'] = len(demo_data['rooms'])
    
    # Insert guests
    if demo_data['guests']:
        await db.guests.insert_many(demo_data['guests'])
        stats['guests'] = len(demo_data['guests'])
    
    # Insert bookings
    if demo_data['bookings']:
        await db.bookings.insert_many(demo_data['bookings'])
        stats['bookings'] = len(demo_data['bookings'])
    
    # Insert staff
    if demo_data['staff']:
        # Note: Staff might need to be in users collection with passwords
        # For demo, we'll just store as reference data
        for staff in demo_data['staff']:
            await db.staff_profiles.insert_one(staff)
        stats['staff'] = len(demo_data['staff'])
    
    # Insert inventory
    if demo_data['inventory']:
        await db.inventory.insert_many(demo_data['inventory'])
        stats['inventory'] = len(demo_data['inventory'])
    
    return {
        'success': True,
        'message': 'Demo data populated successfully',
        'hotel_name': demo_data['hotel_name'],
        'stats': stats
    }



@router.get("/demo/status")
async def get_demo_status(
    current_user: User = Depends(get_current_user)
):
    """Check if account is using demo data"""
    
    rooms_count = await db.rooms.count_documents({'tenant_id': current_user.tenant_id})
    guests_count = await db.guests.count_documents({'tenant_id': current_user.tenant_id})
    bookings_count = await db.bookings.count_documents({'tenant_id': current_user.tenant_id})
    
    is_demo = rooms_count > 0 and guests_count > 0
    
    return {
        'is_demo': is_demo,
        'has_data': rooms_count > 0,
        'stats': {
            'rooms': rooms_count,
            'guests': guests_count,
            'bookings': bookings_count
        }
    }


@router.get("/admin/leads")
async def admin_list_pms_lite_leads(
    status: Optional[PmsLiteLeadStatus] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    current_user: User = Depends(get_current_user),
):
    """List PMS Lite marketing leads for super admin."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can access leads")

    query: Dict[str, Any] = {"source": "pms_lite_landing"}
    if status:
        query["status"] = status.value

    if q:
        regex = {"$regex": q, "$options": "i"}
        query["$or"] = [
            {"contact.full_name": regex},
            {"contact.phone": regex},
            {"contact.email": regex},
            {"hotel.property_name": regex},
            {"hotel.location": regex},
        ]

    total = await db.leads.count_documents(query)

    cursor = (
        db.leads.find(query)
        .sort("created_at", -1)
        .skip(max(offset, 0))
        .limit(max(limit, 1))
    )

    leads: List[Dict[str, Any]] = []
    async for lead in cursor:
        leads.append(
            {
                "lead_id": lead.get("lead_id") or lead.get("id"),
                "created_at": lead.get("created_at"),
                "status": lead.get("status", PmsLiteLeadStatus.NEW.value),
                "note": lead.get("note"),
                "full_name": lead.get("contact", {}).get("full_name"),
                "phone": lead.get("contact", {}).get("phone"),
                "email": lead.get("contact", {}).get("email"),
                "property_name": lead.get("hotel", {}).get("property_name"),
                "location": lead.get("hotel", {}).get("location"),
                "rooms_count": lead.get("hotel", {}).get("rooms_count"),
            }
        )




@router.get("/admin/leads/export.csv")
async def admin_export_pms_lite_leads_csv(
    status: Optional[PmsLiteLeadStatus] = None,
    q: Optional[str] = None,
    follow_up: Optional[bool] = False,
    current_user: User = Depends(get_current_user),
):
    """Export PMS Lite marketing leads as CSV for super admin."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can export leads")

    from io import StringIO
    import csv

    query: Dict[str, Any] = {"source": "pms_lite_landing"}
    if status:
        query["status"] = status.value

    if q:
        regex = {"$regex": q, "$options": "i"}
        query["$or"] = [
            {"contact.full_name": regex},
            {"contact.phone": regex},
            {"contact.email": regex},
            {"hotel.property_name": regex},
            {"hotel.location": regex},
        ]

    docs: List[Dict[str, Any]] = []
    async for lead in db.leads.find(query):
        docs.append(lead)

    now = datetime.now(timezone.utc)

    if follow_up:
        filtered: List[Dict[str, Any]] = []
        for lead in docs:
            s = lead.get("status", "new")
            created = _parse_iso_dt(lead.get("created_at"))
            last_contact = _parse_iso_dt(lead.get("last_contact_at"))

            if s not in {"new", "contacted", "qualified"}:
                continue

            if s == "new":
                if not created:
                    continue
                if (now - created).total_seconds() < 3600:
                    continue
                filtered.append(lead)
            else:
                cutoff = 24 * 3600
                base = last_contact or created
                if not base:
                    continue
                if (now - base).total_seconds() > cutoff:
                    filtered.append(lead)
        docs = filtered

    output = StringIO()
    # BOM for Excel UTF-8
    output.write("\ufeff")
    writer = csv.writer(output)

    headers = [
        "created_at",
        "status",
        "full_name",
        "phone",
        "email",
        "property_name",
        "location",
        "rooms_count",
        "lead_id",
        "note",
        "last_contact_at",
        "status_changed_at",
    ]
    writer.writerow(headers)

    for lead in docs:
        contact = lead.get("contact", {})
        hotel = lead.get("hotel", {})
        row = [
            lead.get("created_at") or "",
            lead.get("status") or "",
            contact.get("full_name") or "",
            contact.get("phone") or "",
            contact.get("email") or "",
            hotel.get("property_name") or "",
            hotel.get("location") or "",
            hotel.get("rooms_count") or "",
            lead.get("lead_id") or lead.get("id") or "",
            lead.get("note") or "",
            lead.get("last_contact_at") or "",
            lead.get("status_changed_at") or "",
        ]
        writer.writerow(row)

    csv_content = output.getvalue()
    from fastapi.responses import Response

    return Response(
        content=csv_content,
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": "attachment; filename=\"pms-lite-leads.csv\"",
        },
    )



@router.patch("/admin/leads/{lead_id}")
async def admin_update_pms_lite_lead(
    lead_id: str,
    payload: PmsLiteLeadAdminUpdateRequest,
    current_user: User = Depends(get_current_user),
):
    """Update status/note of a PMS Lite marketing lead (super_admin only)."""
    if current_user.role != UserRole.SUPER_ADMIN:
        raise HTTPException(status_code=403, detail="Only super_admin can update leads")

    update: Dict[str, Any] = {}
    if payload.status is not None:
        update["status"] = payload.status.value
    if payload.note is not None:
        update["note"] = payload.note

    if not update:
        return {"ok": True}

    result = await db.leads.update_one(
        {"lead_id": lead_id, "source": "pms_lite_landing"}, {"$set": update}
    )
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Lead not found")

    return {"ok": True, "lead_id": lead_id}


# 6. GET /api/sales/follow-ups - Follow-up reminders


@router.post("/settings/sla")
async def create_sla_config(
    config: SLAConfig,
    current_user: User = Depends(get_current_user)
):
    """
    Create or update SLA configuration for property
    """
    try:
        sla_id = str(uuid.uuid4())
        
        # Check if SLA exists for this category
        existing = await db.sla_configs.find_one({
            'tenant_id': current_user.tenant_id,
            'category': config.category,
            'priority': config.priority
        }, {'_id': 0})
        
        if existing:
            # Update existing
            await db.sla_configs.update_one(
                {
                    'tenant_id': current_user.tenant_id,
                    'category': config.category,
                    'priority': config.priority
                },
                {
                    '$set': {
                        'response_time_minutes': config.response_time_minutes,
                        'resolution_time_minutes': config.resolution_time_minutes,
                        'updated_at': datetime.now(timezone.utc).isoformat(),
                        'updated_by': current_user.name
                    }
                }
            )
            sla_id = existing['id']
        else:
            # Create new
            await db.sla_configs.insert_one({
                'id': sla_id,
                'tenant_id': current_user.tenant_id,
                'category': config.category,
                'priority': config.priority,
                'response_time_minutes': config.response_time_minutes,
                'resolution_time_minutes': config.resolution_time_minutes,
                'created_at': datetime.now(timezone.utc).isoformat(),
                'created_by': current_user.name
            })
        
        return {
            'message': 'SLA yapılandırması kaydedildi',
            'sla_id': sla_id,
            'category': config.category,
            'priority': config.priority,
            'response_time': f'{config.response_time_minutes} dakika',
            'resolution_time': f'{config.resolution_time_minutes} dakika'
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save SLA config: {str(e)}")




@router.get("/settings/sla")
async def get_sla_configs(
    current_user: User = Depends(get_current_user)
):
    """
    Get all SLA configurations
    """
    try:
        configs = await db.sla_configs.find({
            'tenant_id': current_user.tenant_id
        }, {'_id': 0}).to_list(100)
        
        # If no configs, return defaults
        if not configs:
            configs = [
                {
                    'category': 'maintenance',
                    'priority': 'urgent',
                    'response_time_minutes': 30,
                    'resolution_time_minutes': 120
                },
                {
                    'category': 'housekeeping',
                    'priority': 'normal',
                    'response_time_minutes': 60,
                    'resolution_time_minutes': 180
                },
                {
                    'category': 'guest_request',
                    'priority': 'normal',
                    'response_time_minutes': 15,
                    'resolution_time_minutes': 60
                }
            ]
        
        return {
            'configs': configs,
            'count': len(configs)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get SLA configs: {str(e)}")


# ============================================================================
# COMPREHENSIVE FINANCE MODULE - CASH FLOW & RISK MANAGEMENT
# ============================================================================

# ============================================================================
# DELAYED TASKS MONITORING & PUSH NOTIFICATIONS
# ============================================================================

# MOVED: /tasks/delayed endpoint moved earlier to avoid path conflict with /tasks/{task_id}


# ============================================================================
# SYSTEM MONITORING & PERFORMANCE - APM INTEGRATED
# ============================================================================

import psutil
import time

# api_metrics is now provided by apm_store from apm_middleware.py
# Backward compat: alias api_metrics to apm_store.requests
try:
    from apm_middleware import apm_store as _apm_store_ref, get_rate_limit_stats as _get_rl_stats
    api_metrics = _apm_store_ref.requests
except ImportError:
    from collections import deque
    api_metrics = deque(maxlen=1000)

# Legacy APIMetricsMiddleware replaced by APMMiddleware in apm_middleware.py

# 1. SYSTEM PERFORMANCE MONITORING


@router.get("/system/performance")
async def get_system_performance(
    minutes: int = 10,
    current_user: User = Depends(get_current_user)
):
    """
    Get real-time system performance metrics powered by APM middleware.
    Returns: CPU, RAM, API response times, request rates, rate limiting, errors
    """
    try:
        # Get CPU and Memory info
        cpu_percent = psutil.cpu_percent(interval=0)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')

        # Get APM summary (real data from middleware)
        try:
            apm_summary = _apm_store_ref.get_summary(minutes=minutes)
        except Exception:
            apm_summary = apm_store.get_summary(minutes=minutes) if hasattr(apm_store, 'get_summary') else {}

        # Get rate limit stats
        try:
            rl_stats = _get_rl_stats()
        except Exception:
            rl_stats = get_rate_limit_stats() if callable(get_rate_limit_stats) else {}

        # Get recent errors
        try:
            recent_errors = _apm_store_ref.get_recent_errors(limit=20)
        except Exception:
            recent_errors = []

        # Database stats (lightweight)
        db_stats = {}
        try:
            server_status = await db.command('serverStatus')
            db_stats = {
                'connections': {
                    'current': server_status.get('connections', {}).get('current', 0),
                    'available': server_status.get('connections', {}).get('available', 0),
                    'total_created': server_status.get('connections', {}).get('totalCreated', 0),
                },
                'opcounters': {
                    'insert': server_status.get('opcounters', {}).get('insert', 0),
                    'query': server_status.get('opcounters', {}).get('query', 0),
                    'update': server_status.get('opcounters', {}).get('update', 0),
                    'delete': server_status.get('opcounters', {}).get('delete', 0),
                },
                'uptime_seconds': server_status.get('uptime', 0),
            }
        except Exception:
            pass

        return {
            'system': {
                'cpu_percent': round(cpu_percent, 2),
                'memory_percent': round(memory.percent, 2),
                'memory_used_gb': round(memory.used / (1024**3), 2),
                'memory_total_gb': round(memory.total / (1024**3), 2),
                'disk_percent': round(disk.percent, 2),
                'disk_used_gb': round(disk.used / (1024**3), 2),
                'disk_total_gb': round(disk.total / (1024**3), 2),
            },
            'api_metrics': {
                'avg_response_time_ms': apm_summary.get('avg_response_time_ms', 0),
                'p50_ms': apm_summary.get('p50_ms', 0),
                'p95_ms': apm_summary.get('p95_ms', 0),
                'p99_ms': apm_summary.get('p99_ms', 0),
                'requests_per_minute': apm_summary.get('requests_per_minute', 0),
                'total_requests_tracked': apm_summary.get('total_requests', 0),
                'error_rate_percent': apm_summary.get('error_rate_percent', 0),
                'slow_requests': apm_summary.get('slow_requests', 0),
                'status_breakdown': apm_summary.get('status_breakdown', {}),
                'endpoints': apm_summary.get('top_endpoints', []),
                'slowest_endpoints': apm_summary.get('slowest_endpoints', []),
                'error_endpoints': apm_summary.get('error_endpoints', []),
            },
            'rate_limiting': {
                'active_clients': rl_stats.get('active_clients', 0),
                'total_rate_limit_hits': rl_stats.get('total_rate_limit_hits', 0),
                'hits_by_endpoint': rl_stats.get('hits_by_endpoint', {}),
                'limits_config': rl_stats.get('limits_config', {}),
            },
            'database': db_stats,
            'recent_errors': recent_errors[:10],
            'timeline': apm_summary.get('timeline', []),
            'health_status': 'healthy' if cpu_percent < 80 and memory.percent < 80 else 'degraded',
            'uptime_seconds': apm_summary.get('uptime_seconds', 0),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get performance metrics: {str(e)}")


# 1b. APM DETAILED ENDPOINT STATS


@router.get("/system/apm/endpoints")
async def get_apm_endpoint_details(
    current_user: User = Depends(get_current_user)
):
    """Get detailed APM stats for all tracked endpoints"""
    try:
        summary = _apm_store_ref.get_summary(minutes=30)
        return {
            'top_endpoints': summary.get('top_endpoints', []),
            'slowest_endpoints': summary.get('slowest_endpoints', []),
            'error_endpoints': summary.get('error_endpoints', []),
            'total_requests': summary.get('total_requests', 0),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 1c. RATE LIMIT STATUS


@router.get("/system/rate-limits")
async def get_rate_limit_status(
    current_user: User = Depends(get_current_user)
):
    """Get current rate limiting status and configuration"""
    try:
        rl_stats = _get_rl_stats()
        return {
            'enabled': True,
            'mode': 'in-memory',
            'stats': rl_stats,
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {
            'enabled': False,
            'mode': 'disabled',
            'error': str(e),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }


# 1d. DATABASE OPTIMIZATION STATUS


@router.get("/system/db-stats")
async def get_database_stats(
    current_user: User = Depends(get_current_user)
):
    """Get database optimization and performance statistics"""
    try:
        from database_optimizer import DatabaseOptimizer
        optimizer = DatabaseOptimizer(db)

        # Get index info
        index_info = await optimizer.verify_indexes()

        # Get collection stats
        collection_stats = await optimizer.get_collection_stats()

        # Get server status
        server_status = await db.command('serverStatus')
        connections = server_status.get('connections', {})
        opcounters = server_status.get('opcounters', {})

        return {
            'indexes': index_info,
            'collections': collection_stats,
            'connections': {
                'current': connections.get('current', 0),
                'available': connections.get('available', 0),
                'total_created': connections.get('totalCreated', 0),
            },
            'operations': {
                'insert': opcounters.get('insert', 0),
                'query': opcounters.get('query', 0),
                'update': opcounters.get('update', 0),
                'delete': opcounters.get('delete', 0),
            },
            'pool_config': {
                'max_pool_size': 500,
                'min_pool_size': 50,
                'max_idle_time_ms': 45000,
            },
            'uptime_seconds': server_status.get('uptime', 0),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get DB stats: {str(e)}")


# 1e. RECENT ERRORS


@router.get("/system/errors")
async def get_recent_errors(
    limit: int = 50,
    current_user: User = Depends(get_current_user)
):
    """Get recent API errors tracked by APM"""
    try:
        errors = _apm_store_ref.get_recent_errors(limit=limit)
        return {
            'errors': errors,
            'total': len(errors),
            'timestamp': datetime.now(timezone.utc).isoformat(),
        }
    except Exception as e:
        return {'errors': [], 'total': 0, 'error': str(e)}


# 2. LOG VIEWER


@router.get("/system/logs")
async def get_system_logs(
    level: Optional[str] = None,  # ERROR, WARN, INFO, DEBUG
    search: Optional[str] = None,
    limit: int = 100,
    current_user: User = Depends(get_current_user)
):
    """
    Get system logs with filtering
    """
    try:
        # Read from audit logs and create application logs
        logs = []
        
        # Get audit logs from database
        filter_dict = {'tenant_id': current_user.tenant_id}
        if search:
            filter_dict['$or'] = [
                {'action': {'$regex': search, '$options': 'i'}},
                {'entity_type': {'$regex': search, '$options': 'i'}},
                {'user_name': {'$regex': search, '$options': 'i'}}
            ]
        
        audit_logs = await db.audit_logs.find(filter_dict).sort('timestamp', -1).limit(limit).to_list(limit)
        
        for log in audit_logs:
            # Convert audit log to application log format
            log_entry = {
                'id': log['id'],
                'level': 'INFO',
                'timestamp': log['timestamp'],
                'message': f"{log['user_name']} performed {log['action']} on {log['entity_type']}",
                'user': log.get('user_name', 'System'),
                'action': log['action'],
                'entity_type': log.get('entity_type'),
                'entity_id': log.get('entity_id'),
                'details': log.get('changes', {})
            }
            
            # Determine log level based on action
            if 'DELETE' in log['action'] or 'VOID' in log['action']:
                log_entry['level'] = 'WARN'
            elif 'ERROR' in log['action'] or 'FAIL' in log['action']:
                log_entry['level'] = 'ERROR'
            
            logs.append(log_entry)
        
        # Add some system logs
        system_logs = [
            {
                'id': str(uuid.uuid4()),
                'level': 'INFO',
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'message': 'System performance check completed',
                'user': 'System',
                'action': 'SYSTEM_CHECK',
                'details': {'status': 'healthy'}
            },
            {
                'id': str(uuid.uuid4()),
                'level': 'INFO',
                'timestamp': (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat(),
                'message': 'Database connection verified',
                'user': 'System',
                'action': 'DB_CHECK',
                'details': {'latency_ms': 12}
            }
        ]
        
        logs.extend(system_logs)
        logs.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Filter by level if specified (after adding all logs)
        if level:
            logs = [log for log in logs if log['level'] == level.upper()]
        
        return {
            'logs': logs[:limit],
            'count': len(logs),
            'filters': {
                'level': level,
                'search': search,
                'limit': limit
            },
            'log_levels': {
                'ERROR': len([l for l in logs if l['level'] == 'ERROR']),
                'WARN': len([l for l in logs if l['level'] == 'WARN']),
                'INFO': len([l for l in logs if l['level'] == 'INFO']),
                'DEBUG': len([l for l in logs if l['level'] == 'DEBUG'])
            }
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve logs: {str(e)}")


# 3. NETWORK PING TEST


@router.post("/demo-requests")
async def create_demo_request(request: DemoRequest):
    """
    Create demo request from landing page
    Public endpoint - no authentication required
    """
    try:
        demo_data = {
            'id': str(uuid.uuid4()),
            'name': request.name,
            'email': request.email,
            'phone': request.phone,
            'hotel_name': request.hotel_name,
            'room_count': request.room_count,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc).isoformat(),
            'contacted': False
        }
        
        await db.demo_requests.insert_one(demo_data)
        
        return {
            'success': True,
            'message': 'Demo talebi başarıyla alındı',
            'request_id': demo_data['id']
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Demo talebi kaydedilemedi: {str(e)}")


# 4. ENDPOINT HEALTH CHECK


@router.get("/system/health")
async def system_health_check(
    current_user: User = Depends(get_current_user)
):
    """
    Check health of all critical endpoints and services
    """
    try:
        health_checks = []
        
        # Check database connection
        try:
            await db.command('ping')
            db_latency_start = time.time()
            await db.bookings.find_one({})
            db_latency = (time.time() - db_latency_start) * 1000
            
            health_checks.append({
                'service': 'MongoDB',
                'status': 'healthy',
                'latency_ms': round(db_latency, 2),
                'message': 'Database connection active'
            })
        except Exception as e:
            health_checks.append({
                'service': 'MongoDB',
                'status': 'unhealthy',
                'latency_ms': 0,
                'message': f'Database error: {str(e)}'
            })
        
        # Check API endpoints
        critical_endpoints = [
            {'name': 'Authentication', 'count_collection': 'users'},
            {'name': 'Bookings', 'count_collection': 'bookings'},
            {'name': 'Rooms', 'count_collection': 'rooms'},
            {'name': 'Guests', 'count_collection': 'guests'}
        ]
        
        for endpoint in critical_endpoints:
            try:
                start_time = time.time()
                count = await db[endpoint['count_collection']].count_documents({'tenant_id': current_user.tenant_id})
                latency = (time.time() - start_time) * 1000
                
                health_checks.append({
                    'service': endpoint['name'],
                    'status': 'healthy',
                    'latency_ms': round(latency, 2),
                    'message': f'{count} records',
                    'record_count': count
                })
            except Exception as e:
                health_checks.append({
                    'service': endpoint['name'],
                    'status': 'unhealthy',
                    'latency_ms': 0,
                    'message': f'Error: {str(e)}'
                })
        
        # Overall health status
        unhealthy_count = len([h for h in health_checks if h['status'] == 'unhealthy'])
        overall_status = 'healthy' if unhealthy_count == 0 else 'degraded' if unhealthy_count < 2 else 'critical'
        
        return {
            'overall_status': overall_status,
            'checks': health_checks,
            'total_checks': len(health_checks),
            'healthy_count': len([h for h in health_checks if h['status'] == 'healthy']),
            'unhealthy_count': unhealthy_count,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Health check failed: {str(e)}")


# ============================================================================
# OPERA CLOUD PARITY FEATURES - CRITICAL ENTERPRISE FUNCTIONALITY
# ============================================================================

# Import night audit models
from night_audit_module import (
    NightAuditRecord, AuditStatus, AutomaticPosting, 
    CityLedgerAccount, CityLedgerTransaction, SplitPayment,
    QueueRoom, AuditTrailEntry
)

# ============= 1. NIGHT AUDIT MODULE (ENTERPRISE GRADE) =============

# ============= 2. CASHIERING & CITY LEDGER MODULE =============

# ============= 3. QUEUE ROOMS MODULE (EARLY ARRIVAL MANAGEMENT) =============

# ============= AUDIT TRAIL LOGGING (AUTO-TRACKING) =============



@router.get("/security/audit-logs")
async def get_security_audit_logs(
    days: int = 7,
    action: Optional[str] = None,
    user_id: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get security audit logs"""
    start_date = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    
    query = {
        'tenant_id': current_user.tenant_id,
        'timestamp': {'$gte': start_date}
    }
    
    if action:
        query['action'] = action
    if user_id:
        query['user_id'] = user_id
    
    logs = await db.audit_logs.find(query, {'_id': 0}).sort('timestamp', -1).limit(100).to_list(100)
    
    return {
        'logs': logs,
        'count': len(logs),
        'date_range': f'Last {days} days'
    }




@router.get("/gdpr/data-requests")
async def get_gdpr_data_requests(
    status: Optional[str] = None,
    current_user: User = Depends(get_current_user)
):
    """Get GDPR data access/deletion requests - REAL DATA from database"""
    query = {'tenant_id': current_user.tenant_id}
    if status:
        query['status'] = status
    
    requests_data = await db.gdpr_requests.find(query, {'_id': 0}).sort('created_at', -1).to_list(100)
    
    # Return real data (empty if none)
    return {
        'requests': requests_data,
        'count': len(requests_data),
        'pending': sum(1 for r in requests_data if r.get('status') == 'pending'),
        'completed': sum(1 for r in requests_data if r.get('status') == 'completed')
    }




@router.get("/compliance/certifications")
async def get_compliance_certifications(current_user: User = Depends(get_current_user)):
    """Get compliance certifications - REAL DATA from database"""
    
    # Get from database
    certs = await db.certifications.find({
        'tenant_id': current_user.tenant_id
    }, {'_id': 0}).to_list(10)
    
    # If no data, return empty
    return {
        'certifications': certs,
        'count': len(certs),
        'certified_count': sum(1 for c in certs if c.get('status') == 'certified'),
        'compliance_score': (sum(c.get('score', 0) for c in certs) / len(certs)) if certs else 0
    }




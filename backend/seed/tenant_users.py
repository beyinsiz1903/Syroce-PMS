"""Seed sections 1+2: tenant + admin/legacy/staff users.

Writes ctx['tenant_id'], ctx['admin_user_id'], ctx['staff_users_count'].
"""

import random

from seed._helpers import (
    DEMO_EMAIL,
    DEMO_HOTEL_NAME,
    DEMO_PASSWORD,
    _encrypt_doc,
    _now,
    _uuid,
    pwd_context,
)


async def seed_tenant_and_users(db, ctx):
    tenant_id = _uuid()
    admin_user_id = _uuid()
    ctx["tenant_id"] = tenant_id
    ctx["admin_user_id"] = admin_user_id

    # ── 1. Tenant ──────────────────────────────────────────
    tenant = {
        "id": tenant_id,
        "hotel_id": "100001",
        "name": DEMO_HOTEL_NAME,
        "property_name": DEMO_HOTEL_NAME,
        "property_type": "hotel",
        "contact_email": DEMO_EMAIL,
        "contact_phone": "+905551234567",
        "address": "Antalya, Türkiye",
        "total_rooms": 30,
        "subscription_status": "active",
        "subscription_start_date": None,
        "subscription_end_date": None,
        "subscription_tier": "enterprise",
        "plan": "enterprise",
        "subscription_plan": None,
        "location": "Antalya",
        "amenities": ["Pool", "Spa", "Restaurant", "Bar", "Gym", "WiFi", "Parking"],
        "created_at": _now().isoformat(),
        "modules": {
            "pms": True,
            "reports": True,
            "invoices": True,
            "ai": True,
            "channel_manager": True,
            "rms": True,
            "housekeeping": True,
            "reservation_calendar": True,
            "loyalty": True,
            "marketplace": True,
            "maintenance": True,
            "night_audit": True,
            "folio_management": True,
            "cost_management": True,
            "sales_crm": True,
            "group_sales": True,
            "gm_dashboards": True,
            "mobile_housekeeping": True,
            "rate_management": True,
            "basic_reporting": True,
            "revenue_management": True,
            "advanced_analytics": True,
        },
        "features": {
            "hidden_rms": True,
            "hidden_channel_manager": True,
        },
    }
    await db.tenants.insert_one(tenant)

    # ── 2. Admin user ──────────────────────────────────────
    admin_user = {
        "id": admin_user_id,
        "tenant_id": tenant_id,
        "agency_id": None,
        "email": DEMO_EMAIL,
        "name": "Demo Admin",
        "role": "super_admin",
        "phone": "+905551234567",
        "is_active": True,
        "email_verified": True,
        "email_verified_at": _now().isoformat(),
        "hashed_password": pwd_context.hash(DEMO_PASSWORD),
        "created_at": _now().isoformat(),
    }
    admin_user = _encrypt_doc(admin_user, "users")
    await db.users.insert_one(admin_user)

    # Backward-compatible alias account (used by legacy tests / docs).
    # Same role + password, separate user id and email.
    legacy_admin = {
        "id": _uuid(),
        "tenant_id": tenant_id,
        "agency_id": None,
        "email": "demo@hotel.com",
        "name": "Demo Admin (Legacy)",
        "role": "super_admin",
        "phone": "+905551234567",
        "is_active": True,
        "email_verified": True,
        "email_verified_at": _now().isoformat(),
        "hashed_password": pwd_context.hash(DEMO_PASSWORD),
        "created_at": _now().isoformat(),
    }
    legacy_admin = _encrypt_doc(legacy_admin, "users")
    await db.users.insert_one(legacy_admin)

    # Extra staff users
    # NOTE: `tenantadmin@hotel.com` (role=admin) covers the tenant-scoped admin
    # path — distinct from `super_admin`. Used by monitoring auth tests
    # (task #57) to verify `require_op("view_system_diagnostics")` admits a
    # plain tenant admin while still rejecting cross-tenant endpoints.
    # Tenant-scoped admin (role=admin, NOT super_admin) — used by
    # tests/test_monitoring_auth.py to verify the require_op gate on
    # /api/channel-manager/monitoring/dispatch-config*.
    staff_users = [
        {"name": "Tenant Admin", "email": "tenantadmin@hotel.com", "role": "admin"},
        {"name": "Front Desk Agent", "email": "frontdesk@hotel.com", "role": "front_desk"},
        {"name": "Housekeeping Mgr", "email": "housekeeping@hotel.com", "role": "housekeeping"},
        {"name": "Finance Manager", "email": "finance@hotel.com", "role": "finance"},
        {"name": "Sales Manager", "email": "sales@hotel.com", "role": "sales"},
    ]
    for su in staff_users:
        staff_doc = {
            "id": _uuid(),
            "tenant_id": tenant_id,
            "agency_id": None,
            "email": su["email"],
            "name": su["name"],
            "role": su["role"],
            "phone": f"+90555{random.randint(1000000, 9999999)}",
            "is_active": True,
            "email_verified": True,
            "email_verified_at": _now().isoformat(),
            "hashed_password": pwd_context.hash("staff123"),
            "created_at": _now().isoformat(),
        }
        staff_doc = _encrypt_doc(staff_doc, "users")
        await db.users.insert_one(staff_doc)

    ctx["staff_users_count"] = len(staff_users)

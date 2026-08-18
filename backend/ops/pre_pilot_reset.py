"""Fail-closed pre-pilot reset planning and module-user seeding.

Nothing in this module runs on import.  The companion CLI defaults to dry-run
and every write path requires explicit execution gates.  Provider APIs are not
imported or called.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

from models.enums import Permission, UserRole
from modules.pms_core.module_scope_service import normalize_module_scopes

RESET_CONFIRMATION = "DELETE_PRELIVE_DATA_KEEP_SUPER_ADMIN"
PRODUCTION_CONFIRMATION = "I_UNDERSTAND_PRE_PILOT_PRODUCTION_RESET"
SEED_CONFIRMATION = "SEED_MODULE_SCOPED_USERS"
TENANT_MARKER_FIELDS = (
    "tenant_id",
    "tenantId",
    "hotel_id",
    "hotelId",
    "property_id",
    "propertyId",
    "organization_id",
    "org_id",
)

# Platform/control-plane collections must never be selected by the reset
# planner.  Unknown collections are inspected and any tenant-owned rows block
# execution until the allowlist is deliberately reviewed in code.
PRESERVED_COLLECTIONS = frozenset(
    {
        "alembic_version",
        "feature_flags",
        "migration_history",
        "migrations",
        "module_catalog",
        "pre_pilot_reset_runs",
        "schema_migrations",
        "system_settings",
    }
)

# Explicit tenant-owned operational data.  The planner only selects documents
# carrying a recognized tenant/property marker and never performs an implicit
# database-wide collection wipe.
OPERATIONAL_COLLECTION_ALLOWLIST = frozenset(
    {
        "accounting_entries",
        "activity_logs",
        "allotments",
        "approvals",
        "ar_transactions",
        "ari_dlq",
        "ari_outbox",
        "ari_snapshots",
        "audit_logs",
        "availability_reconciliation",
        "bank_reconciliations",
        "bank_transactions",
        "billing_history",
        "block_allocations",
        "booking_audit_logs",
        "booking_events",
        "booking_holds",
        "bookings",
        "cash_drawers",
        "cash_transactions",
        "cashier_sessions",
        "channel_connections",
        "channel_mappings",
        "channel_reservations",
        "channel_sync_logs",
        "city_ledger_accounts",
        "city_ledger_transactions",
        "companies",
        "contracts",
        "conversations",
        "corporate_accounts",
        "crm_notes",
        "crm_tasks",
        "departments",
        "deposit_transactions",
        "deposits",
        "eod_reports",
        "employee_documents",
        "employees",
        "entitlement_quota_usage",
        "exely_connections",
        "exely_events",
        "exely_mappings",
        "fnb_costing",
        "folio_entries",
        "folio_items",
        "folio_operations",
        "folio_transactions",
        "folios",
        "general_ledger_accounts",
        "goods_receipts",
        "group_blocks",
        "group_bookings",
        "guest_documents",
        "guest_journeys",
        "guest_notes",
        "guest_profiles",
        "guest_requests",
        "guests",
        "hotel_crm_notes",
        "hotel_crm_tasks",
        "hotelrunner_connections",
        "hotelrunner_events",
        "hotelrunner_mappings",
        "housekeeping_assignments",
        "housekeeping_logs",
        "housekeeping_tasks",
        "id_photo_access_logs",
        "id_photos",
        "integration_connections",
        "inventory_items",
        "inventory_movements",
        "invoice_events",
        "invoice_items",
        "invoice_ledger_links",
        "invoice_sync",
        "invoices",
        "journal_entries",
        "leave_requests",
        "lost_found_items",
        "maintenance_history",
        "maintenance_tasks",
        "maintenance_work_orders",
        "messages",
        "night_audit_runs",
        "nilvera_credit_allocations",
        "nilvera_credit_consumptions",
        "nilvera_credit_ledger",
        "notifications",
        "operational_events",
        "outbox_events",
        "payment_transactions",
        "payments",
        "payroll_items",
        "payroll_runs",
        "positions",
        "pos_order_items",
        "pos_orders",
        "pos_payments",
        "pos_sessions",
        "pos_tables",
        "precheckins",
        "procurement_approvals",
        "procurement_requests",
        "provider_credentials",
        "purchase_order_items",
        "purchase_orders",
        "refunds",
        "reservations",
        "room_assignments",
        "room_blocks",
        "room_images",
        "room_outages",
        "room_status_history",
        "room_types",
        "rooms",
        "sales_activities",
        "sales_leads",
        "security_events",
        "shift_handovers",
        "shifts",
        "stock_items",
        "stock_movements",
        "suppliers",
        "task_comments",
        "tasks",
        "tenant_configs",
        "tenant_settings",
        "travel_agent_transactions",
        "urgent_messages",
        "user_notifications",
        "wake_up_calls",
        "warehouses",
        "web_push_metrics",
    }
)

# Authentication/session residue is user-owned rather than tenant-owned.  It is
# deleted for non-super-admin users only, preserving the protected account.
USER_OWNED_EPHEMERAL_COLLECTIONS = frozenset(
    {
        "auth_challenges",
        "email_verification_tokens",
        "login_attempts",
        "password_reset_tokens",
        "push_subscriptions",
        "refresh_tokens",
        "user_sessions",
    }
)


@dataclass(frozen=True)
class ModuleUserProfile:
    key: str
    display_name: str
    module_scopes: tuple[str, ...]
    granted_permissions: tuple[str, ...]
    role: str = UserRole.STAFF.value


_COMMON_SCOPES = ("dashboard", "profile")


def _permission_values(*permissions: Permission) -> tuple[str, ...]:
    return tuple(permission.value for permission in permissions)


MODULE_USER_PROFILES: tuple[ModuleUserProfile, ...] = (
    ModuleUserProfile(
        "frontdesk",
        "Ön Büro Test Kullanıcısı",
        _COMMON_SCOPES
        + (
            "pms",
            "reservation_calendar",
            "guests",
            "booking_engine",
            "guest_advanced",
            "pms_operations",
            "walkin",
            "room_map",
            "departure_list",
            "no_show_today",
        ),
        _permission_values(
            Permission.VIEW_BOOKINGS,
            Permission.CREATE_BOOKING,
            Permission.EDIT_BOOKING,
            Permission.CHECKIN,
            Permission.CHECKOUT,
            Permission.VIEW_FOLIO,
        ),
    ),
    ModuleUserProfile(
        "housekeeping",
        "Housekeeping Test Kullanıcısı",
        _COMMON_SCOPES + ("housekeeping", "mobile_housekeeping", "pms_mobile"),
        _permission_values(
            Permission.VIEW_HK_BOARD,
            Permission.UPDATE_ROOM_STATUS,
            Permission.ASSIGN_TASK,
        ),
    ),
    ModuleUserProfile(
        "cashier",
        "Kasa Test Kullanıcısı",
        _COMMON_SCOPES + ("cashier", "folio_management", "folio_detail"),
        _permission_values(
            Permission.VIEW_FOLIO,
            Permission.POST_CHARGE,
            Permission.POST_PAYMENT,
            Permission.VOID_CHARGE,
            Permission.TRANSFER_FOLIO,
            Permission.CLOSE_FOLIO,
        ),
    ),
    ModuleUserProfile(
        "finance",
        "Finans Test Kullanıcısı",
        _COMMON_SCOPES
        + (
            "finance",
            "cost_management",
            "general_ledger",
            "bank_reconciliation",
            "city_ledger",
        ),
        _permission_values(
            Permission.VIEW_FOLIO,
            Permission.VIEW_REPORTS,
            Permission.VIEW_FINANCIAL_REPORTS,
            Permission.EXPORT_DATA,
            Permission.VIEW_COMPANIES,
        ),
    ),
    ModuleUserProfile(
        "invoices",
        "E-Fatura Test Kullanıcısı",
        _COMMON_SCOPES + ("invoices", "invoices_basic"),
        _permission_values(
            Permission.VIEW_FOLIO,
            Permission.VIEW_FINANCIAL_REPORTS,
            Permission.EXPORT_DATA,
        ),
    ),
    ModuleUserProfile(
        "pos",
        "POS Test Kullanıcısı",
        _COMMON_SCOPES + ("pos", "pos_fnb", "pos_dashboard"),
        _permission_values(
            Permission.VIEW_FOLIO,
            Permission.POST_CHARGE,
            Permission.POST_PAYMENT,
        ),
    ),
    ModuleUserProfile(
        "stock",
        "Stok Test Kullanıcısı",
        _COMMON_SCOPES + ("inventory", "stock_rehber"),
        _permission_values(Permission.VIEW_PROCUREMENT),
    ),
    ModuleUserProfile(
        "procurement",
        "Satın Alma Test Kullanıcısı",
        _COMMON_SCOPES + ("procurement", "supplies_market"),
        _permission_values(
            Permission.VIEW_PROCUREMENT,
            Permission.MANAGE_PROCUREMENT,
        ),
    ),
    ModuleUserProfile(
        "hr",
        "İnsan Kaynakları Test Kullanıcısı",
        _COMMON_SCOPES + ("hr",),
        _permission_values(Permission.VIEW_HR, Permission.MANAGE_HR),
    ),
    ModuleUserProfile(
        "reports",
        "Raporlar Test Kullanıcısı",
        _COMMON_SCOPES + ("reports", "basic_reporting", "advanced_analytics", "analytics_export"),
        _permission_values(Permission.VIEW_REPORTS, Permission.EXPORT_DATA),
    ),
    ModuleUserProfile(
        "channel",
        "Kanal Yöneticisi Test Kullanıcısı",
        _COMMON_SCOPES + ("channel_manager", "channels", "channels_hub"),
        (),
    ),
    ModuleUserProfile(
        "sales",
        "Satış Test Kullanıcısı",
        _COMMON_SCOPES + ("sales", "sales_crm", "group_sales", "companies"),
        _permission_values(
            Permission.VIEW_COMPANIES,
            Permission.CREATE_COMPANY,
            Permission.EDIT_COMPANY,
        ),
    ),
    ModuleUserProfile(
        "tasks",
        "Görevler Test Kullanıcısı",
        _COMMON_SCOPES + ("tasks", "shift_handover"),
        _permission_values(Permission.ASSIGN_TASK),
    ),
    ModuleUserProfile(
        "maintenance",
        "Teknik Servis Test Kullanıcısı",
        _COMMON_SCOPES + ("maintenance",),
        _permission_values(Permission.ASSIGN_TASK, Permission.UPDATE_ROOM_STATUS),
    ),
)


@dataclass(frozen=True)
class CollectionPlan:
    collection: str
    delete_filter: dict[str, Any]
    candidate_count: int
    protected_count: int = 0
    unscoped_count: int = 0


@dataclass(frozen=True)
class ResetPlan:
    database_name: str
    super_admin_count: int
    super_admin_ids: tuple[str, ...]
    protected_tenant_ids: tuple[str, ...]
    non_super_admin_user_count: int
    removable_tenant_count: int
    collections: tuple[CollectionPlan, ...]
    unknown_tenant_collections: tuple[str, ...]
    unknown_tenant_document_count: int

    @property
    def blockers(self) -> tuple[str, ...]:
        blockers: list[str] = []
        if self.super_admin_count < 1:
            blockers.append("BLOCKED_SUPER_ADMIN_NOT_FOUND")
        if self.unknown_tenant_collections:
            blockers.append("BLOCKED_UNKNOWN_TENANT_COLLECTIONS")
        return tuple(blockers)

    def public_summary(self) -> dict[str, Any]:
        """Return a PII-free JSON-serializable summary."""

        return {
            "database_name": self.database_name,
            "super_admin_count": self.super_admin_count,
            "protected_tenant_count": len(self.protected_tenant_ids),
            "non_super_admin_user_count": self.non_super_admin_user_count,
            "removable_tenant_count": self.removable_tenant_count,
            "collection_candidates": [
                {
                    "collection": item.collection,
                    "candidate_count": item.candidate_count,
                    "protected_count": item.protected_count,
                    "unscoped_count": item.unscoped_count,
                }
                for item in self.collections
            ],
            "unknown_tenant_collections": list(self.unknown_tenant_collections),
            "unknown_tenant_document_count": self.unknown_tenant_document_count,
            "blockers": list(self.blockers),
            "write_count": 0,
        }


@dataclass(frozen=True)
class ModuleUserSpec:
    id: str
    tenant_id: str
    email: str
    username: str
    name: str
    role: str
    module_scopes: tuple[str, ...]
    granted_permissions: tuple[str, ...]

    def public_summary(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("email", None)
        return data


def super_admin_filter() -> dict[str, Any]:
    return {"$or": [{"role": UserRole.SUPER_ADMIN.value}, {"roles": UserRole.SUPER_ADMIN.value}]}


def non_super_admin_filter() -> dict[str, Any]:
    return {"$nor": [{"role": UserRole.SUPER_ADMIN.value}, {"roles": UserRole.SUPER_ADMIN.value}]}


def tenant_data_filter(protected_tenant_ids: Sequence[str] = ()) -> dict[str, Any]:
    protected = tuple(value for value in protected_tenant_ids if value)
    clauses: list[dict[str, Any]] = []
    for field in TENANT_MARKER_FIELDS:
        predicate: dict[str, Any] = {"$exists": True}
        if protected:
            predicate["$nin"] = list(protected)
        clauses.append({field: predicate})
    return {"$or": clauses}


def protected_tenant_filter(protected_tenant_ids: Sequence[str]) -> dict[str, Any]:
    protected = tuple(value for value in protected_tenant_ids if value)
    if not protected:
        return {"_id": {"$exists": False}}
    return {
        "$or": [
            {field: {"$in": list(protected)}}
            for field in TENANT_MARKER_FIELDS
        ]
    }


def tenant_delete_filter(protected_tenant_ids: Sequence[str]) -> dict[str, Any]:
    protected = tuple(value for value in protected_tenant_ids if value)
    if not protected:
        return {}
    return {
        "$nor": [
            {"id": {"$in": list(protected)}},
            {"_id": {"$in": list(protected)}},
        ]
    }


def user_ephemeral_filter(super_admin_ids: Sequence[str]) -> dict[str, Any]:
    protected = tuple(value for value in super_admin_ids if value)
    if not protected:
        return {}
    return {"user_id": {"$nin": list(protected)}}


def _database_name(database: Any) -> str:
    name = getattr(database, "name", None)
    return str(name or "unknown")


async def build_reset_plan(database: Any) -> ResetPlan:
    """Inspect the database without mutating it."""

    super_admin_docs = await database.users.find(
        super_admin_filter(),
        {"_id": 0, "id": 1, "tenant_id": 1},
    ).to_list(length=None)
    super_admin_ids = tuple(
        sorted(str(doc.get("id")) for doc in super_admin_docs if doc.get("id"))
    )
    protected_tenant_ids = tuple(
        sorted({str(doc.get("tenant_id")) for doc in super_admin_docs if doc.get("tenant_id")})
    )

    collection_names = set(await database.list_collection_names())
    plans: list[CollectionPlan] = []

    if "users" in collection_names:
        plans.append(
            CollectionPlan(
                collection="users",
                delete_filter=non_super_admin_filter(),
                candidate_count=await database.users.count_documents(non_super_admin_filter()),
                protected_count=len(super_admin_docs),
            )
        )

    removable_tenant_count = 0
    if "tenants" in collection_names:
        tenant_filter = tenant_delete_filter(protected_tenant_ids)
        removable_tenant_count = await database.tenants.count_documents(tenant_filter)
        plans.append(
            CollectionPlan(
                collection="tenants",
                delete_filter=tenant_filter,
                candidate_count=removable_tenant_count,
                protected_count=await database.tenants.count_documents(
                    {
                        "$or": [
                            {"id": {"$in": list(protected_tenant_ids)}},
                            {"_id": {"$in": list(protected_tenant_ids)}},
                        ]
                    }
                )
                if protected_tenant_ids
                else 0,
            )
        )

    tenant_filter = tenant_data_filter(protected_tenant_ids)
    protected_filter = protected_tenant_filter(protected_tenant_ids)
    for name in sorted(collection_names & OPERATIONAL_COLLECTION_ALLOWLIST):
        collection = database[name]
        total = await collection.count_documents({})
        candidates = await collection.count_documents(tenant_filter)
        protected_count = (
            await collection.count_documents(protected_filter)
            if protected_tenant_ids
            else 0
        )
        unscoped = max(total - candidates - protected_count, 0)
        plans.append(
            CollectionPlan(
                collection=name,
                delete_filter=tenant_filter,
                candidate_count=candidates,
                protected_count=protected_count,
                unscoped_count=unscoped,
            )
        )

    ephemeral_filter = user_ephemeral_filter(super_admin_ids)
    for name in sorted(collection_names & USER_OWNED_EPHEMERAL_COLLECTIONS):
        collection = database[name]
        candidates = await collection.count_documents(ephemeral_filter)
        plans.append(
            CollectionPlan(
                collection=name,
                delete_filter=ephemeral_filter,
                candidate_count=candidates,
            )
        )

    handled = (
        OPERATIONAL_COLLECTION_ALLOWLIST
        | USER_OWNED_EPHEMERAL_COLLECTIONS
        | PRESERVED_COLLECTIONS
        | {"users", "tenants"}
    )
    unknown_tenant_collections: list[str] = []
    unknown_tenant_document_count = 0
    for name in sorted(collection_names - handled):
        if name.startswith("system."):
            continue
        candidate_count = await database[name].count_documents(tenant_filter)
        if candidate_count:
            unknown_tenant_collections.append(name)
            unknown_tenant_document_count += candidate_count

    return ResetPlan(
        database_name=_database_name(database),
        super_admin_count=len(super_admin_docs),
        super_admin_ids=super_admin_ids,
        protected_tenant_ids=protected_tenant_ids,
        non_super_admin_user_count=next(
            (
                item.candidate_count
                for item in plans
                if item.collection == "users"
            ),
            0,
        ),
        removable_tenant_count=removable_tenant_count,
        collections=tuple(plans),
        unknown_tenant_collections=tuple(unknown_tenant_collections),
        unknown_tenant_document_count=unknown_tenant_document_count,
    )


def detect_environment(environ: Mapping[str, str] | None = None) -> str:
    env = environ or os.environ
    for key in ("APP_ENV", "ENVIRONMENT", "ENV"):
        value = str(env.get(key, "")).strip().lower()
        if value:
            return value
    return "unknown"


def validate_reset_execution_guard(
    *,
    execute: bool,
    confirmation: str | None,
    production_confirmation: str | None,
    expected_database_name: str | None,
    expected_super_admin_count: int,
    plan: ResetPlan,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Validate all destructive reset gates; dry-run always remains read-only."""

    if not execute:
        return
    env = environ or os.environ
    if env.get("PRE_PILOT_RESET_ALLOWED") != "1":
        raise RuntimeError("BLOCKED_PRE_PILOT_RESET_NOT_ALLOWED")
    if confirmation != RESET_CONFIRMATION:
        raise RuntimeError("BLOCKED_PRE_PILOT_RESET_CONFIRMATION")
    if not expected_database_name or expected_database_name != plan.database_name:
        raise RuntimeError("BLOCKED_PRE_PILOT_RESET_DATABASE_MISMATCH")
    if expected_super_admin_count < 1 or plan.super_admin_count != expected_super_admin_count:
        raise RuntimeError("BLOCKED_PRE_PILOT_RESET_SUPER_ADMIN_COUNT")
    if plan.blockers:
        raise RuntimeError(plan.blockers[0])

    environment = detect_environment(env)
    if environment in {"prod", "production"}:
        if env.get("PRE_PILOT_RESET_PRODUCTION_ALLOWED") != "1":
            raise RuntimeError("BLOCKED_PRE_PILOT_PRODUCTION_RESET_NOT_ALLOWED")
        if production_confirmation != PRODUCTION_CONFIRMATION:
            raise RuntimeError("BLOCKED_PRE_PILOT_PRODUCTION_CONFIRMATION")


def validate_seed_execution_guard(
    *,
    execute: bool,
    confirmation: str | None,
    expected_database_name: str | None,
    actual_database_name: str,
    environ: Mapping[str, str] | None = None,
) -> None:
    if not execute:
        return
    env = environ or os.environ
    if env.get("PRE_PILOT_RBAC_SEED_ALLOWED") != "1":
        raise RuntimeError("BLOCKED_PRE_PILOT_RBAC_SEED_NOT_ALLOWED")
    if confirmation != SEED_CONFIRMATION:
        raise RuntimeError("BLOCKED_PRE_PILOT_RBAC_SEED_CONFIRMATION")
    if not expected_database_name or expected_database_name != actual_database_name:
        raise RuntimeError("BLOCKED_PRE_PILOT_RBAC_SEED_DATABASE_MISMATCH")


def build_module_user_specs(tenant_id: str, email_domain: str) -> tuple[ModuleUserSpec, ...]:
    tenant_id = tenant_id.strip()
    domain = email_domain.strip().lower().lstrip("@")
    if not tenant_id:
        raise ValueError("tenant_id is required")
    if not domain or "." not in domain or any(char.isspace() for char in domain):
        raise ValueError("email_domain is invalid")

    specs: list[ModuleUserSpec] = []
    for profile in MODULE_USER_PROFILES:
        user_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"syroce:module-user:{tenant_id}:{profile.key}"))
        specs.append(
            ModuleUserSpec(
                id=user_id,
                tenant_id=tenant_id,
                email=f"{profile.key}@{domain}",
                username=profile.key,
                name=profile.display_name,
                role=profile.role,
                module_scopes=normalize_module_scopes(profile.module_scopes),
                granted_permissions=tuple(sorted(set(profile.granted_permissions))),
            )
        )
    return tuple(specs)


async def execute_reset(database: Any, plan: ResetPlan) -> dict[str, int]:
    """Execute exactly the precomputed allowlisted plan."""

    if plan.blockers:
        raise RuntimeError(plan.blockers[0])

    run_id = str(uuid.uuid4())
    started_at = datetime.now(UTC).isoformat()
    await database.pre_pilot_reset_runs.insert_one(
        {
            "id": run_id,
            "status": "running",
            "started_at": started_at,
            "database_name": plan.database_name,
            "super_admin_count": plan.super_admin_count,
        }
    )

    deleted: dict[str, int] = {}
    # Identity roots are removed last so tenant/user references remain available
    # while operational collections are being cleared.
    ordered = sorted(
        plan.collections,
        key=lambda item: (item.collection in {"users", "tenants"}, item.collection),
    )
    try:
        for item in ordered:
            result = await database[item.collection].delete_many(item.delete_filter)
            deleted[item.collection] = int(result.deleted_count)

        remaining_admins = await database.users.find(
            super_admin_filter(),
            {"_id": 0, "id": 1},
        ).to_list(length=None)
        remaining_ids = tuple(
            sorted(str(doc.get("id")) for doc in remaining_admins if doc.get("id"))
        )
        if remaining_ids != plan.super_admin_ids:
            raise RuntimeError("BLOCKED_SUPER_ADMIN_POST_RESET_MISMATCH")

        await database.pre_pilot_reset_runs.update_one(
            {"id": run_id},
            {
                "$set": {
                    "status": "completed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "deleted_counts": deleted,
                }
            },
        )
        return deleted
    except Exception as exc:
        await database.pre_pilot_reset_runs.update_one(
            {"id": run_id},
            {
                "$set": {
                    "status": "failed",
                    "failed_at": datetime.now(UTC).isoformat(),
                    "error_type": type(exc).__name__,
                    "deleted_counts": deleted,
                }
            },
        )
        raise


async def seed_module_users(
    database: Any,
    *,
    tenant_id: str,
    email_domain: str,
    password: str,
) -> dict[str, int]:
    """Idempotently upsert deterministic, seed-managed module users."""

    if len(password) < 12:
        raise RuntimeError("BLOCKED_PRE_PILOT_RBAC_SEED_PASSWORD_TOO_SHORT")
    tenant = await database.tenants.find_one(
        {"$or": [{"id": tenant_id}, {"_id": tenant_id}]},
        {"_id": 0, "id": 1},
    )
    if not tenant:
        raise RuntimeError("BLOCKED_PRE_PILOT_RBAC_SEED_TENANT_NOT_FOUND")

    from core.security import hash_password
    from security.encrypted_lookup import encrypt_user_doc

    now = datetime.now(UTC).isoformat()
    hashed_password = hash_password(password)
    created = 0
    updated = 0
    for spec in build_module_user_specs(tenant_id, email_domain):
        username_collision = await database.users.find_one(
            {
                "tenant_id": tenant_id,
                "username": spec.username,
                "id": {"$ne": spec.id},
            },
            {"_id": 0, "id": 1},
        )
        if username_collision:
            raise RuntimeError("BLOCKED_PRE_PILOT_RBAC_SEED_USERNAME_COLLISION")

        existing = await database.users.find_one({"id": spec.id}, {"_id": 0, "id": 1})
        document = encrypt_user_doc(
            {
                "id": spec.id,
                "tenant_id": spec.tenant_id,
                "email": spec.email,
                "username": spec.username,
                "name": spec.name,
                "role": spec.role,
                "module_scopes": list(spec.module_scopes),
                "granted_permissions": list(spec.granted_permissions),
                "hashed_password": hashed_password,
                "is_active": True,
                "status": "active",
                "email_verified": True,
                "seed_managed": True,
                "seed_profile": spec.username,
                "updated_at": now,
                "created_at": now,
            }
        )
        await database.users.replace_one({"id": spec.id}, document, upsert=True)
        if existing:
            updated += 1
        else:
            created += 1

    return {"created": created, "updated": updated, "total": created + updated}

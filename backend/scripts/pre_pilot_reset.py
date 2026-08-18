#!/usr/bin/env python3
"""Fail-closed pre-pilot reset and module-user seed utility.

The command is intentionally safe by default:

* Every invocation is a dry-run unless ``--execute`` is supplied.
* Reset execution requires an environment gate, an exact confirmation phrase,
  an exact database name, a backup reference, an expected active super-admin,
  and the digest from a reviewed dry-run plan.
* The reset uses explicit collection allowlists and scoped filters. It never
  drops a database or collection.
* Every ``super_admin`` user is protected by query and post-condition checks.
* Module users are created only by the separate ``seed-module-users`` command
  and only for an explicitly selected tenant.
* No external provider client is imported or called.

Examples (read-only):

    cd backend
    python scripts/pre_pilot_reset.py reset --all-non-super-admin-tenants \
        --all-non-super-admin-users

    python scripts/pre_pilot_reset.py seed-module-users \
        --tenant-id <pilot-tenant-id>

Execution is deliberately more verbose. See docs/operations/PRE_PILOT_RESET.md.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import secrets
import stat
import sys
import uuid
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

RESET_CONFIRMATION = "RESET_PRE_LIVE_SYROCE"
SEED_CONFIRMATION = "SEED_MODULE_QA_USERS"
RESET_ENV_GATE = "ALLOW_PRE_PILOT_RESET"
SEED_ENV_GATE = "ALLOW_MODULE_RBAC_SEED"
SUPER_ADMIN_ROLE = "super_admin"
_PLAN_DIGEST_PATTERN = re.compile(r"^[a-f0-9]{64}$")
_EMAIL_DOMAIN_PATTERN = re.compile(
    r"^(?=.{3,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$"
)


@dataclass(frozen=True)
class CollectionSpec:
    """One explicitly approved tenant-scoped operational collection."""

    name: str
    tenant_fields: tuple[str, ...] = ("tenant_id",)
    category: str = "operational"


@dataclass(frozen=True)
class UserLinkedCollectionSpec:
    """One collection whose records are scoped to deleted user IDs."""

    name: str
    user_fields: tuple[str, ...] = ("user_id",)


# Conservative allowlist. Unknown/new collections are intentionally untouched
# until they are reviewed and added here with an appropriate tenant field.
RESET_COLLECTIONS: tuple[CollectionSpec, ...] = (
    CollectionSpec("booking_holds"),
    CollectionSpec("booking_events"),
    CollectionSpec("booking_history"),
    CollectionSpec("reservations"),
    CollectionSpec("bookings"),
    CollectionSpec("guests"),
    CollectionSpec("guest_profiles"),
    CollectionSpec("guest_requests"),
    CollectionSpec("folios"),
    CollectionSpec("folio_items"),
    CollectionSpec("folio_operations"),
    CollectionSpec("payments"),
    CollectionSpec("payment_transactions"),
    CollectionSpec("cash_sessions"),
    CollectionSpec("cash_transactions"),
    CollectionSpec("city_ledger_accounts"),
    CollectionSpec("invoices"),
    CollectionSpec("invoice_events"),
    CollectionSpec("invoice_sync"),
    CollectionSpec("rooms"),
    CollectionSpec("room_types"),
    CollectionSpec("room_outages"),
    CollectionSpec("room_status_history"),
    CollectionSpec("housekeeping_tasks"),
    CollectionSpec("housekeeping_inspections"),
    CollectionSpec("lost_found_items"),
    CollectionSpec("maintenance_tasks"),
    CollectionSpec("maintenance_work_orders"),
    CollectionSpec("tasks"),
    CollectionSpec("task_comments"),
    CollectionSpec("pos_orders"),
    CollectionSpec("pos_order_items"),
    CollectionSpec("pos_payments"),
    CollectionSpec("outlets"),
    CollectionSpec("menu_items"),
    CollectionSpec("stock_items"),
    CollectionSpec("stock_movements"),
    CollectionSpec("inventory_items"),
    CollectionSpec("inventory_movements"),
    CollectionSpec("warehouses"),
    CollectionSpec("suppliers"),
    CollectionSpec("purchase_requests"),
    CollectionSpec("purchase_orders"),
    CollectionSpec("purchase_order_items"),
    CollectionSpec("goods_receipts"),
    CollectionSpec("employees"),
    CollectionSpec("departments"),
    CollectionSpec("positions"),
    CollectionSpec("shifts"),
    CollectionSpec("leave_requests"),
    CollectionSpec("payroll_runs"),
    CollectionSpec("companies"),
    CollectionSpec("agencies"),
    CollectionSpec("corporate_contracts"),
    CollectionSpec("channel_mappings"),
    CollectionSpec("channel_sync_logs"),
    CollectionSpec("channel_reservations"),
    CollectionSpec("rate_plans"),
    CollectionSpec("daily_rates"),
    CollectionSpec("restrictions"),
    CollectionSpec("notifications"),
    CollectionSpec("messages"),
    CollectionSpec("conversations"),
    CollectionSpec("web_push_subscriptions"),
    CollectionSpec("tenant_settings"),
    CollectionSpec("tenant_integrations"),
    CollectionSpec("nilvera_credit_allocations"),
    CollectionSpec("nilvera_credit_consumptions"),
    CollectionSpec("nilvera_credit_audit"),
)

# Authentication/session residue is scoped by the user IDs selected for
# deletion, not by a broad empty query.
USER_LINKED_COLLECTIONS: tuple[UserLinkedCollectionSpec, ...] = (
    UserLinkedCollectionSpec("refresh_tokens"),
    UserLinkedCollectionSpec("user_sessions"),
    UserLinkedCollectionSpec("password_reset_tokens"),
    UserLinkedCollectionSpec("two_factor_challenges"),
    UserLinkedCollectionSpec("notification_preferences"),
    UserLinkedCollectionSpec("device_tokens"),
)

# Security, migration, platform billing, and system configuration are not part
# of the default allowlist. Tenant-scoped operational audit can be included
# only by an explicit flag and remains separately reviewable.
OPTIONAL_OPERATIONAL_AUDIT_COLLECTIONS: tuple[CollectionSpec, ...] = (
    CollectionSpec("audit_logs", category="operational_audit"),
    CollectionSpec("activity_logs", category="operational_audit"),
    CollectionSpec("operation_logs", category="operational_audit"),
)

PRESERVED_COLLECTION_NAMES = frozenset(
    {
        "alembic_version",
        "migrations",
        "schema_migrations",
        "system_settings",
        "platform_settings",
        "security_events",
        "security_audit_logs",
        "login_attempts",
        "subscriptions",
        "billing_events",
        "provider_credentials",
        "nilvera_credit_purchases",
    }
)


@dataclass(frozen=True)
class ModuleUserSpec:
    slug: str
    display_name: str
    role: str
    module_scope: str
    operation_permissions: tuple[str, ...] = ()


MODULE_USER_SPECS: tuple[ModuleUserSpec, ...] = (
    ModuleUserSpec(
        "frontdesk",
        "QA Front Desk",
        "front_desk",
        "frontdesk",
        ("view_bookings", "create_booking", "edit_booking", "checkin", "checkout"),
    ),
    ModuleUserSpec(
        "housekeeping",
        "QA Housekeeping",
        "housekeeping",
        "housekeeping",
        ("view_hk_board", "update_room_status", "assign_task"),
    ),
    ModuleUserSpec(
        "cashier",
        "QA Cashier",
        "staff",
        "cashier",
        ("view_folio", "post_charge", "post_payment", "close_folio"),
    ),
    ModuleUserSpec(
        "finance",
        "QA Finance",
        "finance",
        "finance",
        ("view_folio", "view_financial_reports", "export_data"),
    ),
    ModuleUserSpec(
        "invoice",
        "QA E-Invoice",
        "staff",
        "invoice",
        ("view_folio",),
    ),
    ModuleUserSpec("pos", "QA POS", "staff", "pos"),
    ModuleUserSpec("stock", "QA Stock", "staff", "stock"),
    ModuleUserSpec(
        "procurement",
        "QA Procurement",
        "procurement",
        "procurement",
        ("view_procurement", "manage_procurement"),
    ),
    ModuleUserSpec(
        "hr",
        "QA Human Resources",
        "staff",
        "hr",
        ("view_hr", "manage_hr"),
    ),
    ModuleUserSpec(
        "reports",
        "QA Reports",
        "staff",
        "reports",
        ("view_reports", "export_data"),
    ),
    ModuleUserSpec("channel", "QA Channel Manager", "staff", "channel_manager"),
    ModuleUserSpec(
        "sales",
        "QA Sales",
        "sales",
        "sales",
        ("view_companies", "create_company", "edit_company"),
    ),
    ModuleUserSpec("tasks", "QA Tasks", "staff", "tasks"),
    ModuleUserSpec("maintenance", "QA Maintenance", "staff", "maintenance"),
)


class PrePilotSafetyError(RuntimeError):
    """Stable fail-closed error code for operator-facing CLI failures."""


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _is_truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() == "true"


def _non_empty(value: str | None) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _normalize_ids(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(sorted({value.strip() for value in values if _non_empty(value)}))


def _or_filter(fields: Sequence[str], values: Sequence[str]) -> dict[str, Any]:
    normalized_values = _normalize_ids(values)
    if not normalized_values:
        raise PrePilotSafetyError("BLOCKED_EMPTY_SCOPE")
    clauses = [{field: {"$in": list(normalized_values)}} for field in fields]
    if not clauses:
        raise PrePilotSafetyError("BLOCKED_EMPTY_SCOPE_FIELDS")
    return clauses[0] if len(clauses) == 1 else {"$or": clauses}


def build_tenant_filter(spec: CollectionSpec, tenant_ids: Sequence[str]) -> dict[str, Any]:
    """Build a non-empty, tenant-scoped filter for one allowlisted collection."""
    if spec.name in PRESERVED_COLLECTION_NAMES:
        raise PrePilotSafetyError("BLOCKED_PRESERVED_COLLECTION")
    if spec not in RESET_COLLECTIONS and spec not in OPTIONAL_OPERATIONAL_AUDIT_COLLECTIONS:
        raise PrePilotSafetyError("BLOCKED_COLLECTION_NOT_ALLOWLISTED")
    return _or_filter(spec.tenant_fields, tenant_ids)


def build_user_linked_filter(
    spec: UserLinkedCollectionSpec,
    user_ids: Sequence[str],
) -> dict[str, Any]:
    if spec not in USER_LINKED_COLLECTIONS:
        raise PrePilotSafetyError("BLOCKED_USER_COLLECTION_NOT_ALLOWLISTED")
    return _or_filter(spec.user_fields, user_ids)


def build_user_delete_filter(
    tenant_ids: Sequence[str],
    *,
    all_non_super_admin_users: bool,
) -> dict[str, Any]:
    """Return a user filter that can never match a super-admin document."""
    protected_role = {"role": {"$ne": SUPER_ADMIN_ROLE}}
    if all_non_super_admin_users:
        return protected_role
    ids = _normalize_ids(tenant_ids)
    if not ids:
        raise PrePilotSafetyError("BLOCKED_EMPTY_USER_TENANT_SCOPE")
    return {"$and": [protected_role, {"tenant_id": {"$in": list(ids)}}]}


def validate_reset_execution_args(args: argparse.Namespace) -> None:
    """Validate destructive reset gates without touching the database."""
    if not args.execute:
        return
    if not _is_truthy_env(RESET_ENV_GATE):
        raise PrePilotSafetyError("BLOCKED_PRE_PILOT_RESET_ENV_GATE")
    if args.confirmation != RESET_CONFIRMATION:
        raise PrePilotSafetyError("BLOCKED_PRE_PILOT_RESET_CONFIRMATION")
    if not _non_empty(args.expected_database_name):
        raise PrePilotSafetyError("BLOCKED_EXPECTED_DATABASE_NAME_MISSING")
    if not _non_empty(args.expected_super_admin_email):
        raise PrePilotSafetyError("BLOCKED_EXPECTED_SUPER_ADMIN_MISSING")
    if not _non_empty(args.backup_reference):
        raise PrePilotSafetyError("BLOCKED_BACKUP_REFERENCE_MISSING")
    digest = str(args.approved_plan_digest or "").strip().lower()
    if _PLAN_DIGEST_PATTERN.fullmatch(digest) is None:
        raise PrePilotSafetyError("BLOCKED_APPROVED_PLAN_DIGEST_MISSING_OR_INVALID")


def validate_seed_execution_args(args: argparse.Namespace) -> None:
    """Validate module-user seed gates without touching the database."""
    if not args.execute:
        return
    if not _is_truthy_env(SEED_ENV_GATE):
        raise PrePilotSafetyError("BLOCKED_MODULE_SEED_ENV_GATE")
    if args.confirmation != SEED_CONFIRMATION:
        raise PrePilotSafetyError("BLOCKED_MODULE_SEED_CONFIRMATION")
    if not _non_empty(args.expected_database_name):
        raise PrePilotSafetyError("BLOCKED_EXPECTED_DATABASE_NAME_MISSING")
    if not _non_empty(args.credentials_output):
        raise PrePilotSafetyError("BLOCKED_CREDENTIALS_OUTPUT_MISSING")


def _validate_email_domain(value: str) -> str:
    normalized = value.strip().lower()
    if _EMAIL_DOMAIN_PATTERN.fullmatch(normalized) is None:
        raise PrePilotSafetyError("BLOCKED_MODULE_SEED_EMAIL_DOMAIN_INVALID")
    return normalized


def _module_user_identity(
    tenant_id: str,
    spec: ModuleUserSpec,
    email_domain: str,
) -> tuple[str, str]:
    tenant_tag = hashlib.sha256(tenant_id.encode("utf-8")).hexdigest()[:10]
    username = f"qa_{spec.slug}"
    domain = _validate_email_domain(email_domain)
    email = f"qa-{spec.slug}-{tenant_tag}@{domain}"
    return username, email


def build_module_user_document(
    *,
    tenant_id: str,
    spec: ModuleUserSpec,
    email_domain: str,
    password_hash: str,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build one deterministic module-user document with one explicit scope."""
    if not _non_empty(tenant_id):
        raise PrePilotSafetyError("BLOCKED_MODULE_SEED_TENANT_MISSING")
    if not _non_empty(password_hash):
        raise PrePilotSafetyError("BLOCKED_MODULE_SEED_PASSWORD_HASH_MISSING")
    username, email = _module_user_identity(tenant_id, spec, email_domain)
    permissions = sorted({f"module:{spec.module_scope}", *spec.operation_permissions})
    timestamp = now or _utc_now()
    return {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "email": email,
        "username": username,
        "name": spec.display_name,
        "role": spec.role,
        "password": password_hash,
        "module_scopes": [spec.module_scope],
        "granted_permissions": permissions,
        "is_active": True,
        "email_verified": True,
        "email_verified_at": timestamp,
        "must_change_password": True,
        "is_internal_test_user": True,
        "created_at": timestamp,
    }


def _password_hasher():
    """Resolve the application's password hasher with a compatible fallback."""
    try:
        from core import security as security_module

        for name in ("get_password_hash", "hash_password"):
            candidate = getattr(security_module, name, None)
            if callable(candidate):
                return candidate
    except ImportError:
        pass

    from passlib.context import CryptContext

    context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    return context.hash


def _load_db():
    from core.database import _raw_db

    return _raw_db


async def _cursor_to_list(
    cursor: Any,
    *,
    limit: int = 10_000,
) -> list[dict[str, Any]]:
    if hasattr(cursor, "to_list"):
        return await cursor.to_list(length=limit)
    result: list[dict[str, Any]] = []
    async for item in cursor:
        result.append(item)
        if len(result) >= limit:
            break
    return result


async def _active_super_admins(db: Any) -> list[dict[str, Any]]:
    cursor = db.users.find(
        {"role": SUPER_ADMIN_ROLE, "is_active": {"$ne": False}},
        {"_id": 0, "id": 1, "email": 1, "tenant_id": 1},
    )
    return await _cursor_to_list(cursor, limit=100)


async def _selected_tenant_ids(
    db: Any,
    args: argparse.Namespace,
    super_admins: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    explicit = _normalize_ids(args.tenant_id or [])
    protected_tenants = {
        str(admin.get("tenant_id")).strip()
        for admin in super_admins
        if _non_empty(str(admin.get("tenant_id") or ""))
    }

    if args.all_non_super_admin_tenants:
        tenants = await _cursor_to_list(
            db.tenants.find({}, {"_id": 0, "id": 1}),
            limit=100_000,
        )
        selected = {
            str(item.get("id")).strip()
            for item in tenants
            if _non_empty(str(item.get("id") or ""))
        }
        selected.difference_update(protected_tenants)
        selected.update(explicit)
    else:
        selected = set(explicit)

    if selected.intersection(protected_tenants):
        raise PrePilotSafetyError("BLOCKED_SUPER_ADMIN_TENANT_SELECTED")
    if not selected and not args.all_non_super_admin_users:
        raise PrePilotSafetyError("BLOCKED_NO_RESET_SCOPE_SELECTED")
    return tuple(sorted(selected))


def _collection_specs(args: argparse.Namespace) -> tuple[CollectionSpec, ...]:
    if args.include_operational_audit:
        return (*RESET_COLLECTIONS, *OPTIONAL_OPERATIONAL_AUDIT_COLLECTIONS)
    return RESET_COLLECTIONS


def _canonical_plan_payload(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Select stable plan fields used for operator approval."""
    return {
        "database": plan.get("database"),
        "protected_super_admin_ids": plan.get("protected_super_admin_ids", []),
        "selected_tenant_ids": plan.get("selected_tenant_ids", []),
        "selected_user_ids": plan.get("selected_user_ids", []),
        "users": plan.get("users"),
        "tenants": plan.get("tenants"),
        "collections": plan.get("collections", []),
        "user_linked_collections": plan.get("user_linked_collections", []),
    }


def compute_plan_digest(plan: Mapping[str, Any]) -> str:
    canonical = json.dumps(
        _canonical_plan_payload(plan),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


async def build_reset_plan(db: Any, args: argparse.Namespace) -> dict[str, Any]:
    super_admins = await _active_super_admins(db)
    if not super_admins:
        raise PrePilotSafetyError("BLOCKED_NO_ACTIVE_SUPER_ADMIN")

    expected_email = (args.expected_super_admin_email or "").strip().lower()
    if args.execute and expected_email not in {
        str(admin.get("email") or "").strip().lower() for admin in super_admins
    }:
        raise PrePilotSafetyError("BLOCKED_EXPECTED_SUPER_ADMIN_NOT_FOUND")

    tenant_ids = await _selected_tenant_ids(db, args, super_admins)
    user_filter = build_user_delete_filter(
        tenant_ids,
        all_non_super_admin_users=args.all_non_super_admin_users,
    )
    user_documents = await _cursor_to_list(
        db.users.find(user_filter, {"_id": 0, "id": 1}),
        limit=100_000,
    )
    user_ids = _normalize_ids(
        str(item.get("id") or "")
        for item in user_documents
        if item.get("id")
    )

    collection_rows: list[dict[str, Any]] = []
    for spec in _collection_specs(args):
        if tenant_ids:
            query: dict[str, Any] | None = build_tenant_filter(spec, tenant_ids)
            count = await db[spec.name].count_documents(query)
        else:
            query = None
            count = 0
        collection_rows.append(
            {
                "collection": spec.name,
                "category": spec.category,
                "count": int(count),
                "filter": query,
            }
        )

    user_linked_rows: list[dict[str, Any]] = []
    for spec in USER_LINKED_COLLECTIONS:
        if user_ids:
            query = build_user_linked_filter(spec, user_ids)
            count = await db[spec.name].count_documents(query)
        else:
            query = None
            count = 0
        user_linked_rows.append(
            {
                "collection": spec.name,
                "category": "user_linked",
                "count": int(count),
                "filter": query,
            }
        )

    user_count = await db.users.count_documents(user_filter)
    tenant_count = (
        await db.tenants.count_documents({"id": {"$in": list(tenant_ids)}})
        if tenant_ids
        else 0
    )

    plan: dict[str, Any] = {
        "operation": "pre_pilot_reset",
        "mode": "execute" if args.execute else "dry_run",
        "database": getattr(db, "name", None),
        "generated_at": _utc_now().isoformat(),
        "active_super_admin_count": len(super_admins),
        "protected_super_admin_ids": sorted(
            str(admin.get("id")) for admin in super_admins if admin.get("id")
        ),
        "selected_tenant_ids": list(tenant_ids),
        "selected_user_ids": list(user_ids),
        "users": {"count": int(user_count), "filter": user_filter},
        "tenants": {
            "count": int(tenant_count),
            "filter": {"id": {"$in": list(tenant_ids)}} if tenant_ids else None,
        },
        "collections": collection_rows,
        "user_linked_collections": user_linked_rows,
        "preserved_collection_names": sorted(PRESERVED_COLLECTION_NAMES),
        "backup_reference": args.backup_reference if args.execute else None,
    }
    plan["plan_digest"] = compute_plan_digest(plan)
    return plan


def _assert_database_name(db: Any, expected: str | None) -> None:
    actual = str(getattr(db, "name", "") or "")
    if actual != str(expected or ""):
        raise PrePilotSafetyError("BLOCKED_DATABASE_NAME_MISMATCH")


def _assert_plan_digest(args: argparse.Namespace, plan: Mapping[str, Any]) -> None:
    approved = str(args.approved_plan_digest or "").strip().lower()
    actual = str(plan.get("plan_digest") or "").strip().lower()
    if not secrets.compare_digest(approved, actual):
        raise PrePilotSafetyError("BLOCKED_PLAN_DIGEST_MISMATCH")


async def execute_reset(
    db: Any,
    args: argparse.Namespace,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    """Execute an already-reviewed plan; never called in default dry-run mode."""
    validate_reset_execution_args(args)
    _assert_database_name(db, args.expected_database_name)
    _assert_plan_digest(args, plan)

    before_admins = await _active_super_admins(db)
    before_admin_ids = {str(item.get("id")) for item in before_admins}
    if not before_admin_ids:
        raise PrePilotSafetyError("BLOCKED_NO_ACTIVE_SUPER_ADMIN")

    deleted: dict[str, int] = {}
    tenant_allowlist = {spec.name for spec in _collection_specs(args)}
    user_allowlist = {spec.name for spec in USER_LINKED_COLLECTIONS}

    for row in plan["user_linked_collections"]:
        query = row.get("filter")
        if not query:
            continue
        name = str(row["collection"])
        if name not in user_allowlist or name in PRESERVED_COLLECTION_NAMES:
            raise PrePilotSafetyError("BLOCKED_USER_COLLECTION_NOT_ALLOWLISTED")
        result = await db[name].delete_many(query)
        deleted[name] = int(result.deleted_count)

    for row in plan["collections"]:
        query = row.get("filter")
        if not query:
            continue
        name = str(row["collection"])
        if name not in tenant_allowlist or name in PRESERVED_COLLECTION_NAMES:
            raise PrePilotSafetyError("BLOCKED_COLLECTION_NOT_ALLOWLISTED")
        result = await db[name].delete_many(query)
        deleted[name] = int(result.deleted_count)

    user_result = await db.users.delete_many(plan["users"]["filter"])
    deleted["users"] = int(user_result.deleted_count)

    tenant_filter = plan["tenants"].get("filter")
    if tenant_filter:
        tenant_result = await db.tenants.delete_many(tenant_filter)
        deleted["tenants"] = int(tenant_result.deleted_count)
    else:
        deleted["tenants"] = 0

    after_admins = await _active_super_admins(db)
    after_admin_ids = {str(item.get("id")) for item in after_admins}
    if before_admin_ids != after_admin_ids:
        raise PrePilotSafetyError("CRITICAL_SUPER_ADMIN_POSTCONDITION_FAILED")

    remaining_users = await db.users.count_documents(plan["users"]["filter"])
    remaining_tenants = (
        await db.tenants.count_documents(tenant_filter) if tenant_filter else 0
    )
    if remaining_users or remaining_tenants:
        raise PrePilotSafetyError("CRITICAL_RESET_POSTCONDITION_FAILED")

    return {
        "operation": "pre_pilot_reset",
        "mode": "executed",
        "database": getattr(db, "name", None),
        "completed_at": _utc_now().isoformat(),
        "approved_plan_digest": plan["plan_digest"],
        "backup_reference": args.backup_reference,
        "deleted": deleted,
        "protected_super_admin_count": len(after_admins),
    }


async def build_seed_plan(db: Any, args: argparse.Namespace) -> dict[str, Any]:
    email_domain = _validate_email_domain(args.email_domain)
    tenant = await db.tenants.find_one(
        {"id": args.tenant_id},
        {"_id": 0, "id": 1},
    )
    if not tenant:
        raise PrePilotSafetyError("BLOCKED_MODULE_SEED_TENANT_NOT_FOUND")

    rows: list[dict[str, Any]] = []
    for spec in MODULE_USER_SPECS:
        username, email = _module_user_identity(args.tenant_id, spec, email_domain)
        collision = await db.users.find_one(
            {
                "$or": [
                    {"tenant_id": args.tenant_id, "username": username},
                    {"email": email},
                ]
            },
            {"_id": 0, "id": 1, "is_internal_test_user": 1},
        )
        state = "missing"
        if collision:
            state = (
                "existing_module_user"
                if collision.get("is_internal_test_user") is True
                else "collision"
            )
        rows.append(
            {
                "slug": spec.slug,
                "username": username,
                "email": email,
                "role": spec.role,
                "module_scopes": [spec.module_scope],
                "state": state,
            }
        )

    if any(row["state"] == "collision" for row in rows):
        raise PrePilotSafetyError("BLOCKED_MODULE_SEED_IDENTITY_COLLISION")

    return {
        "operation": "seed_module_users",
        "mode": "execute" if args.execute else "dry_run",
        "database": getattr(db, "name", None),
        "tenant_id": args.tenant_id,
        "generated_at": _utc_now().isoformat(),
        "accounts": rows,
    }


def _secure_write_json(path: Path, payload: Any, *, overwrite: bool) -> None:
    flags = os.O_WRONLY | os.O_CREAT
    flags |= os.O_TRUNC if overwrite else os.O_EXCL
    fd = os.open(path, flags, stat.S_IRUSR | stat.S_IWUSR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
    except Exception:
        try:
            path.unlink(missing_ok=True)
        finally:
            raise


async def execute_seed(
    db: Any,
    args: argparse.Namespace,
    plan: Mapping[str, Any],
) -> dict[str, Any]:
    validate_seed_execution_args(args)
    _assert_database_name(db, args.expected_database_name)

    output_path = Path(args.credentials_output).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists() and not args.overwrite_credentials_output:
        raise PrePilotSafetyError("BLOCKED_CREDENTIALS_OUTPUT_EXISTS")

    hasher = _password_hasher()
    credentials: list[dict[str, str]] = []
    inserted: list[str] = []
    skipped: list[str] = []
    spec_by_slug = {spec.slug: spec for spec in MODULE_USER_SPECS}

    for row in plan["accounts"]:
        slug = str(row["slug"])
        if row["state"] == "existing_module_user":
            skipped.append(slug)
            continue
        spec = spec_by_slug[slug]
        temporary_password = secrets.token_urlsafe(24)
        document = build_module_user_document(
            tenant_id=args.tenant_id,
            spec=spec,
            email_domain=args.email_domain,
            password_hash=hasher(temporary_password),
        )
        result = await db.users.update_one(
            {
                "tenant_id": args.tenant_id,
                "username": document["username"],
                "is_internal_test_user": True,
            },
            {"$setOnInsert": document},
            upsert=True,
        )
        if result.upserted_id is None:
            skipped.append(slug)
            continue
        inserted.append(slug)
        credentials.append(
            {
                "module": spec.module_scope,
                "username": document["username"],
                "email": document["email"],
                "temporary_password": temporary_password,
            }
        )

    _secure_write_json(
        output_path,
        {
            "tenant_id": args.tenant_id,
            "generated_at": _utc_now().isoformat(),
            "accounts": credentials,
        },
        overwrite=args.overwrite_credentials_output,
    )

    return {
        "operation": "seed_module_users",
        "mode": "executed",
        "database": getattr(db, "name", None),
        "tenant_id": args.tenant_id,
        "inserted": sorted(inserted),
        "skipped_existing": sorted(set(skipped)),
        "credentials_file": str(output_path),
        "credentials_file_mode": "0600",
    }


def _write_report(path: str | None, payload: Any) -> None:
    if not _non_empty(path):
        return
    target = Path(str(path)).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )


def _base_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Syroce fail-closed pre-pilot reset utility"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    reset = subparsers.add_parser(
        "reset",
        help="Plan or execute the pre-pilot data reset",
    )
    reset.add_argument("--tenant-id", action="append", default=[])
    reset.add_argument("--all-non-super-admin-tenants", action="store_true")
    reset.add_argument("--all-non-super-admin-users", action="store_true")
    reset.add_argument("--include-operational-audit", action="store_true")
    reset.add_argument(
        "--execute",
        action="store_true",
        help="Opt into mutation; default is dry-run",
    )
    reset.add_argument("--confirmation")
    reset.add_argument("--expected-database-name")
    reset.add_argument("--expected-super-admin-email")
    reset.add_argument("--backup-reference")
    reset.add_argument("--approved-plan-digest")
    reset.add_argument("--report-path")

    seed = subparsers.add_parser(
        "seed-module-users",
        help="Plan or seed one QA user per module",
    )
    seed.add_argument("--tenant-id", required=True)
    seed.add_argument("--email-domain", default="qa.syroce.app")
    seed.add_argument(
        "--execute",
        action="store_true",
        help="Opt into mutation; default is dry-run",
    )
    seed.add_argument("--confirmation")
    seed.add_argument("--expected-database-name")
    seed.add_argument("--credentials-output")
    seed.add_argument("--overwrite-credentials-output", action="store_true")
    seed.add_argument("--report-path")
    return parser


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    db = _load_db()
    if args.command == "reset":
        validate_reset_execution_args(args)
        plan = await build_reset_plan(db, args)
        if not args.execute:
            return plan
        return await execute_reset(db, args, plan)

    if args.command == "seed-module-users":
        validate_seed_execution_args(args)
        plan = await build_seed_plan(db, args)
        if not args.execute:
            return plan
        return await execute_seed(db, args, plan)

    raise PrePilotSafetyError("BLOCKED_UNKNOWN_COMMAND")


def main(argv: Sequence[str] | None = None) -> int:
    args = _base_parser().parse_args(argv)
    try:
        result = asyncio.run(_run(args))
    except PrePilotSafetyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        # Do not leak provider responses, credentials, or document contents.
        print(
            f"PRE_PILOT_RESET_UNEXPECTED_ERROR:{type(exc).__name__}",
            file=sys.stderr,
        )
        return 1

    _write_report(getattr(args, "report_path", None), result)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

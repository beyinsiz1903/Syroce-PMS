"""
TI-003: Tenant Isolation Full Enforcement
==========================================
3-layer tenant isolation:
  Layer 1 — DB Proxy: auto-inject tenant_id into all queries (TenantAwareDBProxy)
  Layer 2 — Runtime Guard: exception on unscoped access (STRICT_TENANT_MODE)
  Layer 3 — Static Audit: CI check for raw db usage

Usage in routes (automatic via middleware):
    # The global `db` object from core.database IS the proxy.
    # If middleware has set tenant context, all queries are scoped.
    from core.database import db
    result = await db.bookings.find_one({"status": "confirmed"})
    # tenant_id is auto-injected ✅

Usage with explicit get_db():
    from core.tenant_db import get_db
    db = get_db()  # raises if no tenant context
    rooms = await db.rooms.find({}).to_list(100)

Usage in workers:
    from core.tenant_db import get_db_for_tenant
    db = get_db_for_tenant(event["tenant_id"])
    await db.bookings.update_one(...)

Usage in system operations (startup, health):
    from core.tenant_db import get_system_db
    raw = get_system_db()
    await raw.rooms.create_index(...)
"""
import logging
import os
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

logger = logging.getLogger("core.tenant_db")

# ── Tenant Context (per-request, per-task) ──────────────────────
_tenant_ctx: ContextVar[str | None] = ContextVar("tenant_id", default=None)

# ── Configuration ───────────────────────────────────────────────
STRICT_TENANT_MODE = os.environ.get("STRICT_TENANT_MODE", "false").lower() == "true"

# ── Collections where tenant_id filter is MANDATORY ─────────────
TENANT_SCOPED_COLLECTIONS: set[str] = {
    "rooms", "bookings", "guests", "folios", "tasks", "users",
    "audit_logs", "reports", "rate_plans", "invoices", "payments",
    "housekeeping_tasks", "maintenance_orders", "inventory_items",
    "suppliers", "expenses", "bank_accounts", "staff",
    "gdpr_consents", "ip_rules", "user_2fa", "notifications",
    "pos_orders", "restaurant_tables", "menu_items",
    "spa_services", "spa_bookings", "meeting_rooms", "events",
    "group_bookings", "crm_contacts", "crm_activities",
    "loyalty_members", "loyalty_transactions",
    "channel_mappings", "ota_connections",
    "data_processing_agreements", "retention_policies",
    "tenant_security_policies", "extra_charges",
    "folio_charges", "pms_audit_trail", "outbox_events",
    "pipeline_runs", "exely_auto_import_runs",
    "rate_plans", "cancellation_policies",
    "guest_journey_checkins", "guest_journey_feedback",
    "night_audit_logs", "night_audit_records",
    "night_audit_runs", "night_audit_run_items",
    "tenant_access_logs", "tenant_isolation_policies",
    "imported_reservations", "lineage",
    "rate_periods", "rate_overrides", "packages",
    "channel_connections", "channel_sync_logs", "rate_updates",
    "charges",
    "room_blocks", "room_block_logs",
    "hotel_services", "hotel_service_requests",
    "departments", "department_tasks",
    "budget_configs", "budget_actuals",
    "survey_responses", "external_reviews",
    "companies", "contracts",
}

# ── Collections that are global (no tenant_id) ──────────────────
GLOBAL_COLLECTIONS: set[str] = {
    "tenants", "hotel_chains", "system_config", "system_logs",
    "subscription_plans", "marketplace_extensions",
}


class TenantViolationError(Exception):
    """Raised when a cross-tenant access attempt is detected."""


# ── Context Management ──────────────────────────────────────────

def set_tenant_context(tenant_id: str) -> None:
    """Set the current tenant context for this async task."""
    _tenant_ctx.set(tenant_id)


def clear_tenant_context() -> None:
    """Clear the current tenant context."""
    _tenant_ctx.set(None)


def get_current_tenant_id() -> str | None:
    """Get the current tenant_id from context, or None."""
    return _tenant_ctx.get()


@contextmanager
def tenant_context(tenant_id: str):
    """Context manager for explicit tenant scoping (useful in workers)."""
    token = _tenant_ctx.set(tenant_id)
    try:
        yield
    finally:
        _tenant_ctx.reset(token)


# ── TenantScopedCollection ─────────────────────────────────────

class TenantScopedCollection:
    """
    Wraps a Motor collection to auto-inject and validate tenant_id
    on every operation. Cross-tenant access is blocked.
    """

    __slots__ = ("_coll", "_tenant_id", "_name")

    def __init__(self, collection, tenant_id: str, collection_name: str):
        self._coll = collection
        self._tenant_id = tenant_id
        self._name = collection_name

    def _inject_filter(self, filter_dict: dict[str, Any] | None = None) -> dict[str, Any]:
        if filter_dict is None:
            filter_dict = {}
        existing = filter_dict.get("tenant_id")
        if existing is None:
            filter_dict["tenant_id"] = self._tenant_id
        elif existing != self._tenant_id:
            logger.critical(
                "TENANT VIOLATION: collection=%s expected=%s got=%s",
                self._name, self._tenant_id, existing,
            )
            raise TenantViolationError(
                f"Cross-tenant access blocked on {self._name}: "
                f"expected {self._tenant_id}, got {existing}"
            )
        return filter_dict

    def _inject_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        if "tenant_id" in doc and doc["tenant_id"] != self._tenant_id:
            logger.critical(
                "TENANT WRITE VIOLATION: collection=%s expected=%s got=%s",
                self._name, self._tenant_id, doc["tenant_id"],
            )
            raise TenantViolationError(
                f"Cannot insert document for tenant {doc['tenant_id']} "
                f"into context {self._tenant_id}"
            )
        doc["tenant_id"] = self._tenant_id
        return doc

    # ── Read operations ──

    async def find_one(self, filter=None, *args, **kwargs):
        return await self._coll.find_one(self._inject_filter(filter), *args, **kwargs)

    def find(self, filter=None, *args, **kwargs):
        return self._coll.find(self._inject_filter(filter), *args, **kwargs)

    async def count_documents(self, filter=None, *args, **kwargs):
        if filter is None:
            filter = {}
        return await self._coll.count_documents(self._inject_filter(filter), *args, **kwargs)

    async def distinct(self, key, filter=None, *args, **kwargs):
        return await self._coll.distinct(key, self._inject_filter(filter), *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        if pipeline and isinstance(pipeline[0], dict) and "$match" in pipeline[0]:
            pipeline[0]["$match"] = self._inject_filter(pipeline[0]["$match"])
        else:
            pipeline.insert(0, {"$match": {"tenant_id": self._tenant_id}})
        return self._coll.aggregate(pipeline, *args, **kwargs)

    # ── Write operations ──

    async def insert_one(self, document, *args, **kwargs):
        return await self._coll.insert_one(self._inject_doc(document), *args, **kwargs)

    async def insert_many(self, documents, *args, **kwargs):
        return await self._coll.insert_many(
            [self._inject_doc(d) for d in documents], *args, **kwargs
        )

    async def update_one(self, filter, update, *args, **kwargs):
        return await self._coll.update_one(self._inject_filter(filter), update, *args, **kwargs)

    async def update_many(self, filter, update, *args, **kwargs):
        return await self._coll.update_many(self._inject_filter(filter), update, *args, **kwargs)

    async def delete_one(self, filter, *args, **kwargs):
        return await self._coll.delete_one(self._inject_filter(filter), *args, **kwargs)

    async def delete_many(self, filter, *args, **kwargs):
        return await self._coll.delete_many(self._inject_filter(filter), *args, **kwargs)

    async def find_one_and_update(self, filter, update, *args, **kwargs):
        return await self._coll.find_one_and_update(
            self._inject_filter(filter), update, *args, **kwargs
        )

    async def find_one_and_delete(self, filter, *args, **kwargs):
        return await self._coll.find_one_and_delete(
            self._inject_filter(filter), *args, **kwargs
        )

    async def find_one_and_replace(self, filter, replacement, *args, **kwargs):
        return await self._coll.find_one_and_replace(
            self._inject_filter(filter), replacement, *args, **kwargs
        )

    # ── Bulk operations (pass-through, caller must handle tenant_id) ──

    async def bulk_write(self, requests, *args, **kwargs):
        return await self._coll.bulk_write(requests, *args, **kwargs)

    # ── Index operations (pass-through — schema ops, not data ops) ──

    async def create_index(self, *args, **kwargs):
        return await self._coll.create_index(*args, **kwargs)

    async def create_indexes(self, *args, **kwargs):
        return await self._coll.create_indexes(*args, **kwargs)

    async def list_indexes(self, *args, **kwargs):
        return await self._coll.list_indexes(*args, **kwargs)

    async def drop_index(self, *args, **kwargs):
        return await self._coll.drop_index(*args, **kwargs)

    # ── Property pass-through ──

    @property
    def name(self):
        return self._coll.name

    @property
    def full_name(self):
        return self._coll.full_name

    def __getattr__(self, name):
        return getattr(self._coll, name)


# ── TenantScopedDB (explicit) ──────────────────────────────────

class TenantScopedDB:
    """
    Explicit tenant-scoped DB. Always requires a tenant_id.
    Use via get_db() or get_db_for_tenant().
    """

    def __init__(self, database, tenant_id: str):
        object.__setattr__(self, "_db", database)
        object.__setattr__(self, "_tenant_id", tenant_id)

    @property
    def tenant_id(self) -> str:
        return object.__getattribute__(self, "_tenant_id")

    @property
    def client(self):
        return object.__getattribute__(self, "_db").client

    @property
    def name(self):
        return object.__getattribute__(self, "_db").name

    def __getattr__(self, name: str):
        raw_db = object.__getattribute__(self, "_db")
        tenant_id = object.__getattribute__(self, "_tenant_id")
        coll = raw_db[name]
        if name in GLOBAL_COLLECTIONS:
            return coll
        return TenantScopedCollection(coll, tenant_id, name)

    def __getitem__(self, name: str):
        return self.__getattr__(name)


class SchemaOnlyCollection:
    """
    Guarded wrapper that allows only schema operations (indexes) but
    blocks data operations. Used in STRICT_TENANT_MODE when a
    tenant-scoped collection is accessed without tenant context.
    """

    __slots__ = ("_coll", "_name")

    _SCHEMA_OPS = frozenset({
        "create_index", "create_indexes", "list_indexes", "drop_index",
        "index_information", "name", "full_name",
    })

    def __init__(self, collection, name: str):
        self._coll = collection
        self._name = name

    def __getattr__(self, attr: str):
        if attr in SchemaOnlyCollection._SCHEMA_OPS:
            return getattr(self._coll, attr)
        raise TenantViolationError(
            f"Data operation '{attr}' on tenant-scoped collection '{self._name}' "
            f"without tenant context is forbidden (STRICT_TENANT_MODE=true). "
            f"Use get_system_db() for system ops or set tenant context."
        )


# ── TenantAwareDBProxy (transparent) ───────────────────────────

class TenantAwareDBProxy:
    """
    Transparent proxy that replaces the raw `db` object in core.database.
    Reads tenant_id from contextvars (set by middleware).

    - If tenant context exists → returns TenantScopedCollection
    - If no context + STRICT_MODE → returns SchemaOnlyCollection
      (allows index creation, blocks data operations)
    - If no context + soft mode → returns raw collection with warning
    """

    _DB_PASSTHROUGH = frozenset({
        "command", "list_collection_names", "list_collections",
        "create_collection", "drop_collection",
        "with_options", "get_collection",
        "codec_options", "read_preference", "read_concern", "write_concern",
        "dereference",
    })

    def __init__(self, database):
        object.__setattr__(self, "_db", database)

    @property
    def client(self):
        return object.__getattribute__(self, "_db").client

    @property
    def name(self):
        return object.__getattribute__(self, "_db").name

    def __getattr__(self, name: str):
        raw_db = object.__getattribute__(self, "_db")

        # Pass through database-level methods/properties
        if name in TenantAwareDBProxy._DB_PASSTHROUGH:
            return getattr(raw_db, name)

        raw_coll = raw_db[name]

        # Global collections → no scoping needed
        if name in GLOBAL_COLLECTIONS:
            return raw_coll

        # Check tenant context
        tenant_id = _tenant_ctx.get()

        if tenant_id:
            return TenantScopedCollection(raw_coll, tenant_id, name)

        # No tenant context
        if name in TENANT_SCOPED_COLLECTIONS:
            if STRICT_TENANT_MODE:
                # Return schema-only wrapper: allows indexes, blocks data ops
                return SchemaOnlyCollection(raw_coll, name)
            # Soft mode: warn but allow (for startup, health, auth)
            return raw_coll

        # Unknown collection without context → treat as raw
        return raw_coll

    def __getitem__(self, name: str):
        return self.__getattr__(name)


# ── Public API ──────────────────────────────────────────────────

def get_db() -> TenantScopedDB:
    """
    Get a tenant-scoped DB from the current request context.
    Raises TenantViolationError if no context is set.
    """
    tenant_id = _tenant_ctx.get()
    if not tenant_id:
        raise TenantViolationError(
            "get_db() called without tenant context. "
            "Use get_db_for_tenant() in workers or get_system_db() for system ops."
        )
    from core.database import _raw_db
    return TenantScopedDB(_raw_db, tenant_id)


def get_db_for_tenant(tenant_id: str) -> TenantScopedDB:
    """
    Get a tenant-scoped DB for a specific tenant.
    Use in workers/background tasks where there's no request context.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required")
    from core.database import _raw_db
    return TenantScopedDB(_raw_db, tenant_id)


def get_system_db():
    """
    Get the raw (unscoped) database for system operations.
    Only use for: startup indexes, health checks, cross-tenant admin queries.
    """
    from core.database import _raw_db
    return _raw_db


# ── Descriptor for repository class-level collection access ────

class LazyCollection:
    """
    Descriptor that resolves a collection through the TenantAwareDBProxy
    at access time (not at import time).

    Usage:
        class GuestRepository:
            collection = LazyCollection("guests")

        # cls.collection now respects tenant context
    """

    __slots__ = ("_name",)

    def __init__(self, name: str):
        self._name = name

    def __get__(self, obj, objtype=None):
        from core.database import db
        return getattr(db, self._name)

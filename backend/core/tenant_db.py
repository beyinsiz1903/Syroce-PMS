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
STRICT_TENANT_MODE = os.environ.get("STRICT_TENANT_MODE", "true").lower() == "true"

# ── Collections where tenant_id filter is MANDATORY ─────────────
TENANT_SCOPED_COLLECTIONS: set[str] = {
    "rooms",
    "bookings",
    "guests",
    "folios",
    "tasks",
    "users",
    "audit_logs",
    "reports",
    "rate_plans",
    "invoices",
    "payments",
    "housekeeping_tasks",
    "maintenance_orders",
    "inventory_items",
    "suppliers",
    "expenses",
    "bank_accounts",
    "staff",
    "gdpr_consents",
    "ip_rules",
    "user_2fa",
    "notifications",
    "pos_orders",
    "restaurant_tables",
    "menu_items",
    "spa_services",
    "spa_bookings",
    "events",
    "group_bookings",
    "crm_contacts",
    "crm_activities",
    "loyalty_members",
    "loyalty_transactions",
    "channel_mappings",
    "ota_connections",
    "data_processing_agreements",
    "retention_policies",
    "tenant_security_policies",
    "extra_charges",
    "folio_charges",
    "pms_audit_trail",
    "outbox_events",
    "pipeline_runs",
    "exely_auto_import_runs",
    "rate_plans",
    "cancellation_policies",
    "guest_journey_checkins",
    "guest_journey_feedback",
    "night_audit_logs",
    "night_audit_records",
    "night_audit_runs",
    "night_audit_run_items",
    "tenant_access_logs",
    "tenant_isolation_policies",
    "imported_reservations",
    "lineage",
    "rate_periods",
    "rate_overrides",
    "packages",
    "channel_connections",
    "channel_sync_logs",
    "rate_updates",
    "charges",
    "room_blocks",
    "room_block_logs",
    "hotel_services",
    "hotel_service_requests",
    "departments",
    "department_tasks",
    "budget_configs",
    "budget_actuals",
    "survey_responses",
    "external_reviews",
    "companies",
    "contracts",
    "pos_late_charges",
    "invoice_sync",
}

# ── Append-only audit collections (Task #568) ───────────────────
# Records in these collections are immutable: app code may INSERT and READ but
# must never update/delete/replace them. The single sanctioned removal from the
# hot collection is the controlled retention MOVE into the immutable archive,
# which runs under audit_retention_context() (or a raw system client in Celery).
APPEND_ONLY_COLLECTIONS: set[str] = {"audit_logs", "audit_logs_archive"}

# The hot collection is the single canonical destination for new audit records.
# Every insert into it (regardless of call site) is auto-attributed (client
# IP / user-agent) and tamper-evidently chained at this DB layer, so the chain
# stays complete even for call sites that bypass append_audit_log().
HOT_AUDIT_COLLECTION: str = "audit_logs"

# ── Collections that are global (no tenant_id) ──────────────────
GLOBAL_COLLECTIONS: set[str] = {
    "tenants",
    "hotel_chains",
    "system_config",
    "system_logs",
    "subscription_plans",
    "marketplace_extensions",
    # CapX integration — cross-tenant admin views (super_admin only)
    "capx_tenant_credentials",
    "capx_counter_offers",
    "capx_events",
}


class TenantViolationError(Exception):
    """Raised when a cross-tenant access attempt is detected."""


class AuditImmutabilityError(Exception):
    """Raised when app code attempts to update/delete an append-only audit record."""


# Set True only inside audit_retention_context() — the controlled retention move.
_audit_retention_ctx: ContextVar[bool] = ContextVar("audit_retention", default=False)


@contextmanager
def audit_retention_context():
    """Permit the immutability-guarded audit collections to be mutated for the
    duration of the controlled retention move (archive copy-then-delete). All
    other code paths through the `db` proxy / get_db() stay append-only."""
    token = _audit_retention_ctx.set(True)
    try:
        yield
    finally:
        _audit_retention_ctx.reset(token)


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

# Collections whose write operations must evict the in-process auth caches
# in core.security (_USER_DOC_CACHE) and core.helpers (_TENANT_DOC_CACHE).
# Without this hook, password / role / module-toggle mutations would not take
# effect until the 30s/60s TTL expired (architect "stale-authz window" finding).
_AUTH_CACHE_USER_COLLECTIONS = frozenset({"users"})
_AUTH_CACHE_TENANT_COLLECTIONS = frozenset({"tenants"})


def _extract_doc_id(filter_dict: Any) -> str | None:
    """Best-effort: pull a plain string `id` out of a Mongo filter so we can
    do a targeted invalidate. Anything operator-shaped or non-string returns
    None → caller falls back to a full cache flush (safe but slightly wasteful).
    """
    if not isinstance(filter_dict, dict):
        return None
    val = filter_dict.get("id")
    if isinstance(val, str) and "$" not in val:
        return val
    return None


def _invalidate_auth_caches_for(collection_name: str, filter_dict: Any) -> None:
    """Evict user / tenant doc caches after a mutation. Imported lazily to
    avoid an import cycle (core.security → core.database → core.tenant_db)."""
    try:
        if collection_name in _AUTH_CACHE_USER_COLLECTIONS:
            from core.security import invalidate_user_doc_cache

            invalidate_user_doc_cache(_extract_doc_id(filter_dict))
        elif collection_name in _AUTH_CACHE_TENANT_COLLECTIONS:
            from core.helpers import invalidate_tenant_doc_cache

            invalidate_tenant_doc_cache(_extract_doc_id(filter_dict))
    except Exception:
        # Never let a cache-eviction error block the mutation result.
        logger.debug("auth cache invalidation failed for %s", collection_name, exc_info=True)


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
                self._name,
                self._tenant_id,
                existing,
            )
            raise TenantViolationError(f"Cross-tenant access blocked on {self._name}: expected {self._tenant_id}, got {existing}")
        return filter_dict

    def _inject_doc(self, doc: dict[str, Any]) -> dict[str, Any]:
        if "tenant_id" in doc and doc["tenant_id"] != self._tenant_id:
            logger.critical(
                "TENANT WRITE VIOLATION: collection=%s expected=%s got=%s",
                self._name,
                self._tenant_id,
                doc["tenant_id"],
            )
            raise TenantViolationError(f"Cannot insert document for tenant {doc['tenant_id']} into context {self._tenant_id}")
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
    # NOTE: every mutation method below ends with _invalidate_auth_caches_for(...)
    # so the in-process user/tenant doc caches in core.security/core.helpers stay
    # consistent with Atlas without each call site having to remember.

    async def insert_one(self, document, *args, **kwargs):
        result = await self._coll.insert_one(self._inject_doc(document), *args, **kwargs)
        _invalidate_auth_caches_for(self._name, document)
        return result

    async def insert_many(self, documents, *args, **kwargs):
        result = await self._coll.insert_many([self._inject_doc(d) for d in documents], *args, **kwargs)
        if self._name in _AUTH_CACHE_USER_COLLECTIONS or self._name in _AUTH_CACHE_TENANT_COLLECTIONS:
            _invalidate_auth_caches_for(self._name, None)  # bulk → flush
        return result

    async def update_one(self, filter, update, *args, **kwargs):
        result = await self._coll.update_one(self._inject_filter(filter), update, *args, **kwargs)
        _invalidate_auth_caches_for(self._name, filter)
        return result

    async def update_many(self, filter, update, *args, **kwargs):
        result = await self._coll.update_many(self._inject_filter(filter), update, *args, **kwargs)
        _invalidate_auth_caches_for(self._name, filter)
        return result

    async def delete_one(self, filter, *args, **kwargs):
        result = await self._coll.delete_one(self._inject_filter(filter), *args, **kwargs)
        _invalidate_auth_caches_for(self._name, filter)
        return result

    async def delete_many(self, filter, *args, **kwargs):
        result = await self._coll.delete_many(self._inject_filter(filter), *args, **kwargs)
        _invalidate_auth_caches_for(self._name, filter)
        return result

    async def find_one_and_update(self, filter, update, *args, **kwargs):
        result = await self._coll.find_one_and_update(self._inject_filter(filter), update, *args, **kwargs)
        _invalidate_auth_caches_for(self._name, filter)
        return result

    async def find_one_and_delete(self, filter, *args, **kwargs):
        result = await self._coll.find_one_and_delete(self._inject_filter(filter), *args, **kwargs)
        _invalidate_auth_caches_for(self._name, filter)
        return result

    async def find_one_and_replace(self, filter, replacement, *args, **kwargs):
        result = await self._coll.find_one_and_replace(self._inject_filter(filter), replacement, *args, **kwargs)
        _invalidate_auth_caches_for(self._name, filter)
        return result

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
            if name in _AUTH_CACHE_TENANT_COLLECTIONS:
                inner = GlobalCachedCollection(coll, name)
            else:
                inner = coll
        else:
            inner = TenantScopedCollection(coll, tenant_id, name)
        # Immutability guard: audit collections are append-only for app code.
        if name in APPEND_ONLY_COLLECTIONS:
            return AppendOnlyCollection(inner, name)
        return inner

    def __getitem__(self, name: str):
        return self.__getattr__(name)


class GlobalCachedCollection:
    """
    Pass-through wrapper for GLOBAL collections (e.g. `tenants`) whose
    write operations must still evict the in-process auth caches.
    Reads go straight to the raw Motor collection (no tenant scoping).
    """

    __slots__ = ("_coll", "_name")

    _MUTATION_OPS = frozenset(
        {
            "insert_one",
            "insert_many",
            "update_one",
            "update_many",
            "delete_one",
            "delete_many",
            "find_one_and_update",
            "find_one_and_delete",
            "find_one_and_replace",
            "replace_one",
        }
    )

    def __init__(self, collection, name: str):
        self._coll = collection
        self._name = name

    def __getattr__(self, attr: str):
        target = getattr(self._coll, attr)
        if attr not in GlobalCachedCollection._MUTATION_OPS:
            return target

        async def _wrapped(*args, **kwargs):
            result = await target(*args, **kwargs)
            # First positional is the filter (or document for insert_one).
            payload = args[0] if args else kwargs.get("filter") or kwargs.get("document")
            if attr == "insert_many":
                _invalidate_auth_caches_for(self._name, None)
            else:
                _invalidate_auth_caches_for(self._name, payload)
            return result

        return _wrapped


class AppendOnlyCollection:
    """
    Immutability + canonical-write guard (Task #568). Wraps an audit collection
    handle and:

    - BLOCKS every update/delete/replace from application code (records are
      immutable). The only sanctioned mutation is the controlled retention move,
      which runs inside audit_retention_context().
    - Makes every insert into the hot audit collection the single canonical write
      path: it auto-stamps the request's client IP / user-agent (when the caller
      omitted them) and tamper-evidently chains the record, so call sites that
      insert directly (bypassing append_audit_log) still produce attributed,
      chained records. This keeps the chain verifier trustworthy — there are no
      silently-unchained post-genesis rows from normal flows.

    Chaining is idempotent: a record already carrying `record_hash` (linked by
    append_audit_log) is passed straight through, never re-chained.
    """

    __slots__ = ("_inner", "_name")

    _BLOCKED_OPS = frozenset(
        {
            "update_one",
            "update_many",
            "delete_one",
            "delete_many",
            "find_one_and_update",
            "find_one_and_delete",
            "find_one_and_replace",
            "replace_one",
            "drop",
            "rename",
        }
    )

    def __init__(self, inner, name: str):
        self._inner = inner
        self._name = name

    def _resolve_tenant_id(self, document) -> str | None:
        """Best-effort tenant_id for chaining: explicit on the doc, otherwise the
        scoped collection's tenant, otherwise the current request context."""
        if isinstance(document, dict):
            tid = document.get("tenant_id")
            if tid:
                return tid
        tid = getattr(self._inner, "_tenant_id", None)
        if tid:
            return tid
        return _tenant_ctx.get()

    async def _prepare_audit_doc(self, document):
        """Attribute + chain a hot-collection audit record before it is written.

        No-op for the archive (records are copied verbatim during the retention
        move and must keep their original chain fields) and while inside
        audit_retention_context()."""
        if self._name != HOT_AUDIT_COLLECTION or _audit_retention_ctx.get() or not isinstance(document, dict):
            return document

        # Attribution: stamp client IP + user-agent when the caller omitted them.
        try:
            from common.request_context import get_client_ip, get_user_agent

            if not document.get("ip_address"):
                ip = get_client_ip()
                if ip:
                    document["ip_address"] = ip
            if not document.get("user_agent"):
                ua = get_user_agent()
                if ua:
                    document["user_agent"] = ua
        except Exception:
            logger.debug("audit attribution fill failed", exc_info=True)

        # Tamper-evident chaining. Idempotent: append_audit_log may already have
        # linked the record (record_hash present) → leave it untouched.
        if "record_hash" not in document:
            tenant_id = self._resolve_tenant_id(document)
            if tenant_id:
                document.setdefault("tenant_id", tenant_id)
                try:
                    from core.audit_chain import _link_chain

                    seq, prev_hash, record_hash = await _link_chain(tenant_id, document)
                    document["seq"] = seq
                    document["prev_hash"] = prev_hash
                    document["record_hash"] = record_hash
                except Exception as exc:
                    # Best-effort (mirrors append_audit_log): never lose the audit
                    # event over a chain hiccup. A genuinely unchained post-genesis
                    # row is surfaced by verify_chain, not hidden.
                    logger.warning(
                        "audit chain link failed at DB layer (writing unchained): %s",
                        exc,
                    )

        return document

    async def insert_one(self, document, *args, **kwargs):
        document = await self._prepare_audit_doc(document)
        return await self._inner.insert_one(document, *args, **kwargs)

    async def insert_many(self, documents, *args, **kwargs):
        documents = [await self._prepare_audit_doc(d) for d in documents]
        return await self._inner.insert_many(documents, *args, **kwargs)

    def __getattr__(self, attr: str):
        if attr in AppendOnlyCollection._BLOCKED_OPS and not _audit_retention_ctx.get():
            logger.critical(
                "AUDIT IMMUTABILITY VIOLATION: blocked '%s' on append-only collection '%s'",
                attr,
                self._name,
            )
            raise AuditImmutabilityError(
                f"Mutation '{attr}' on append-only audit collection '{self._name}' is "
                f"forbidden. Audit records are immutable; only inserts and the controlled "
                f"retention move (audit_retention_context) may alter them."
            )
        return getattr(self._inner, attr)

    @property
    def name(self):
        return self._inner.name


class SchemaOnlyCollection:
    """
    Guarded wrapper that allows only schema operations (indexes) but
    blocks data operations. Used in STRICT_TENANT_MODE when a
    tenant-scoped collection is accessed without tenant context.
    """

    __slots__ = ("_coll", "_name")

    _SCHEMA_OPS = frozenset(
        {
            "create_index",
            "create_indexes",
            "list_indexes",
            "drop_index",
            "index_information",
            "name",
            "full_name",
        }
    )

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

    _DB_PASSTHROUGH = frozenset(
        {
            "command",
            "list_collection_names",
            "list_collections",
            "create_collection",
            "drop_collection",
            "with_options",
            "get_collection",
            "codec_options",
            "read_preference",
            "read_concern",
            "write_concern",
            "dereference",
        }
    )

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

        # Global collections → no scoping, but `tenants` writes must invalidate
        # the in-process tenant doc cache, so wrap it.
        if name in GLOBAL_COLLECTIONS:
            if name in _AUTH_CACHE_TENANT_COLLECTIONS:
                inner = GlobalCachedCollection(raw_coll, name)
            else:
                inner = raw_coll
        else:
            # Check tenant context
            tenant_id = _tenant_ctx.get()
            if tenant_id:
                inner = TenantScopedCollection(raw_coll, tenant_id, name)
            elif name in TENANT_SCOPED_COLLECTIONS:
                if STRICT_TENANT_MODE:
                    # Schema-only wrapper: allows indexes, blocks data ops
                    inner = SchemaOnlyCollection(raw_coll, name)
                else:
                    # Soft mode: warn but allow (for startup, health, auth)
                    inner = raw_coll
            else:
                # Unknown collection without context → treat as raw
                inner = raw_coll

        # Immutability guard: audit collections are append-only for app code.
        if name in APPEND_ONLY_COLLECTIONS:
            return AppendOnlyCollection(inner, name)
        return inner

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
        raise TenantViolationError("get_db() called without tenant context. Use get_db_for_tenant() in workers or get_system_db() for system ops.")
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


class _SystemAuditGuardDB:
    """Thin view over the raw system db that keeps the audit collections
    append-only + canonical (auto-attributed, chained) even on the unscoped
    system path. Everything else passes straight through to the raw Motor db, so
    startup indexes, health checks and cross-tenant admin queries are unchanged.

    Without this, call sites that hold a raw system handle (e.g. routers/auth.py
    does `db = get_system_db()`) would bypass the proxy guard and write
    unattributed, unchained audit records.
    """

    __slots__ = ("_raw",)

    def __init__(self, raw):
        self._raw = raw

    def __getattr__(self, name: str):
        if name in APPEND_ONLY_COLLECTIONS:
            return AppendOnlyCollection(self._raw[name], name)
        return getattr(self._raw, name)

    def __getitem__(self, name: str):
        if name in APPEND_ONLY_COLLECTIONS:
            return AppendOnlyCollection(self._raw[name], name)
        return self._raw[name]


def get_system_db():
    """
    Get the (unscoped) database for system operations.
    Only use for: startup indexes, health checks, cross-tenant admin queries.

    The audit collections are still returned append-only + canonical (the
    immutability guard + auto-attribution/chaining apply); all other collections
    pass through to the raw Motor db unchanged.
    """
    from core.database import _raw_db

    return _SystemAuditGuardDB(_raw_db)


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

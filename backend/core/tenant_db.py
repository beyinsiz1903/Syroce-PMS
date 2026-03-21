"""
Tenant-Scoped Database Access (TI-001)
======================================
Prevents cross-tenant data leakage by auto-injecting tenant_id
into every query on tenant-scoped collections.

Usage in routes:
    from core.tenant_db import get_tenant_db, TenantScopedDB

    @router.get("/rooms")
    async def list_rooms(tdb: TenantScopedDB = Depends(get_tenant_db)):
        rooms = await tdb.rooms.find({}).to_list(100)
        # tenant_id is auto-injected — no need to specify it

If a query already has tenant_id, it is validated.
If it has a DIFFERENT tenant_id → TenantViolationError is raised.
"""
import logging
from typing import Any, Dict, Optional, Set

from core.database import db, client

logger = logging.getLogger("core.tenant_db")

# ── Collections where tenant_id filter is MANDATORY ──
TENANT_SCOPED_COLLECTIONS: Set[str] = {
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
    "tenant_access_logs", "tenant_isolation_policies",
}

# ── Collections that are global (no tenant_id) ──
GLOBAL_COLLECTIONS: Set[str] = {
    "tenants", "hotel_chains", "system_config", "system_logs",
    "subscription_plans", "marketplace_extensions",
}


class TenantViolationError(Exception):
    """Raised when a cross-tenant access attempt is detected."""


class TenantScopedCollection:
    """
    Wraps a Motor collection to auto-inject and validate tenant_id
    on every operation.
    """

    def __init__(self, collection, tenant_id: str, collection_name: str):
        self._coll = collection
        self._tenant_id = tenant_id
        self._name = collection_name

    def _inject_filter(self, filter_dict: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
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

    def _inject_doc(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        if "tenant_id" not in doc:
            doc["tenant_id"] = self._tenant_id
        elif doc["tenant_id"] != self._tenant_id:
            raise TenantViolationError(
                f"Cannot insert document for tenant {doc['tenant_id']} "
                f"into tenant-scoped context {self._tenant_id}"
            )
        return doc

    # ── Read operations ──

    async def find_one(self, filter=None, *args, **kwargs):
        return await self._coll.find_one(self._inject_filter(filter), *args, **kwargs)

    def find(self, filter=None, *args, **kwargs):
        return self._coll.find(self._inject_filter(filter), *args, **kwargs)

    async def count_documents(self, filter=None, *args, **kwargs):
        return await self._coll.count_documents(self._inject_filter(filter), *args, **kwargs)

    async def distinct(self, key, filter=None, *args, **kwargs):
        return await self._coll.distinct(key, self._inject_filter(filter), *args, **kwargs)

    def aggregate(self, pipeline, *args, **kwargs):
        # Prepend $match with tenant_id if not already present
        if pipeline and pipeline[0].get("$match"):
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

    # ── Index operations (pass-through) ──

    async def create_index(self, *args, **kwargs):
        return await self._coll.create_index(*args, **kwargs)

    async def list_indexes(self, *args, **kwargs):
        return await self._coll.list_indexes(*args, **kwargs)

    # ── Passthrough for other attributes ──
    def __getattr__(self, name):
        return getattr(self._coll, name)


class TenantScopedDB:
    """
    Database proxy that enforces tenant isolation.

    For tenant-scoped collections → returns TenantScopedCollection (auto-injects tenant_id).
    For global collections → returns raw Motor collection (no filter).
    For unknown collections → returns TenantScopedCollection (safe default).
    """

    def __init__(self, database, tenant_id: str):
        self._db = database
        self._tenant_id = tenant_id

    @property
    def tenant_id(self) -> str:
        return self._tenant_id

    @property
    def client(self):
        return self._db.client

    def __getattr__(self, name: str):
        coll = self._db[name]
        if name in GLOBAL_COLLECTIONS:
            return coll
        # Tenant-scoped or unknown → enforce isolation
        return TenantScopedCollection(coll, self._tenant_id, name)

    def __getitem__(self, name: str):
        return self.__getattr__(name)


# ── FastAPI Dependency ──

async def get_tenant_db(current_user=None) -> TenantScopedDB:
    """
    FastAPI dependency that returns a tenant-scoped database proxy.

    Usage:
        @router.get("/rooms")
        async def list_rooms(tdb: TenantScopedDB = Depends(get_tenant_db)):
            ...

    Note: This requires `current_user` to be injected. Override in routes.
    """
    if current_user is None:
        raise ValueError("get_tenant_db requires current_user")
    return TenantScopedDB(db, current_user.tenant_id)

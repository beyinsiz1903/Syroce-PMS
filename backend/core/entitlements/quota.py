from datetime import UTC, datetime
from typing import Any

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from core.database import db

_HR_MODULE = "hr"
_HR_ACTIVE_EMPLOYEES_METRIC = "active_employees"

# Bootstrap marker collection: ``entitlement_quota_bootstrap``
# Schema: { tenant_id, module_key, metric, completed_at }
# Unique index: (tenant_id, module_key, metric) — ensures only one
# bootstrap record per combination (set by ensure_indexes.py / startup).


class QuotaExceededException(Exception):
    pass

async def _ensure_quota_doc(
    tenant_id: str,
    module_key: str,
    metric: str,
    *,
    db_handle: Any = None,
) -> None:
    """Ensure a quota usage document exists for (tenant, module, metric).

    Uses the provided ``db_handle`` if given, otherwise falls back to the
    global ``db``.  Every caller inside bootstrap passes ``_db`` so that
    all writes go to the same database connection.
    """
    _db = db_handle if db_handle is not None else db
    try:
        await _db.entitlement_quota_usage.update_one(
            {
                "tenant_id": tenant_id,
                "module_key": module_key,
                "metric": metric
            },
            {
                "$setOnInsert": {
                    "used": 0,
                    "resources": [],
                    "created_at": datetime.now(UTC)
                }
            },
            upsert=True
        )
    except DuplicateKeyError:
        pass

async def reserve_quota(tenant_id: str, module_key: str, metric: str, resource_id: str, limit: int, force: bool = False) -> dict:
    """
    Atomically reserves a quota slot.
    If force=True, it will increment the quota even if it exceeds the limit.
    Idempotent: if resource_id is already reserved, returns safely.
    """
    if limit <= 0 and not force:
        raise QuotaExceededException(f"Kota limiti {limit} oldugu icin islem yapilamaz.")

    await _ensure_quota_doc(tenant_id, module_key, metric)
    now = datetime.now(UTC)

    query = {
        "tenant_id": tenant_id,
        "module_key": module_key,
        "metric": metric,
        "resources": {"$ne": resource_id}
    }
    if not force:
        query["used"] = {"$lt": limit}

    doc = await db.entitlement_quota_usage.find_one_and_update(
        query,
        {
            "$inc": {"used": 1},
            "$addToSet": {"resources": resource_id},
            "$set": {"updated_at": now}
        },
        return_document=ReturnDocument.AFTER
    )

    if not doc:
        # It failed. Let's check why.
        current = await db.entitlement_quota_usage.find_one({
            "tenant_id": tenant_id,
            "module_key": module_key,
            "metric": metric
        })
        # If it's already in the list, it's an idempotent success
        if current and resource_id in current.get("resources", []):
            return current

        raise QuotaExceededException(f"Maksimum limit ({limit}) asildi.")

    return doc

async def release_quota(tenant_id: str, module_key: str, metric: str, resource_id: str) -> None:
    """
    Atomically releases a quota slot.
    Idempotent: if resource_id is not found, does nothing.
    """
    now = datetime.now(UTC)
    await db.entitlement_quota_usage.update_one(
        {
            "tenant_id": tenant_id,
            "module_key": module_key,
            "metric": metric,
            "resources": resource_id,
            "used": {"$gt": 0}
        },
        {
            "$inc": {"used": -1},
            "$pull": {"resources": resource_id},
            "$set": {"updated_at": now}
        }
    )


# ── Bootstrap / Reconciliation ───────────────────────────────────────────────

async def is_hr_quota_bootstrapped(tenant_id: str, *, db_handle: Any = None) -> bool:
    """Return True if the one-time bootstrap has already completed for this tenant.

    Accepts an explicit ``db_handle`` so callers (bootstrap fn, tests, migrations)
    can guarantee the same DB connection is used throughout the operation.
    Falls back to the global ``db`` when ``db_handle`` is None.
    """
    _db = db_handle if db_handle is not None else db
    doc = await _db.entitlement_quota_bootstrap.find_one({
        "tenant_id": tenant_id,
        "module_key": _HR_MODULE,
        "metric": _HR_ACTIVE_EMPLOYEES_METRIC,
    })
    return doc is not None


async def _mark_hr_quota_bootstrapped(tenant_id: str, *, db_handle: Any = None) -> None:
    """Mark bootstrap as done. Idempotent — upsert so concurrent calls are safe.

    Accepts an explicit ``db_handle`` so the marker is written to the same
    database used by the surrounding bootstrap operation.
    """
    _db = db_handle if db_handle is not None else db
    try:
        await _db.entitlement_quota_bootstrap.update_one(
            {
                "tenant_id": tenant_id,
                "module_key": _HR_MODULE,
                "metric": _HR_ACTIVE_EMPLOYEES_METRIC,
            },
            {
                "$setOnInsert": {
                    "completed_at": datetime.now(UTC).isoformat(),
                }
            },
            upsert=True,
        )
    except DuplicateKeyError:
        # Another concurrent call won the upsert race — still done.
        pass


async def bootstrap_hr_active_employees(tenant_id: str, *, db_handle: Any = None) -> dict:
    """One-time reconciliation: imports all active, non-terminated staff_members
    into the ``active_employees`` quota ledger using each record's own ``id``
    as the ``resource_id``.

    Rules enforced:
    - Only ``staff_members`` collection (``users`` excluded).
    - Only active==True AND ``terminated_at`` absent/None.
    - Each staff_id is added at most once (``$addToSet``).
    - Does NOT enforce the plan limit — existing staff are never evicted.
    - Idempotent and safe to re-run: already-ledgered entries are skipped.
    - Concurrent invocations for the same tenant do not produce duplicate ledger
      entries because ``$addToSet`` is atomic.
    - A bootstrap marker is written after the sweep so subsequent requests skip
      the DB scan entirely.

    Returns a dict with summary stats.
    """
    _db = db_handle if db_handle is not None else db

    # Fast-path: bootstrap already done — pass _db through so the check
    # hits the same database as the rest of the operation.
    if await is_hr_quota_bootstrapped(tenant_id, db_handle=_db):
        return {"skipped": True, "reason": "already_bootstrapped"}

    # Gather active, non-terminated staff for this tenant.
    cursor = _db.staff_members.find(
        {
            "tenant_id": tenant_id,
            "active": True,
            "$or": [
                {"terminated_at": None},
                {"terminated_at": {"$exists": False}},
            ],
        },
        {"id": 1, "_id": 0},
    )
    staff_ids: list[str] = [doc["id"] async for doc in cursor if doc.get("id")]

    if not staff_ids:
        # Nothing to import; still mark done so we don't scan again.
        await _mark_hr_quota_bootstrapped(tenant_id, db_handle=_db)
        return {"skipped": False, "imported": 0, "staff_ids": []}

    # Ensure the quota document exists — pass _db through.
    await _ensure_quota_doc(tenant_id, _HR_MODULE, _HR_ACTIVE_EMPLOYEES_METRIC, db_handle=_db)

    # Add each staff_id that isn't already in the ledger.  A single
    # ``$addToSet`` with an ``$each`` modifier is atomic across the whole list.
    now = datetime.now(UTC)
    result = await _db.entitlement_quota_usage.find_one_and_update(
        {
            "tenant_id": tenant_id,
            "module_key": _HR_MODULE,
            "metric": _HR_ACTIVE_EMPLOYEES_METRIC,
        },
        {
            "$addToSet": {"resources": {"$each": staff_ids}},
            "$set": {"updated_at": now},
        },
        return_document=ReturnDocument.AFTER,
    )

    # Recompute ``used`` to match the authoritative resource list length.
    if result:
        canonical_count = len(result.get("resources", []))
        if result.get("used") != canonical_count:
            await _db.entitlement_quota_usage.update_one(
                {"tenant_id": tenant_id, "module_key": _HR_MODULE, "metric": _HR_ACTIVE_EMPLOYEES_METRIC},
                {"$set": {"used": canonical_count, "updated_at": now}},
            )

    # Persist the completion marker — using the same _db handle.
    await _mark_hr_quota_bootstrapped(tenant_id, db_handle=_db)

    return {"skipped": False, "imported": len(staff_ids), "staff_ids": staff_ids}

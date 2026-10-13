"""Cross-process serialization of agency admission checks and durable booking.

The Mongo _id unique constraint is the arbiter, not an in-process lock. No TTL:
a stalled/crashed writer must not lose its fence while it could still commit.
Orphan locks require operator reconciliation, never an automatic unsafe takeover.
"""
import hashlib
import json
import logging
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


@asynccontextmanager
async def agency_sale_guard(database, tenant_id, agency_id, *, operation="reservation", idempotency_key=None, reference_id=None):
    """Acquire an agency admission fence with enough context for manual recovery.

    A lock is intentionally never expired automatically.  The recovery console
    can release it only after an operator attests that the original writer has
    stopped and records the matching reservation/idempotency evidence.
    """
    key = hashlib.sha256(json.dumps([tenant_id, agency_id]).encode()).hexdigest()
    owner = str(uuid.uuid4())
    try:
        await database.agency_sale_mutexes.insert_one({
            "_id": key, "owner": owner, "tenant_id": tenant_id, "agency_id": agency_id,
            "operation": operation, "idempotency_key": idempotency_key,
            "reference_id": reference_id, "recovery_state": "active",
            "created_at": datetime.now(UTC),
        })
    except DuplicateKeyError:
        raise HTTPException(409, "Acente satış kontrolü meşgul. Aynı işlem anahtarıyla tekrar deneyin; sürerse destek ile iletişime geçin.") from None
    release = False
    try:
        yield
        release = True
    except HTTPException:
        release = True  # Validation/rejection: no ambiguous storage result.
        raise
    finally:
        if release:
            try:
                await database.agency_sale_mutexes.delete_one({"_id": key, "owner": owner})
            except Exception:
                # Keep the fence rather than return a false booking failure.
                logger.error("Agency admission fence cleanup failed; reconciliation required key=%s", key)
        else:
            logger.error("Agency admission result uncertain; fence retained key=%s", key)


async def durable_agency_replay(database, tenant_id, agency_id, key, request_hash):
    """Survives idempotency-cache expiry and a failed marketplace ledger write."""
    row = await database.bookings.find_one({
        "tenant_id": tenant_id, "agency_id": agency_id, "agency_idempotency_key": key,
    }, {"_id": 0})
    if not row:
        return None
    if row.get("agency_request_hash") != request_hash:
        raise HTTPException(409, "İşlem anahtarı farklı rezervasyon bilgileriyle kullanılmış")
    fields = ("id", "tenant_id", "confirmation_code", "status", "room_type", "rate_plan_code",
              "meal_plan", "cancellation_policy", "check_in", "check_out", "total_amount", "currency")
    row["integration_status"] = row.get("agency_completion", {}).get("status", "unknown")
    fields += ("integration_status",)
    return {"ok": True, "idempotent_replay": True, "reservation": {key: row.get(key) for key in fields}}

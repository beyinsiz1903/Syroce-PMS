"""Pessimistic reservation-detail edit locks.

One active edit lease is allowed per ``(tenant_id, booking_id)``.  The browser
owns a per-view ``lock_id`` and renews the lease every 30 seconds.  The server
lease is 120 seconds, so an abandoned tab self-heals without an operator-only
cleanup path.

The unique index makes acquire atomic across processes.  A competing upsert
hits the unique key and is surfaced as a lock conflict instead of creating two
simultaneous owners.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import DuplicateKeyError

LOCK_COLLECTION = "reservation_edit_locks"
LEASE_SECONDS = 120
HEARTBEAT_SECONDS = 30

_INDEX_READY = False
_INDEX_LOCK = asyncio.Lock()


class ReservationEditLockError(Exception):
    """Base reservation edit-lock error."""


class ReservationEditLockConflict(ReservationEditLockError):
    """Raised when another active view owns the reservation lock."""


class ReservationEditLockLost(ReservationEditLockError):
    """Raised when a view tries to renew/use a lease it no longer owns."""


@dataclass(frozen=True)
class ReservationEditLease:
    tenant_id: str
    booking_id: str
    lock_id: str
    owner_user_id: str
    acquired_at: datetime
    heartbeat_at: datetime
    expires_at: datetime

    @classmethod
    def from_doc(cls, doc: dict) -> "ReservationEditLease":
        return cls(
            tenant_id=str(doc["tenant_id"]),
            booking_id=str(doc["booking_id"]),
            lock_id=str(doc["lock_id"]),
            owner_user_id=str(doc["owner_user_id"]),
            acquired_at=doc["acquired_at"],
            heartbeat_at=doc["heartbeat_at"],
            expires_at=doc["expires_at"],
        )

    def public_dict(self) -> dict:
        return {
            "booking_id": self.booking_id,
            "lock_id": self.lock_id,
            "lease_seconds": LEASE_SECONDS,
            "heartbeat_seconds": HEARTBEAT_SECONDS,
            "acquired_at": self.acquired_at.isoformat(),
            "heartbeat_at": self.heartbeat_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
        }


def _utcnow() -> datetime:
    return datetime.now(UTC)


async def ensure_reservation_edit_lock_indexes(db) -> None:
    """Create the uniqueness + TTL backstops once per process."""
    global _INDEX_READY
    if _INDEX_READY:
        return

    async with _INDEX_LOCK:
        if _INDEX_READY:
            return
        collection = db[LOCK_COLLECTION]
        await collection.create_index(
            [("tenant_id", ASCENDING), ("booking_id", ASCENDING)],
            name="uq_reservation_edit_lock_tenant_booking",
            unique=True,
        )
        await collection.create_index(
            [("expires_at", ASCENDING)],
            name="ttl_reservation_edit_lock_expires",
            expireAfterSeconds=0,
        )
        _INDEX_READY = True


async def acquire_reservation_edit_lock(
    db,
    *,
    tenant_id: str,
    booking_id: str,
    owner_user_id: str,
    lock_id: str,
    now: datetime | None = None,
) -> ReservationEditLease:
    """Atomically acquire/reacquire one per-view reservation edit lease."""
    await ensure_reservation_edit_lock_indexes(db)
    now = now or _utcnow()
    expires_at = now + timedelta(seconds=LEASE_SECONDS)
    collection = db[LOCK_COLLECTION]

    query = {
        "tenant_id": tenant_id,
        "booking_id": booking_id,
        "$or": [
            {"expires_at": {"$lte": now}},
            {"owner_user_id": owner_user_id, "lock_id": lock_id},
        ],
    }
    update = {
        "$set": {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "owner_user_id": owner_user_id,
            "lock_id": lock_id,
            # Every explicit acquire starts a fresh lease epoch. Heartbeats only
            # extend heartbeat_at/expires_at and never rewrite acquired_at.
            "acquired_at": now,
            "heartbeat_at": now,
            "expires_at": expires_at,
        },
    }

    try:
        doc = await collection.find_one_and_update(
            query,
            update,
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise ReservationEditLockConflict("reservation is locked by another active view") from exc

    if not doc:
        raise ReservationEditLockConflict("reservation edit lock could not be acquired")

    if doc.get("owner_user_id") != owner_user_id or doc.get("lock_id") != lock_id:
        # Defensive only: the atomic update above should already have replaced
        # owner/lock fields. Fail closed rather than returning an ambiguous lease.
        raise ReservationEditLockConflict("reservation edit lock ownership is ambiguous")

    return ReservationEditLease.from_doc(doc)


async def renew_reservation_edit_lock(
    db,
    *,
    tenant_id: str,
    booking_id: str,
    owner_user_id: str,
    lock_id: str,
    now: datetime | None = None,
) -> ReservationEditLease:
    """Renew only the exact, still-active owner/view lease."""
    await ensure_reservation_edit_lock_indexes(db)
    now = now or _utcnow()
    expires_at = now + timedelta(seconds=LEASE_SECONDS)
    collection = db[LOCK_COLLECTION]

    doc = await collection.find_one_and_update(
        {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "owner_user_id": owner_user_id,
            "lock_id": lock_id,
            "expires_at": {"$gt": now},
        },
        {"$set": {"heartbeat_at": now, "expires_at": expires_at}},
        return_document=ReturnDocument.AFTER,
    )
    if not doc:
        raise ReservationEditLockLost("reservation edit lease expired or ownership changed")
    return ReservationEditLease.from_doc(doc)


async def assert_reservation_edit_lock(
    db,
    *,
    tenant_id: str,
    booking_id: str,
    owner_user_id: str,
    lock_id: str,
    now: datetime | None = None,
) -> ReservationEditLease:
    """Validate an active exact-owner lease without extending it."""
    now = now or _utcnow()
    doc = await db[LOCK_COLLECTION].find_one(
        {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "owner_user_id": owner_user_id,
            "lock_id": lock_id,
            "expires_at": {"$gt": now},
        },
        {"_id": 0},
    )
    if not doc:
        raise ReservationEditLockLost("active reservation edit lock required")
    return ReservationEditLease.from_doc(doc)


async def release_reservation_edit_lock(
    db,
    *,
    tenant_id: str,
    booking_id: str,
    owner_user_id: str,
    lock_id: str,
) -> bool:
    """Owner-only unlock. Missing/expired rows are idempotent."""
    collection = db[LOCK_COLLECTION]
    current = await collection.find_one(
        {"tenant_id": tenant_id, "booking_id": booking_id},
        {"_id": 0, "owner_user_id": 1, "lock_id": 1},
    )
    if not current:
        return False
    if str(current.get("owner_user_id")) != owner_user_id or str(current.get("lock_id")) != lock_id:
        raise ReservationEditLockConflict("only the current reservation edit-lock owner may unlock")

    result = await collection.delete_one(
        {
            "tenant_id": tenant_id,
            "booking_id": booking_id,
            "owner_user_id": owner_user_id,
            "lock_id": lock_id,
        }
    )
    return result.deleted_count == 1

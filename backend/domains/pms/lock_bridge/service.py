"""Lock-bridge service: command queue + connector auth.

All operations are tenant-scoped and fail-closed. Connector keys are stored only
as salted SHA-256 hashes (never plaintext, never logged). Command enqueue is
idempotent via a unique ``(tenant_id, dedup_key)`` index, so a retried lifecycle
event (re-issue, re-checkout) can never produce a duplicate physical-card action.
"""

import hashlib
import logging
import os
import secrets
import uuid
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

# Vendor-neutral command verbs the on-prem connector understands.
CMD_ENCODE = "encode_card"
CMD_REVOKE = "revoke_card"

_PENDING = "pending"
_CLAIMED = "claimed"
_DONE = "done"
_FAILED = "failed"

_TERMINAL = {_DONE, _FAILED}

# A claimed command whose connector crashes before ack must not stay stuck
# forever; after this lease elapses another poll may reclaim it so the physical
# card eventually gets encoded/revoked (at-least-once delivery).
_CLAIM_LEASE_SECONDS = 120


def _key_pepper() -> str:
    return (os.environ.get("LOCK_BRIDGE_KEY_PEPPER") or "").strip()


def hash_connector_key(plaintext: str) -> str:
    """Salted SHA-256 of a connector key. Keys are high-entropy random tokens."""
    pepper = _key_pepper()
    return hashlib.sha256(f"{pepper}:{plaintext}".encode()).hexdigest()


async def ensure_lock_bridge_indexes(db) -> None:
    """Create idempotency + claim indexes. Safe to call repeatedly."""
    await db.lock_commands.create_index(
        [("tenant_id", 1), ("dedup_key", 1)],
        unique=True,
        name="uniq_lock_cmd_dedup",
    )
    await db.lock_commands.create_index(
        [("tenant_id", 1), ("status", 1), ("created_at", 1)],
        name="idx_lock_cmd_claim",
    )
    await db.lock_bridge_connectors.create_index([("key_hash", 1)], unique=True, name="uniq_lock_connector_key")


async def enqueue_lock_command(
    db,
    *,
    tenant_id: str,
    command: str,
    keycard_id: str,
    booking_id: str | None = None,
    room_number: str | None = None,
    card_number: str | None = None,
    valid_from: str | None = None,
    valid_until: str | None = None,
) -> bool:
    """Idempotently enqueue a lock command for the on-prem connector.

    Returns True if a new command was enqueued, False if it already existed
    (idempotent no-op). Fail-soft: never raises into the calling lifecycle path;
    a transient failure is logged (without PII) and the desk can re-issue.
    """
    if not tenant_id or not keycard_id or command not in (CMD_ENCODE, CMD_REVOKE):
        return False
    # dedup_key makes (encode|revoke) of a given keycard exactly-once.
    dedup_key = f"{command}:{keycard_id}"
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "command": command,
        "keycard_id": keycard_id,
        "booking_id": booking_id,
        "room_number": room_number,
        "card_number": card_number,
        "valid_from": valid_from,
        "valid_until": valid_until,
        "status": _PENDING,
        "dedup_key": dedup_key,
        "attempts": 0,
        "created_at": datetime.now(UTC).isoformat(),
        "claimed_at": None,
        "claimed_by": None,
        "completed_at": None,
        "result": None,
    }
    try:
        await db.lock_commands.insert_one(doc)
        return True
    except Exception as e:  # noqa: BLE001 - includes DuplicateKeyError (idempotent)
        if e.__class__.__name__ == "DuplicateKeyError":
            return False
        logger.warning("lock_bridge enqueue failed (tenant=%s command=%s)", tenant_id, command)
        return False


async def claim_commands(
    db,
    *,
    tenant_id: str,
    connector_id: str | None = None,
    limit: int = 20,
    lease_seconds: int = _CLAIM_LEASE_SECONDS,
) -> list[dict]:
    """Atomically claim up to ``limit`` claimable commands (CAS -> claimed).

    A command is claimable when it is ``pending`` OR it was ``claimed`` but the
    claim lease has elapsed (the previous connector crashed before ack). Each
    command is handed to exactly one connector poll via a per-document
    compare-and-set guarded on the prior ``(status, claimed_at)``, so concurrent
    polls never double-deliver and a stale claim can be safely reclaimed.
    """
    limit = max(1, min(100, int(limit)))
    claimed: list[dict] = []
    seen: list[str] = []
    while len(claimed) < limit:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat()
        cutoff = (now_dt - timedelta(seconds=max(0, int(lease_seconds)))).isoformat()
        flt: dict = {
            "tenant_id": tenant_id,
            "$or": [
                {"status": _PENDING},
                {"status": _CLAIMED, "claimed_at": {"$lt": cutoff}},
            ],
        }
        if seen:
            flt["id"] = {"$nin": seen}
        candidate = await db.lock_commands.find_one(flt, sort=[("created_at", 1)], projection={"_id": 0})
        if not candidate:
            break
        seen.append(candidate["id"])
        # CAS guarded on the exact prior state so a concurrent poll that already
        # (re)claimed this command between our read and write loses the race.
        res = await db.lock_commands.update_one(
            {
                "id": candidate["id"],
                "tenant_id": tenant_id,
                "status": candidate["status"],
                "claimed_at": candidate.get("claimed_at"),
            },
            {
                "$set": {"status": _CLAIMED, "claimed_at": now, "claimed_by": connector_id},
                "$inc": {"attempts": 1},
            },
        )
        if getattr(res, "matched_count", 0) == 1:
            candidate["status"] = _CLAIMED
            candidate["claimed_at"] = now
            candidate["claimed_by"] = connector_id
            claimed.append(_connector_view(candidate))
    return claimed


def _connector_view(cmd: dict) -> dict:
    """Trim a command to the vendor-neutral wire contract (no internal fields)."""
    return {
        "id": cmd.get("id"),
        "command": cmd.get("command"),
        "keycard_id": cmd.get("keycard_id"),
        "booking_id": cmd.get("booking_id"),
        "room_number": cmd.get("room_number"),
        "card_number": cmd.get("card_number"),
        "valid_from": cmd.get("valid_from"),
        "valid_until": cmd.get("valid_until"),
        "attempts": cmd.get("attempts"),
        "created_at": cmd.get("created_at"),
    }


async def ack_command(
    db,
    *,
    tenant_id: str,
    command_id: str,
    success: bool,
    detail: str | None = None,
    connector_id: str | None = None,
) -> bool:
    """Mark a claimed command done/failed (tenant-scoped). Idempotent on terminal.

    A failed command is returned to ``pending`` (claim cleared) so the connector
    retries it on a later poll (the physical card must eventually be
    encoded/revoked); the result detail is recorded for the operator. When
    ``connector_id`` is given the ack is bound to the connector that currently
    holds the claim, so a connector cannot finalize a command it does not own
    (e.g. after its lease expired and another connector reclaimed it). Returns
    False if the command does not belong to this tenant, is already terminal, or
    is no longer held by this connector.
    """
    cmd = await db.lock_commands.find_one({"id": command_id, "tenant_id": tenant_id}, {"_id": 0})
    if not cmd or cmd.get("status") in _TERMINAL:
        return False
    now = datetime.now(UTC).isoformat()
    if success:
        update = {"status": _DONE, "completed_at": now, "result": (detail or "")[:500]}
    else:
        # Re-queue for retry; release the claim so any connector can pick it up.
        update = {
            "status": _PENDING,
            "claimed_at": None,
            "claimed_by": None,
            "result": (detail or "")[:500],
        }
    cas: dict = {
        "id": command_id,
        "tenant_id": tenant_id,
        "status": {"$nin": list(_TERMINAL)},
    }
    if connector_id is not None:
        cas["claimed_by"] = connector_id
    res = await db.lock_commands.update_one(cas, {"$set": update})
    return getattr(res, "matched_count", 0) == 1


async def register_connector(db, *, tenant_id: str, name: str) -> str:
    """Register an on-prem connector and return its plaintext key ONCE.

    Only the salted hash is persisted; the caller must capture the returned
    plaintext immediately (it cannot be recovered later).
    """
    plaintext = secrets.token_urlsafe(32)
    doc = {
        "id": str(uuid.uuid4()),
        "tenant_id": tenant_id,
        "name": name,
        "key_hash": hash_connector_key(plaintext),
        "active": True,
        "created_at": datetime.now(UTC).isoformat(),
        "last_seen_at": None,
    }
    await db.lock_bridge_connectors.insert_one(doc)
    return plaintext


async def resolve_connector(db, provided_key: str | None) -> dict | None:
    """Resolve a connector key to its stored record. Fail-closed: None on miss.

    Identity (tenant_id + connector id) is derived from the stored record, never
    from client input. Touches ``last_seen_at`` as best-effort telemetry.
    """
    candidate = (provided_key or "").strip()
    if not candidate:
        return None
    record = await db.lock_bridge_connectors.find_one({"key_hash": hash_connector_key(candidate), "active": True}, {"_id": 0})
    if not record:
        return None
    try:
        await db.lock_bridge_connectors.update_one(
            {"id": record["id"]},
            {"$set": {"last_seen_at": datetime.now(UTC).isoformat()}},
        )
    except Exception:  # noqa: BLE001 - last_seen is best-effort telemetry
        pass
    return record


async def authenticate_connector(db, provided_key: str | None) -> str | None:
    """Resolve a connector key to its tenant_id. Fail-closed: None on any miss.

    Tenant is derived from the stored connector record, never from client input.
    """
    record = await resolve_connector(db, provided_key)
    return record.get("tenant_id") if record else None

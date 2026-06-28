"""Transaction-backed booking helpers for spa appointments and MICE events.

Pattern
-------
The conflict checks for therapist/room/space bookings are inherently
*range overlap* checks — a unique index alone cannot enforce them.
We instead combine two MongoDB primitives that ARE atomic:

1. **Lock document per resource** — a row in `<module>_locks` keyed by
   `(tenant_id, kind, resource_id)`. We `update_one(upsert=True)` the
   row inside the transaction, which serializes any other transaction
   that touches the same document (it will get a `WriteConflict` and
   the driver auto-retries via `with_transaction()`).
2. **Read overlap inside the transaction** — once we hold the lock on
   every affected resource, a snapshot read of the existing rows for
   that resource cannot race against a parallel writer.

`with_transaction()` retries `TransientTransactionError` automatically
per MongoDB best practice, so callers get serializable semantics for
the conflict check + insert/update without explicit retry loops.

Atlas (a replica set) supports multi-document transactions, so this
pattern is production-safe for our deployment target.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Awaitable, Callable

from pymongo.errors import OperationFailure
from pymongo.read_concern import ReadConcern
from pymongo.write_concern import WriteConcern


def standalone_fallback_allowed() -> bool:
    """Fallback to non-transactional booking is **off by default**.

    Atlas (production) is a replica set so transactions always work; the
    fallback path only matters for standalone-Mongo local dev. Without
    transactions we cannot serialize the conflict-check + insert, which
    can permit double-bookings under concurrency. Operators must
    explicitly opt in via env to accept that risk in dev environments.
    """
    return os.getenv("ALLOW_STANDALONE_BOOKING_FALLBACK", "").lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def with_resource_locks(
    *,
    client,
    db,
    tenant_id: str,
    locks_collection: str,
    resources: list[tuple[str, str]],  # [(kind, resource_id), …]
    callback: Callable[[object], Awaitable[dict]],
) -> dict:
    """Run *callback(session)* inside a transaction holding locks on
    every (kind, resource_id) tuple in *resources*.

    Concurrent calls touching the same lock document conflict on commit
    (`WriteConflict`), and the Mongo driver retries the entire callback
    transparently.
    """
    async with await client.start_session() as session:

        async def _txn(s):
            now_iso = datetime.now(UTC).isoformat()
            for kind, rid in resources:
                if not rid:
                    continue
                await db[locks_collection].update_one(
                    {"tenant_id": tenant_id, "kind": kind, "resource_id": rid},
                    {"$set": {"touched_at": now_iso}, "$setOnInsert": {"created_at": now_iso}},
                    upsert=True,
                    session=s,
                )
            return await callback(s)

        return await session.with_transaction(
            _txn,
            read_concern=ReadConcern("snapshot"),
            write_concern=WriteConcern("majority"),
        )


def is_replica_set_unavailable(exc: Exception) -> bool:
    """Detect 'Transaction numbers are only allowed on a replica set' style
    errors — used to allow standalone-MongoDB local dev fallback.
    """
    if not isinstance(exc, OperationFailure):
        return False
    msg = str(exc).lower()
    return ("replica set" in msg) or ("transactions are not supported" in msg)

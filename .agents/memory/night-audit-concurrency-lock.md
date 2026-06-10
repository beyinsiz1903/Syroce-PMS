---
name: Night audit run-level concurrency lock
description: How the pms-core night audit is made safe against two simultaneous runs double-posting room charges / double-incrementing folio.balance.
---

# Night audit concurrency lock

Two simultaneous night-audit runs for the same (tenant_id, business_date) must
post a booking's room charge exactly once and increment folio.balance exactly
once. The guard is TWO layers, and both are required:

1. A run-level lock on collection `night_audit_locks` (upsert
   `{tenant_id, business_date, released:False}` with `$setOnInsert`; acquired
   only if `upserted_id is not None`).
2. A DB-level unique dedup index on `folio_charges`
   (tenant_id, booking_id, business_date, charge_type) as the backstop.

## Rule 1 — a Mongo upsert lock is NOT atomic without a unique index
**Why:** two concurrent upserts that both match no document will BOTH insert
and BOTH return an upserted_id → both "acquire" the lock → double-post. The
lock is only a real mutex with a unique partial index on the filter fields:
`idx_na_locks_active_unique` on (tenant_id, business_date)
`partialFilterExpression {released:False}` (one active lock per tenant+date;
released docs fall out of the index so re-runs are allowed). With it, the race
loser gets DuplicateKeyError OR matched=1/upserted_id=None — keep the
`upserted_id is not None` check, it handles both.
**How to apply:** any "lock via upsert" pattern in this codebase needs the
matching unique (partial) index created at startup, or it silently allows
concurrent acquisition. The index is the load-bearing part, not the code.

## Rule 2 — release the lock BY lock_id, never by (tenant_id, business_date)
**Why:** once stale-takeover exists, releasing by (tenant,date) can match an
older released doc (deadlock) or, after a takeover, release the NEW owner's
lock and reopen the double-post window. Each run holds its own `lock_id` and
releases `{id: lock_id, released:False}`.
**How to apply:** mirror this if you copy the dead
`domains/pms/night_audit/service.py` lock convention — it releases by
(tenant,date) and has no stale-takeover, which is unsafe on a live path.

## Rule 3 — the revenue backstop is the folio_charges dedup index, not the lock
**Why:** the lock can be bypassed (e.g. a run exceeding the 900s stale window
gets taken over while still alive). The unique dedup index then rejects the
duplicate charge insert; the engine's BulkWriteError reconcile excludes the
rejected ids from inserted_ids and the balance `$inc` loop only increments for
inserted_ids → double-$inc is structurally impossible. For this to work the
engine room-charge doc MUST carry `business_date` + `charge_type="room_charge"`
(it historically only had charge_category="room" + night_audit_date, which the
index does NOT cover). This also shares the dedup keyspace with the hardened
engine — desirable cross-engine idempotency (one room night posts once).

## Stale takeover
900s threshold (matches hardened engine). Conditional release
`{released:False, acquired_at:{$lt:cutoff}}` is a single atomic update_one
(only one caller wins modified_count=1), retry upsert again guarded by the
unique index. ISO-string `$lt` is valid because both sides use
`datetime.now(UTC).isoformat()` (fixed-width UTC). Release in `finally` AFTER
all awaited charge/$inc/snapshot/roll/record work — no pre-durability window.

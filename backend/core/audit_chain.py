"""
Core — Tamper-evident audit chain.

Every audit record is linked to the previous record for its tenant via a
SHA-256 hash chain:

    record_hash = sha256( canonical(record_core) + prev_hash )

A monotonic per-tenant sequence number (`seq`) provides a deterministic walk
order, and the previous record's `record_hash` is stored as `prev_hash`. If any
persisted record is later edited or deleted, recomputing the chain no longer
matches the stored hashes — the tamper is detectable.

Chain state (`seq` + `last_hash`) lives in the `audit_chain_state` collection,
one document per tenant (`_id == tenant_id`). Linking uses a compare-and-swap on
`seq` so concurrent writers cannot fork the chain.

This module is intentionally self-contained and best-effort on the WRITE side: if
chain linking fails (DB hiccup), the audit record is still written WITHOUT chain
fields rather than losing the audit event. The VERIFIER, however, is fail-visible:
records written before the chain genesis are honestly skipped as legacy, but any
unchained record written AFTER the genesis is surfaced as an integrity break so a
silent linking gap can never masquerade as a healthy chain.
"""

import hashlib
import json
import logging

logger = logging.getLogger(__name__)

CHAIN_STATE_COLLECTION = "audit_chain_state"
HOT_COLLECTION = "audit_logs"
ARCHIVE_COLLECTION = "audit_logs_archive"
# Collections that together hold the full retained audit trail. The verifier
# walks both so the chain stays continuous across the retention move.
_CHAIN_COLLECTIONS = (HOT_COLLECTION, ARCHIVE_COLLECTION)

# Fields that participate in the per-record content hash. Order is irrelevant
# (canonical JSON sorts keys); presence/absence is what matters.
_HASHED_FIELDS = (
    "tenant_id",
    "actor_id",
    "operation_name",
    "action",
    "target_type",
    "entity_type",
    "target_id",
    "entity_id",
    "result_status",
    "severity",
    "before_snapshot",
    "after_snapshot",
    "ip_address",
    "user_agent",
    "timestamp",
)


def _canonical(value) -> str:
    """Deterministic JSON for hashing (sorted keys, str fallback for exotics)."""
    return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False, separators=(",", ":"))


def compute_record_hash(entry: dict, seq: int, prev_hash: str) -> str:
    """SHA-256 over the record's stable content + chain links."""
    core = {k: entry.get(k) for k in _HASHED_FIELDS}
    core["seq"] = seq
    core["prev_hash"] = prev_hash or ""
    digest = hashlib.sha256(_canonical(core).encode("utf-8")).hexdigest()
    return digest


def _system_db():
    from core.tenant_db import get_system_db

    return get_system_db()


async def _link_chain(tenant_id: str, entry: dict) -> tuple[int, str, str]:
    """Atomically reserve the next (seq, prev_hash) for `tenant_id` and return
    (seq, prev_hash, record_hash). Compare-and-swap on `seq` serializes the
    chain even under concurrent writers. Raises on persistent contention.
    """
    from pymongo import ReturnDocument

    sysdb = _system_db()
    coll = sysdb[CHAIN_STATE_COLLECTION]

    # Initialize the genesis state document once (race-safe via upsert filter).
    for _ in range(8):
        state = await coll.find_one({"_id": tenant_id})
        if state is None:
            seq = 1
            prev_hash = ""
            record_hash = compute_record_hash(entry, seq, prev_hash)
            # Insert genesis only if it still doesn't exist.
            res = await coll.find_one_and_update(
                {"_id": tenant_id, "seq": {"$exists": False}},
                {"$set": {"seq": seq, "last_hash": record_hash}},
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            if res and res.get("seq") == seq and res.get("last_hash") == record_hash:
                return seq, prev_hash, record_hash
            # Lost the genesis race — retry through the CAS branch.
            continue

        cur_seq = int(state.get("seq", 0))
        prev_hash = state.get("last_hash", "") or ""
        seq = cur_seq + 1
        record_hash = compute_record_hash(entry, seq, prev_hash)
        # CAS: only advance if seq is still what we read.
        res = await coll.find_one_and_update(
            {"_id": tenant_id, "seq": cur_seq},
            {"$set": {"seq": seq, "last_hash": record_hash}},
            return_document=ReturnDocument.AFTER,
        )
        if res is not None and res.get("seq") == seq:
            return seq, prev_hash, record_hash
        # Concurrent writer advanced seq — retry.

    raise RuntimeError(f"audit chain CAS contention for tenant {tenant_id}")


async def append_audit_log(db, entry: dict) -> dict:
    """Single canonical audit insert: fills chain fields + persists.

    `db` is whatever collection-bearing handle the caller already uses (the
    tenant-scoped proxy or a system db). Chain-state bookkeeping always uses the
    system db so it works in request, worker, and Celery contexts alike.

    Best-effort: a chain-linking failure still writes the record (unchained) so
    the audit event is never lost.
    """
    tenant_id = entry.get("tenant_id")
    if tenant_id:
        try:
            seq, prev_hash, record_hash = await _link_chain(tenant_id, entry)
            entry["seq"] = seq
            entry["prev_hash"] = prev_hash
            entry["record_hash"] = record_hash
        except Exception as exc:
            logger.warning("audit chain link failed (writing unchained): %s", exc)

    await db.audit_logs.insert_one(entry)
    return entry


async def verify_chain(tenant_id: str, limit: int = 5000) -> dict:
    """Walk a tenant's full audit chain (hot + archive) and report integrity.

    Returns:
        {
          "ok": bool,                # True only when no breaks AND no gaps
          "checked": int,            # chained records examined
          "breaks": [ {seq, id, reason, ...}, ... ],
          "last_seq": int | None,
          "unverifiable": int,       # post-genesis unchained records (gaps)
          "legacy_skipped": int,     # pre-genesis unchained (honestly skipped)
        }

    Records carrying a `record_hash` are verified for content + link continuity.
    Both the hot `audit_logs` and the immutable `audit_logs_archive` collections
    are unioned and sorted by `seq`, so the chain remains continuous across the
    retention move. The first chained record in the window is treated as the
    chain start (its `prev_hash` is not compared to a predecessor outside the
    window).

    Fail-visible: a record written BEFORE the chain genesis is legacy and
    skipped, but any unchained record written AFTER the genesis is counted as an
    `unverifiable` gap and forces `ok=false` — a silent linking failure can never
    be reported as a healthy chain.
    """
    sysdb = _system_db()

    # ── Gather chained rows from hot + archive, merged + de-duplicated by seq ──
    chained: list[dict] = []
    truncated = False
    for coll_name in _CHAIN_COLLECTIONS:
        cursor = (
            sysdb[coll_name]
            .find(
                {"tenant_id": tenant_id, "record_hash": {"$exists": True}},
                {"_id": 0},
            )
            .sort("seq", 1)
            .limit(limit)
        )
        part = await cursor.to_list(limit)
        if len(part) >= limit:
            truncated = True
        chained.extend(part)

    chained.sort(key=lambda r: r.get("seq") if isinstance(r.get("seq"), int) else 0)
    rows: list[dict] = []
    seen_seq: set = set()
    for r in chained:
        s = r.get("seq")
        if s in seen_seq:
            continue
        seen_seq.add(s)
        rows.append(r)

    breaks: list[dict] = []
    prev_record_hash: str | None = None
    last_seq = None
    genesis_ts = None
    checked = 0

    for idx, row in enumerate(rows):
        seq = row.get("seq")
        stored_hash = row.get("record_hash")
        stored_prev = row.get("prev_hash", "") or ""
        if genesis_ts is None:
            genesis_ts = row.get("timestamp")
        last_seq = seq
        checked += 1

        # Recompute this record's hash from its persisted content.
        recomputed = compute_record_hash(row, seq, stored_prev)
        if recomputed != stored_hash:
            breaks.append(
                {
                    "seq": seq,
                    "id": row.get("id"),
                    "reason": "content_hash_mismatch",
                }
            )

        # Link continuity (skip for the first record in the window).
        if idx > 0 and prev_record_hash is not None and stored_prev != prev_record_hash:
            breaks.append(
                {
                    "seq": seq,
                    "id": row.get("id"),
                    "reason": "prev_hash_mismatch",
                }
            )

        prev_record_hash = stored_hash

    # ── Fail-visible gap detection: unchained rows written after genesis ──
    unverifiable = 0
    legacy_skipped = 0
    for coll_name in _CHAIN_COLLECTIONS:
        coll = sysdb[coll_name]
        if genesis_ts is not None:
            unverifiable += await coll.count_documents(
                {
                    "tenant_id": tenant_id,
                    "record_hash": {"$exists": False},
                    "timestamp": {"$gte": genesis_ts},
                }
            )
            legacy_skipped += await coll.count_documents(
                {
                    "tenant_id": tenant_id,
                    "record_hash": {"$exists": False},
                    "timestamp": {"$lt": genesis_ts},
                }
            )
        else:
            # No chained record at all → chain has not started; every unchained
            # row is legacy (forward-only), not a gap.
            legacy_skipped += await coll.count_documents(
                {
                    "tenant_id": tenant_id,
                    "record_hash": {"$exists": False},
                }
            )

    if unverifiable > 0:
        breaks.append(
            {
                "seq": None,
                "id": None,
                "reason": "unverifiable_unchained_records",
                "count": unverifiable,
            }
        )

    return {
        "ok": len(breaks) == 0,
        "checked": checked,
        "breaks": breaks,
        "last_seq": last_seq,
        "unverifiable": unverifiable,
        "legacy_skipped": legacy_skipped,
        "truncated": truncated,
    }

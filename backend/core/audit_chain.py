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


def attribute_audit_entry(entry: dict) -> dict:
    """Fill request attribution BEFORE sealing; never mutate sealed content.

    Canonical helper writes and direct proxy inserts share this boundary. A
    proxy must not add hashed IP/device fields after append_audit_log has
    reserved the sequence and computed its content hash.
    """
    if "record_hash" in entry:
        return entry
    try:
        from common.request_context import get_client_ip, get_user_agent

        for field, value in (("ip_address", get_client_ip()), ("user_agent", get_user_agent())):
            if not entry.get(field) and value:
                entry[field] = value
    except Exception:
        logger.debug("audit attribution fill failed", exc_info=True)
    return entry


def _system_db():
    from core.tenant_db import get_system_db

    return get_system_db()


async def _link_chain(tenant_id: str, entry: dict, session=None) -> tuple[int, str, str]:
    """Atomically reserve the next (seq, prev_hash) for `tenant_id` and return
    (seq, prev_hash, record_hash). Compare-and-swap on `seq` serializes the
    chain even under concurrent writers. Raises on persistent contention.
    """
    from pymongo import ReturnDocument

    sysdb = _system_db()
    coll = sysdb[CHAIN_STATE_COLLECTION]
    session_kwargs = {"session": session} if session is not None else {}

    # Initialize the genesis state document once (race-safe via upsert filter).
    for _ in range(8):
        state = await coll.find_one({"_id": tenant_id}, **session_kwargs)
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
                **session_kwargs,
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
            **session_kwargs,
        )
        if res is not None and res.get("seq") == seq:
            return seq, prev_hash, record_hash
        # Concurrent writer advanced seq — retry.

    raise RuntimeError(f"audit chain CAS contention for tenant {tenant_id}")


async def append_audit_log(db, entry: dict, session=None, *, require_chain=False) -> dict:
    """Single canonical audit insert: fills chain fields + persists.

    `db` is whatever collection-bearing handle the caller already uses (the
    tenant-scoped proxy or a system db). Chain-state bookkeeping always uses the
    system db so it works in request, worker, and Celery contexts alike.

    Best-effort: a chain-linking failure still writes the record (unchained) so
    the audit event is never lost. Financial callers may opt into require_chain
    inside their transaction: a linking failure then aborts the financial write
    instead of allowing an unchained record or a proxy re-link outside session.
    """
    attribute_audit_entry(entry)
    tenant_id = entry.get("tenant_id")
    if require_chain and not tenant_id:
        raise ValueError("A required audit chain needs a tenant_id")
    if tenant_id:
        try:
            seq, prev_hash, record_hash = await _link_chain(tenant_id, entry, session=session)
            entry["seq"] = seq
            entry["prev_hash"] = prev_hash
            entry["record_hash"] = record_hash
        except Exception as exc:
            if require_chain:
                raise
            logger.warning("audit chain link failed (writing unchained): %s", exc)

    insert_kwargs = {"session": session} if session is not None else {}
    await db.audit_logs.insert_one(entry, **insert_kwargs)
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
          "as_of_seq": int | None,   # captured commitment before reading rows
          "concurrent_appends": bool,# newer events excluded from this prefix
        }

    Records carrying a `record_hash` are verified for content + link continuity.
    Both the hot `audit_logs` and the immutable `audit_logs_archive` collections
    are unioned and sorted by `seq`, so the chain remains continuous across the
    retention move. The first chained record in the window is treated as the
    chain start (its `prev_hash` is not compared to a predecessor outside the
    window). The sequence horizon is captured at scan start; newer appends are
    disclosed but are not evidence of deletion in the already-read prefix.
    This is not a snapshot transaction or certification of later events.

    Fail-visible: a record written BEFORE the chain genesis is legacy and
    skipped, but any unchained record written AFTER the genesis is counted as an
    `unverifiable` gap and forces `ok=false` — a silent linking failure can never
    be reported as a healthy chain.
    """
    sysdb = _system_db()

    # Fix the verification horizon BEFORE reading either collection. Appends
    # during the scan must not be compared with a newer state tip after an
    # older cursor was already consumed (a false deleted-tail warning).
    # This is a sequence-prefix check, not a database snapshot transaction.
    chain_state = await sysdb[CHAIN_STATE_COLLECTION].find_one(
        {"_id": tenant_id}, {"_id": 0, "seq": 1, "last_hash": 1},
    )
    chain_state = dict(chain_state) if chain_state else None
    as_of_seq = chain_state.get("seq") if chain_state else None
    valid_horizon = isinstance(as_of_seq, int) and not isinstance(as_of_seq, bool) and as_of_seq >= 0
    sequence_bound = {"seq": {"$lte": as_of_seq if valid_horizon else 0}}

    # ── Gather chained rows from hot + archive, merged + de-duplicated by seq ──
    chained: list[dict] = []
    truncated = False
    for coll_name in _CHAIN_COLLECTIONS:
        cursor = (
            sysdb[coll_name]
            .find(
                {"tenant_id": tenant_id, "record_hash": {"$exists": True}, **sequence_bound},
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
    invalid_sequences = 0
    chained_without_commitment = 0
    for coll_name in _CHAIN_COLLECTIONS:
        coll = sysdb[coll_name]
        invalid_sequences += await coll.count_documents({
            "tenant_id": tenant_id, "record_hash": {"$exists": True},
            "$or": [{"seq": {"$not": {"$type": ["int", "long"]}}}, {"seq": {"$lt": 1}}],
        })
        if not valid_horizon:
            chained_without_commitment += await coll.count_documents({"tenant_id": tenant_id, "record_hash": {"$exists": True}})
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

    # The captured state is still the commitment that detects a deleted tail;
    # never replace it with the live (possibly advanced) tip. A bounded response
    # naturally stops before the captured tip and must disclose truncation.
    latest_state = await sysdb[CHAIN_STATE_COLLECTION].find_one(
        {"_id": tenant_id},
        {"_id": 0, "seq": 1, "last_hash": 1},
    )
    if chain_state and not truncated:
        expected_seq = chain_state.get("seq")
        expected_hash = chain_state.get("last_hash")
        actual_hash = rows[-1].get("record_hash") if rows else None
        if expected_seq != last_seq or expected_hash != actual_hash:
            breaks.append(
                {
                    "seq": last_seq,
                    "id": rows[-1].get("id") if rows else None,
                    "reason": "chain_state_tip_mismatch",
                    "expected_seq": expected_seq,
                    "actual_seq": last_seq,
                }
            )

    latest_seq = latest_state.get("seq") if latest_state else None
    concurrent_appends = bool(valid_horizon and isinstance(latest_seq, int) and latest_seq > as_of_seq)
    state_changed_without_append = bool(chain_state and (
        not latest_state
        or not isinstance(latest_seq, int)
        or latest_seq < as_of_seq
        or (latest_seq == as_of_seq and latest_state.get("last_hash") != chain_state.get("last_hash"))
    )) if valid_horizon else bool(chain_state)
    if state_changed_without_append:
        breaks.append({"seq": as_of_seq, "id": None, "reason": "chain_state_changed_without_append"})
    # No commitment at scan start: do not turn an advancing genesis or invalid
    # state into a clean empty-chain result. A later request can inspect it.
    degraded = bool(not valid_horizon and (chain_state or latest_state or rows or chained_without_commitment))

    if invalid_sequences:
        breaks.append({"seq": None, "id": None, "reason": "invalid_sequence_records", "count": invalid_sequences})

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
        "ok": len(breaks) == 0 and not degraded,
        "checked": checked,
        "breaks": breaks,
        "last_seq": last_seq,
        "unverifiable": unverifiable,
        "legacy_skipped": legacy_skipped,
        "truncated": truncated,
        "as_of_seq": as_of_seq,
        "observed_latest_seq": latest_seq,
        "concurrent_appends": concurrent_appends,
        "verification_scope": "sequence_prefix" if valid_horizon else "no_start_commitment",
        "degraded": degraded,
        "retryable": degraded,
    }

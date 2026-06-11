"""Search-normalize companion-field indexes + one-shot idempotent backfill.

Wires the ``<field>_lower`` companion fields (see
``security/search_normalize.py``) into the database:

* ``ensure_search_normalize_indexes`` — idempotent compound indexes
  ``(<leading_key>, <field>_lower)`` (tenant_id-leading where tenant-scoped).
* ``backfill_search_normalize_fields`` — populates the companion fields on
  existing rows. Marker-gated via ``search_normalize_backfill`` so it runs once
  per collection (per version) and is a cheap no-op on subsequent startups.

Both are PII-safe: they only touch the plaintext fields configured in
``NORMALIZED_SEARCH_FIELDS`` (never an encrypted field).
"""
from __future__ import annotations

import logging

from pymongo import UpdateOne

from security.search_normalize import (
    LEADING_KEY,
    NORMALIZED_SEARCH_FIELDS,
    build_normalized_updates,
    companion_field,
)
from security.search_ngram import (
    NGRAM_LEADING_KEY,
    NGRAM_SOURCE_FIELDS,
    NGRAM_TARGET_FIELD,
    ngram_tokens_for_doc,
)

logger = logging.getLogger(__name__)

# Bump when the field set in NORMALIZED_SEARCH_FIELDS changes so the backfill
# re-runs to populate newly-added companion fields.
_BACKFILL_VERSION = 1
_PROGRESS_COLLECTION = "search_normalize_backfill"
_BATCH = 500


async def ensure_search_normalize_indexes(raw_db) -> list[str]:
    """Create the compound companion-field indexes. Idempotent.

    Returns the list of index names that were (re)requested.
    """
    created: list[str] = []
    for collection, fields in NORMALIZED_SEARCH_FIELDS.items():
        leading = LEADING_KEY.get(collection, "tenant_id")
        for field in fields:
            companion = companion_field(field)
            # Stable, descriptive name; dotted paths -> underscores.
            name = f"sn_{leading}_{companion.replace('.', '_')}"
            try:
                await raw_db[collection].create_index(
                    [(leading, 1), (companion, 1)], name=name, background=True
                )
                created.append(f"{collection}.{name}")
            except Exception as e:  # pragma: no cover - defensive
                logger.warning(
                    "search-normalize index %s on %s failed: %s",
                    name, collection, e,
                )
    return created


async def _backfill_collection(raw_db, collection: str, fields: list[str]) -> int:
    coll = raw_db[collection]
    # Only visit docs missing at least one companion field (one-time scan; cheap
    # no-op once complete because the match set becomes empty).
    missing_filter = {
        "$or": [{companion_field(f): {"$exists": False}} for f in fields]
    }
    projection = {"_id": 1}
    for f in fields:
        # project the source path so we can normalize without a 2nd read
        projection[f.split(".")[0]] = 1

    updated = 0
    ops: list[UpdateOne] = []
    cursor = coll.find(missing_filter, projection)
    async for doc in cursor:
        sets = build_normalized_updates(doc, fields)
        if not sets:
            continue
        ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": sets}))
        if len(ops) >= _BATCH:
            res = await coll.bulk_write(ops, ordered=False)
            updated += res.modified_count
            ops = []
    if ops:
        res = await coll.bulk_write(ops, ordered=False)
        updated += res.modified_count
    return updated


async def backfill_search_normalize_fields(raw_db) -> dict[str, int]:
    """Marker-gated, idempotent backfill of companion fields on existing rows.

    Returns ``{collection: rows_updated}`` for collections that ran this call.
    """
    progress = raw_db[_PROGRESS_COLLECTION]
    ran: dict[str, int] = {}
    for collection, fields in NORMALIZED_SEARCH_FIELDS.items():
        marker_id = f"{collection}:v{_BACKFILL_VERSION}"
        if await progress.find_one({"_id": marker_id, "done": True}):
            continue
        try:
            updated = await _backfill_collection(raw_db, collection, fields)
            await progress.update_one(
                {"_id": marker_id},
                {"$set": {"done": True, "updated": updated}},
                upsert=True,
            )
            ran[collection] = updated
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "search-normalize backfill for %s failed: %s", collection, e
            )
    return ran


# ── Trigram infix-search companions (`_ng_<target>`) ──────────────────────────
# Mirrors the prefix-companion index/backfill above for the INFIX (substring)
# trigram field. PII-safe: only PLAINTEXT name fields, raw (un-hashed) tokens.

_NGRAM_BACKFILL_VERSION = 1
_NGRAM_PROGRESS_COLLECTION = "ngram_backfill"


def ngram_index_name(collection: str) -> str:
    leading = NGRAM_LEADING_KEY.get(collection, "tenant_id")
    target = NGRAM_TARGET_FIELD[collection].lstrip("_")
    return f"ng_{leading}_{target}"


async def ensure_ngram_indexes(raw_db) -> list[str]:
    """Create the ``(<leading>, _ng_<target>)`` multikey indexes. Idempotent."""
    created: list[str] = []
    for collection in NGRAM_TARGET_FIELD:
        leading = NGRAM_LEADING_KEY.get(collection, "tenant_id")
        target = NGRAM_TARGET_FIELD[collection]
        name = ngram_index_name(collection)
        try:
            await raw_db[collection].create_index(
                [(leading, 1), (target, 1)], name=name, background=True
            )
            created.append(f"{collection}.{name}")
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "ngram index %s on %s failed: %s", name, collection, e
            )
    return created


async def _backfill_ngram_collection(
    raw_db, collection: str, source_fields: list[str]
) -> int:
    coll = raw_db[collection]
    target = NGRAM_TARGET_FIELD[collection]
    missing_filter = {target: {"$exists": False}}
    projection = {"_id": 1}
    for f in source_fields:
        projection[f] = 1

    updated = 0
    ops: list[UpdateOne] = []
    cursor = coll.find(missing_filter, projection)
    async for doc in cursor:
        tokens = ngram_tokens_for_doc(doc, collection)
        if not tokens:
            continue
        ops.append(UpdateOne({"_id": doc["_id"]}, {"$set": {target: tokens}}))
        if len(ops) >= _BATCH:
            res = await coll.bulk_write(ops, ordered=False)
            updated += res.modified_count
            ops = []
    if ops:
        res = await coll.bulk_write(ops, ordered=False)
        updated += res.modified_count
    return updated


async def backfill_ngram_fields(raw_db) -> dict[str, int]:
    """Marker-gated, idempotent backfill of trigram companions on existing rows."""
    progress = raw_db[_NGRAM_PROGRESS_COLLECTION]
    ran: dict[str, int] = {}
    for collection, source_fields in NGRAM_SOURCE_FIELDS.items():
        marker_id = f"{collection}:v{_NGRAM_BACKFILL_VERSION}"
        if await progress.find_one({"_id": marker_id, "done": True}):
            continue
        try:
            updated = await _backfill_ngram_collection(
                raw_db, collection, source_fields
            )
            await progress.update_one(
                {"_id": marker_id},
                {"$set": {"done": True, "updated": updated}},
                upsert=True,
            )
            ran[collection] = updated
        except Exception as e:  # pragma: no cover - defensive
            logger.warning(
                "ngram backfill for %s failed: %s", collection, e
            )
    return ran

"""Ortak idempotency helper'ı + DB seviyesinde atomic guard.

Mongo unique partial index'i ile `(tenant_id, idempotency_key)` çiftinde
çift insert engellenir; race condition'da ikinci insert DuplicateKeyError
fırlatır ve mevcut doküman idempotent flag ile döndürülür.
"""
from __future__ import annotations

import logging
from typing import Any

from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)

_INDEXES_READY: set[str] = set()


async def ensure_idem_index(collection, index_name: str | None = None) -> None:
    """Lazy-create a unique partial index on (tenant_id, idempotency_key).

    Fail-closed: a failed create_index does **not** mark the collection as
    ready, so the next request retries. If the index is genuinely
    unavailable (e.g. cluster lost permission), the atomicity guarantee is
    broken — callers can detect this by `is_idem_index_ready(collection)`.
    """
    key = f"{collection.name}::idem"
    if key in _INDEXES_READY:
        return
    try:
        await collection.create_index(
            [("tenant_id", 1), ("idempotency_key", 1)],
            unique=True,
            partialFilterExpression={"idempotency_key": {"$type": "string"}},
            name=index_name or f"{collection.name}_idem_unique",
        )
        _INDEXES_READY.add(key)
    except Exception as exc:
        # Common idempotent case: index already exists with same/different opts.
        msg = str(exc).lower()
        if "already exists" in msg or "indexoptionsconflict" in msg or "exists with different options" in msg:
            _INDEXES_READY.add(key)
            return
        # Otherwise: do NOT cache — next call retries. Surface a warning so
        # ops can see degraded atomicity.
        logger.warning(
            f"idem index ensure FAILED on {collection.name}: {exc!r} — "
            f"atomic idempotency guarantee weakened; will retry on next request."
        )
        raise


def is_idem_index_ready(collection) -> bool:
    """Return True when the unique idempotency index has been confirmed present."""
    return f"{collection.name}::idem" in _INDEXES_READY


async def idempotent_insert(
    collection,
    tenant_id: str,
    idempotency_key: str | None,
    doc: dict,
    index_name: str | None = None,
) -> tuple[dict, bool]:
    """Insert `doc` or return prior row if `idempotency_key` already used.

    Returns (effective_doc, was_idempotent_replay).

    `index_name` lets a caller reuse an existing (tenant_id, idempotency_key)
    index by name (e.g. the POS `ux_pos_orders_tenant_idemp` index shared with
    create-order), avoiding an equivalent-index-different-name conflict.

    If the unique index cannot be created (DB perms/transient), the request
    fails closed with the underlying error rather than silently degrading
    atomicity — callers must surface this to the operator instead of
    accepting non-idempotent writes.
    """
    if not idempotency_key:
        await collection.insert_one(doc)
        doc.pop("_id", None)
        return doc, False

    await ensure_idem_index(collection, index_name=index_name)  # may raise → fail-closed
    try:
        await collection.insert_one(doc)
        doc.pop("_id", None)
        return doc, False
    except DuplicateKeyError:
        prior = await collection.find_one(
            {"tenant_id": tenant_id, "idempotency_key": idempotency_key},
            {"_id": 0},
        )
        return prior or doc, True


async def ensure_compound_unique(
    collection,
    keys: list[tuple[str, int]],
    partial_filter: dict | None = None,
    name: str | None = None,
) -> None:
    """Generic helper for other compound unique indexes (e.g. open-shift).

    Fail-closed on real errors; tolerant only of "already exists" variants.
    """
    cache_key = f"{collection.name}::{name or '_'.join(k for k, _ in keys)}"
    if cache_key in _INDEXES_READY:
        return
    try:
        kwargs: dict[str, Any] = {"unique": True, "name": name or f"{collection.name}_unique"}
        if partial_filter:
            kwargs["partialFilterExpression"] = partial_filter
        await collection.create_index(keys, **kwargs)
        _INDEXES_READY.add(cache_key)
    except Exception as exc:
        msg = str(exc).lower()
        if "already exists" in msg or "indexoptionsconflict" in msg or "exists with different options" in msg:
            _INDEXES_READY.add(cache_key)
            return
        logger.warning(
            f"compound unique index ensure FAILED on {collection.name} (keys={keys}): {exc!r} — "
            f"atomicity guarantee weakened; will retry on next request."
        )
        raise

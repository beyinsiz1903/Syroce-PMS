"""
Normalized lowercase search companion fields for index-serviceable prefix search.

Problem
-------
Search-box endpoints historically query MongoDB with an unanchored
case-insensitive regex (``{"$regex": term, "$options": "i"}``) on plaintext
fields. A btree index cannot serve that shape, so each search scans the whole
tenant slice of the collection. Under load this spikes the Atlas
"Query Targeting: Scanned Objects / Returned > 1000" alert.

Fix
---
On create/update we write a normalized lowercase companion field
(``<field>_lower``) for each plaintext search field. The common "starts typing
a name" search is then served as an anchored, case-SENSITIVE prefix **range**
query against the companion field — which the planner serves with an IXSCAN on a
``(<leading_key>, <field>_lower)`` compound index (tenant_id-leading where the
collection is tenant-scoped).

A prefix *range* (``{"$gte": p, "$lt": p<next>}``) is used rather than an
anchored ``^regex`` so the planner is guaranteed to use the index bounds with no
dependence on regex prefix-optimization heuristics.

Security
--------
This is for PLAINTEXT search fields only. Encrypted-PII fields (guest/user
email, phone, id_number, passport, …) must NOT get a lowercase plaintext copy —
that would re-expose the plaintext we encrypted. Those keep the existing
deterministic ``_hash_<field>`` blind-index exact-match path. None of the
fields configured here are encrypted.
"""
from __future__ import annotations

import unicodedata

# Collection → plaintext search fields that get a `<field>_lower` companion.
# Dotted paths (e.g. "contact.full_name") are supported for nested documents.
# IMPORTANT: never list an ENCRYPTED field here (see module docstring).
NORMALIZED_SEARCH_FIELDS: dict[str, list[str]] = {
    "bookings": ["guest_name", "booking_number"],
    "guests": ["name", "first_name", "last_name"],
    "mice_accounts": ["name", "legal_name", "tax_no"],
    "mice_opportunities": ["contact_name", "company_name", "contact_email"],
    "leads": [
        "contact.full_name",
        "contact.phone",
        "contact.email",
        "hotel.property_name",
        "hotel.location",
    ],
}

# Leading equality predicate per collection. Tenant-scoped collections lead with
# tenant_id (preserves tenant isolation in the index). `leads` (PMS-Lite landing
# marketing leads) is NOT tenant-scoped — it is a global, super-admin-only
# dataset filtered by `source` — so its index leads with `source`.
LEADING_KEY: dict[str, str] = {
    "bookings": "tenant_id",
    "guests": "tenant_id",
    "mice_accounts": "tenant_id",
    "mice_opportunities": "tenant_id",
    "leads": "source",
}

# Bound the stored/queried prefix length to keep index keys small.
_MAX_LEN = 256


def companion_field(field: str) -> str:
    """`name` -> `name_lower`; `contact.full_name` -> `contact.full_name_lower`."""
    return f"{field}_lower"


def normalize_search_value(value) -> str | None:
    """NFKC-normalize, strip and lowercase a value for storage/matching.

    Returns None for empty / whitespace-only input. Mirrors the
    strip()+lower() normalization used by the encrypted-field search hash so the
    two conventions stay consistent.
    """
    if value is None:
        return None
    s = unicodedata.normalize("NFKC", str(value)).strip().lower()
    if not s:
        return None
    return s[:_MAX_LEN]


def _dotted_get(doc: dict, path: str):
    cur = doc
    for part in path.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _dotted_set(doc: dict, path: str, value) -> None:
    parts = path.split(".")
    cur = doc
    for part in parts[:-1]:
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    cur[parts[-1]] = value


def build_normalized_updates(source: dict, fields: list[str]) -> dict:
    """Return a FLAT ``{companion_dotted_key: normalized_value}`` map.

    Only includes fields that are present and non-empty in ``source``. Suitable
    for merging into a Mongo ``$set`` document (dotted keys are fine there).
    """
    out: dict = {}
    for field in fields:
        norm = normalize_search_value(_dotted_get(source, field))
        if norm is not None:
            out[companion_field(field)] = norm
    return out


def apply_normalized_fields(doc: dict, fields: list[str]) -> dict:
    """Mutate ``doc`` in place, writing companion fields (handles nesting).

    Returns the same ``doc`` for convenience. Use on insert documents.
    """
    for key, value in build_normalized_updates(doc, fields).items():
        _dotted_set(doc, key, value)
    return doc


def apply_collection_normalized_fields(doc: dict, *, collection: str) -> dict:
    """Convenience wrapper: normalize a doc using the configured field list.

    Also writes the trigram infix-search companion (``_ng_<target>``) for
    collections configured in ``search_ngram`` — folded in here so every writer
    already producing ``<field>_lower`` gets infix tokens for free (no-op for
    collections without ngram config).
    """
    fields = NORMALIZED_SEARCH_FIELDS.get(collection)
    if fields:
        apply_normalized_fields(doc, fields)
    # Trigram infix companion (plaintext names only; raw, un-hashed tokens).
    from security.search_ngram import apply_ngram_fields
    apply_ngram_fields(doc, collection=collection)
    return doc


def normalized_set_for_update(update_source: dict, *, collection: str) -> dict:
    """Companion ``$set`` entries for fields present in an update payload.

    Pass the (already-allowlisted) fields the caller is about to ``$set``; only
    those that are configured search fields produce companion updates. Trigram
    infix tokens (``_ng_<target>``) are recomputed alongside the ``<field>_lower``
    companions when a name field is part of the update.
    """
    out: dict = {}
    fields = NORMALIZED_SEARCH_FIELDS.get(collection)
    if fields:
        out.update(build_normalized_updates(update_source, fields))
    from security.search_ngram import ngram_set_for_update
    out.update(ngram_set_for_update(update_source, collection=collection))
    return out


def _prefix_upper_bound(prefix: str) -> str:
    """Exclusive upper bound for a prefix range scan.

    "ali" -> "alj" (matches every string starting with "ali"). For the rare
    case the last char is the max code point, append the max code point so the
    bound still excludes nothing legitimate.
    """
    last = prefix[-1]
    if last == "\U0010ffff":
        return prefix + "\U0010ffff"
    return prefix[:-1] + chr(ord(last) + 1)


def prefix_condition(field: str, raw_value: str) -> dict | None:
    """Index-serviceable anchored prefix match on one companion field.

    Returns ``{<field>_lower: {"$gte": p, "$lt": p<next>}}`` or None when the
    value normalizes to empty.
    """
    norm = normalize_search_value(raw_value)
    if norm is None:
        return None
    return {companion_field(field): {"$gte": norm, "$lt": _prefix_upper_bound(norm)}}


def prefix_conditions(fields: list[str], raw_value: str) -> list[dict]:
    """List of per-field prefix conditions for an ``$or`` query.

    Empty list when the value normalizes to empty (caller should then skip
    adding the search filter rather than match everything).
    """
    norm = normalize_search_value(raw_value)
    if norm is None:
        return []
    upper = _prefix_upper_bound(norm)
    return [
        {companion_field(field): {"$gte": norm, "$lt": upper}} for field in fields
    ]

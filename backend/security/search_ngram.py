"""Trigram (n-gram) INFIX search companions for PLAINTEXT name fields.

Problem
-------
``search_normalize.py`` gives index-serviceable PREFIX search on plaintext name
fields via ``<field>_lower`` (anchored ``$gte``/``$lt`` range). That serves
"starts typing a name" but NOT infix/substring: typing the middle of a name
("ladi" in "Vladimir") or a surname when the record stores "First Last" matches
nothing, forcing front-desk staff to re-key a guest who is already on file.

Fix
---
On create/update we tokenize the plaintext name fields into overlapping 3-char
groups (trigrams), dedupe, and store them as ONE multikey array field
``_ng_<target>`` (e.g. ``_ng_name``). A substring query of length >= 3 is then
served as an index-serviceable ``{_ng_name: {"$all": [trigrams(q)]}}`` against a
``(tenant_id, _ng_name)`` multikey index. Because trigram ``$all`` can
over-match (it ignores adjacency / word order), the caller MUST re-verify each
candidate with a plain substring check (``ngram_match``) before returning it.

Security
--------
This module is for PLAINTEXT name fields ONLY. Trigrams are stored RAW (NOT
hashed): the source name is already plaintext in the same document and already
has a ``<field>_lower`` companion, so raw trigrams expose nothing new while
keeping the multikey index keys small (3 chars vs a 64-hex HMAC). NEVER
configure an ENCRYPTED field here — storing trigrams of encrypted PII
(email / id_number / passport / iban) is a real confidentiality downgrade
(trigram frequency / co-occurrence analysis partially reconstructs values, and
for low-entropy structured fields it is effectively recoverable). That is an
opt-in, separately-flagged phase, out of scope for this module by design.
"""
from __future__ import annotations

import unicodedata

# collection -> plaintext source fields combined into ONE `_ng_<target>` field.
NGRAM_SOURCE_FIELDS: dict[str, list[str]] = {
    "guests": ["name", "first_name", "last_name"],
}

# collection -> the single combined multikey token field.
NGRAM_TARGET_FIELD: dict[str, str] = {
    "guests": "_ng_name",
}

# Leading key for the (leading, target) multikey index (tenant-scoped).
NGRAM_LEADING_KEY: dict[str, str] = {
    "guests": "tenant_id",
}

NGRAM_SIZE = 3
_MAX_WORD_LEN = 64       # cap per-word length before tokenizing (DoS guard)
_MAX_DOC_TOKENS = 96     # cap trigrams stored per document (write/index amp)
_MAX_QUERY_TOKENS = 64   # cap trigrams in a single query's $all


def normalize_ngram_value(value) -> str | None:
    """Normalizer used IDENTICALLY at store, query and re-verify time.

    NFKC (fold fullwidth / compatibility forms) + casefold (cross-script
    case-insensitivity for Russian/Greek/etc.) + a second NFKC to settle any
    combining marks casefold introduced. Returns ``None`` for empty/blank.

    The exact same function MUST be used everywhere or stored tokens and query
    tokens silently never match.
    """
    if value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    s = unicodedata.normalize("NFKC", value).casefold()
    s = unicodedata.normalize("NFKC", s).strip()
    return s or None


def _word_trigrams(word: str) -> set[str]:
    word = word[:_MAX_WORD_LEN]
    if len(word) < NGRAM_SIZE:
        return set()
    return {word[i:i + NGRAM_SIZE] for i in range(len(word) - NGRAM_SIZE + 1)}


def trigrams(text) -> list[str]:
    """Per-word trigrams of ``text``, deduped + capped. Empty if no word >= 3."""
    norm = normalize_ngram_value(text)
    if not norm:
        return []
    out: set[str] = set()
    for word in norm.split():
        out |= _word_trigrams(word)
        if len(out) >= _MAX_DOC_TOKENS:
            break
    return sorted(out)[:_MAX_DOC_TOKENS]


def ngram_tokens_for_doc(source: dict, collection: str) -> list[str] | None:
    """Combined trigram list for a doc's configured name fields, or ``None``."""
    src_fields = NGRAM_SOURCE_FIELDS.get(collection)
    if not src_fields or not isinstance(source, dict):
        return None
    parts: list[str] = []
    for f in src_fields:
        v = source.get(f)
        if isinstance(v, str) and v.strip():
            parts.append(v)
    if not parts:
        return None
    toks = trigrams(" ".join(parts))
    return toks or None


def apply_ngram_fields(doc: dict, *, collection: str) -> dict:
    """Write the ``_ng_<target>`` multikey field on ``doc`` in place.

    No-op for collections not configured for ngram search.
    """
    target = NGRAM_TARGET_FIELD.get(collection)
    if not target or not isinstance(doc, dict):
        return doc
    toks = ngram_tokens_for_doc(doc, collection)
    if toks:
        doc[target] = toks
    return doc


def ngram_set_for_update(update_source: dict, *, collection: str) -> dict:
    """``$set`` fragment recomputing the token field when a name field changes.

    Returns ``{}`` if this collection isn't configured or no source field is
    present in the update (so unrelated updates don't touch the token field).
    """
    target = NGRAM_TARGET_FIELD.get(collection)
    if not target or not isinstance(update_source, dict):
        return {}
    src_fields = NGRAM_SOURCE_FIELDS.get(collection, [])
    if not any(f in update_source for f in src_fields):
        return {}
    toks = ngram_tokens_for_doc(update_source, collection)
    return {target: toks} if toks else {}


def ngram_set_for_update_merged(
    existing_doc, update_source: dict, *, collection: str
) -> dict:
    """``$set`` fragment recomputing the COMBINED token field from MERGED names.

    ``ngram_set_for_update`` sees only the update payload, so a partial rename
    that touches one source field (e.g. ``name``) would silently drop the
    trigrams of the untouched source fields (``first_name``/``last_name``),
    making the guest no longer infix-findable by surname. Pass the stored doc
    (whose name fields are plaintext) plus the update so the combined token
    field stays complete.

    Returns ``{}`` when the collection isn't configured or the update touches
    no source field (so unrelated updates don't rewrite the token field).
    """
    target = NGRAM_TARGET_FIELD.get(collection)
    if not target or not isinstance(update_source, dict):
        return {}
    src_fields = NGRAM_SOURCE_FIELDS.get(collection, [])
    if not any(f in update_source for f in src_fields):
        return {}
    merged: dict = {}
    if isinstance(existing_doc, dict):
        for f in src_fields:
            v = existing_doc.get(f)
            if v is not None:
                merged[f] = v
    for f in src_fields:
        if f in update_source:
            merged[f] = update_source[f]
    toks = ngram_tokens_for_doc(merged, collection)
    return {target: toks} if toks else {}


def ngram_all_condition(q, *, collection: str) -> dict | None:
    """Index-serviceable infix condition ``{target: {"$all": trigrams(q)}}``.

    Returns ``None`` when the collection isn't configured or the (normalized)
    query has no word of length >= ``NGRAM_SIZE`` — the caller then falls back
    to the existing prefix/exact path (which handles 1-2 char queries).
    """
    target = NGRAM_TARGET_FIELD.get(collection)
    if not target:
        return None
    toks = trigrams(q)
    if not toks:
        return None
    return {target: {"$all": toks[:_MAX_QUERY_TOKENS]}}


def ngram_match(doc: dict, q, *, collection: str) -> bool:
    """Post-fetch exact substring re-verify (trigram ``$all`` over-matches).

    Returns ``True`` only if the normalized query is a CONTIGUOUS substring of a
    configured name field (or the joined "name first last" form). This is what
    makes trigram search safe on plaintext: we never return a guest whose name
    does not actually contain what was typed.
    """
    src_fields = NGRAM_SOURCE_FIELDS.get(collection)
    if not src_fields or not isinstance(doc, dict):
        return True
    nq = normalize_ngram_value(q)
    if not nq:
        return True
    parts: list[str] = []
    for f in src_fields:
        v = doc.get(f)
        if isinstance(v, str) and v.strip():
            nv = normalize_ngram_value(v) or ""
            if nq in nv:
                return True
            parts.append(nv)
    return nq in " ".join(parts)


def strip_ngram_fields(doc: dict) -> dict:
    """Drop the internal token field(s) from a doc before returning it."""
    if isinstance(doc, dict):
        for target in set(NGRAM_TARGET_FIELD.values()):
            doc.pop(target, None)
    return doc

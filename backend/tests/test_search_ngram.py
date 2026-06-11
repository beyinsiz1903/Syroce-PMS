"""Unit tests for the trigram (n-gram) INFIX search helper.

Pins the contract behind partial/substring guest-name search:
  * The SAME NFKC+casefold normalizer is used at store, query and re-verify time
    (multi-script: Latin / Cyrillic / Arabic / Turkish), or stored and query
    tokens silently never match.
  * A query shorter than the trigram size yields NO condition (caller falls back
    to the prefix path) — never a match-everything query.
  * Trigram `$all` over-matches, so `ngram_match` re-verifies a CONTIGUOUS
    substring before a candidate is returned.
  * The `(tenant_id, _ng_name)` multikey index is created as configured.
  * Trigrams are PLAINTEXT-NAME ONLY: no encrypted-PII field is ever configured
    for trigram tokenization (that would be a KVKK confidentiality downgrade).
"""
from __future__ import annotations

import asyncio

from security.search_ngram import (
    NGRAM_SIZE,
    NGRAM_SOURCE_FIELDS,
    NGRAM_TARGET_FIELD,
    apply_ngram_fields,
    ngram_all_condition,
    ngram_match,
    ngram_set_for_update,
    ngram_set_for_update_merged,
    ngram_tokens_for_doc,
    normalize_ngram_value,
    strip_ngram_fields,
    trigrams,
)


# ── Normalizer ────────────────────────────────────────────────────────────────


def test_normalize_value_nfkc_casefold_strip():
    assert normalize_ngram_value("  Vladimir  ") == "vladimir"
    # NFKC folds fullwidth so the normalize-bypass trick can't dodge it.
    assert normalize_ngram_value("ＶＬＡＤ") == "vlad"
    # casefold handles non-Latin case (Cyrillic В/в).
    assert normalize_ngram_value("ВЛАД") == normalize_ngram_value("влад")
    assert normalize_ngram_value("") is None
    assert normalize_ngram_value("   ") is None
    assert normalize_ngram_value(None) is None


# ── Tokenizer (multi-script) ──────────────────────────────────────────────────


def test_trigrams_latin_overlapping_and_deduped():
    toks = trigrams("Vladimir")
    assert "vla" in toks and "lad" in toks and "mir" in toks
    # Overlapping windows: len-2 trigrams for an 8-char word.
    assert len(toks) == len("vladimir") - NGRAM_SIZE + 1
    # Deduped + sorted (deterministic for index/backfill).
    assert toks == sorted(set(toks))


def test_trigrams_multiscript_nonempty_and_consistent():
    # Cyrillic, Arabic and Turkish all tokenize (non-empty for >=3 letters).
    assert trigrams("Владимир")
    assert trigrams("محمود")
    assert trigrams("Çağrı")
    # Same value, different case -> identical tokens (store == query).
    assert trigrams("ВЛАДИМИР") == trigrams("владимир")


def test_trigrams_short_word_yields_nothing():
    assert trigrams("Vl") == []
    assert trigrams("") == []
    assert trigrams(None) == []


def test_trigrams_per_word_no_cross_word_tokens():
    # Trigrams are per-word: no token spans the space between words.
    toks = trigrams("Ivan Vladimirov")
    assert "n v" not in toks and "n v".replace(" ", "") not in toks
    assert "iva" in toks and "vla" in toks


# ── Doc token application ────────────────────────────────────────────────────


def test_apply_ngram_fields_combines_name_fields():
    doc = {"first_name": "Ivan", "last_name": "Vladimirov"}
    apply_ngram_fields(doc, collection="guests")
    target = NGRAM_TARGET_FIELD["guests"]
    assert "vla" in doc[target] and "iva" in doc[target]
    # Original plaintext untouched.
    assert doc["first_name"] == "Ivan"


def test_apply_ngram_fields_noop_for_unconfigured_collection():
    doc = {"name": "Whatever"}
    apply_ngram_fields(doc, collection="rooms")
    assert "_ng_name" not in doc


def test_ngram_tokens_for_doc_none_when_no_source():
    assert ngram_tokens_for_doc({"unrelated": "x"}, "guests") is None
    assert ngram_tokens_for_doc({"name": "Ab"}, "guests") is None  # too short


def test_ngram_set_for_update_only_when_name_changes():
    sets = ngram_set_for_update({"name": "Vladimir"}, collection="guests")
    assert "vla" in sets[NGRAM_TARGET_FIELD["guests"]]
    # An update that touches no configured name field leaves tokens alone.
    assert ngram_set_for_update({"phone": "+90..."}, collection="guests") == {}
    assert ngram_set_for_update({"name": "X"}, collection="rooms") == {}


def test_ngram_set_for_update_merged_preserves_other_name_fields():
    # A guest stored with split first/last names is renamed via a path that only
    # carries `name`. The naive per-payload recompute would drop first/last-name
    # trigrams; the merged variant must keep the surname infix-findable.
    stored = {"first_name": "Ivan", "last_name": "Vladimirov"}
    target = NGRAM_TARGET_FIELD["guests"]

    naive = ngram_set_for_update({"name": "Ivan V."}, collection="guests")
    assert "lad" not in naive[target]  # surname trigram lost — the bug

    merged = ngram_set_for_update_merged(
        stored, {"name": "Ivan V."}, collection="guests")
    toks = merged[target]
    assert "lad" in toks and "imi" in toks  # surname trigrams preserved
    assert "iva" in toks                      # changed field included too

    # No source field in the update → token field is left untouched.
    assert ngram_set_for_update_merged(
        stored, {"phone": "+90..."}, collection="guests") == {}
    # Unconfigured collection is a no-op.
    assert ngram_set_for_update_merged(
        stored, {"name": "X"}, collection="rooms") == {}


# ── Query condition thresholds ───────────────────────────────────────────────


def test_ngram_all_condition_none_below_trigram_size():
    # 1-2 char queries fall through to the prefix path (no infix condition).
    assert ngram_all_condition("V", collection="guests") is None
    assert ngram_all_condition("Vl", collection="guests") is None
    assert ngram_all_condition("   ", collection="guests") is None


def test_ngram_all_condition_builds_all_query():
    cond = ngram_all_condition("Vladi", collection="guests")
    target = NGRAM_TARGET_FIELD["guests"]
    assert set(cond[target]["$all"]) == {"vla", "lad", "adi"}
    # Index-served shape: $all over the multikey token field, never a regex.
    assert "$regex" not in cond[target]


def test_ngram_all_condition_none_for_unconfigured_collection():
    assert ngram_all_condition("Vladi", collection="rooms") is None


# ── Re-verify (over-match suppression) ───────────────────────────────────────


def test_ngram_match_accepts_real_substring():
    doc = {"first_name": "Ivan", "last_name": "Vladimirov"}
    assert ngram_match(doc, "ladi", collection="guests") is True
    assert ngram_match(doc, "Vladimir", collection="guests") is True


def test_ngram_match_rejects_trigram_over_match():
    # "imi" + "mir" trigrams of "imir" both exist across the two words, so a
    # raw $all would match — but "imir" is NOT a contiguous substring, so the
    # re-verify must reject it.
    doc = {"first_name": "Imi", "last_name": "Mir"}
    cond = ngram_all_condition("imir", collection="guests")
    target = NGRAM_TARGET_FIELD["guests"]
    apply_ngram_fields(doc, collection="guests")
    # The stored tokens DO satisfy $all (this is the over-match)...
    assert set(cond[target]["$all"]).issubset(set(doc[target]))
    # ...but the contiguous re-verify rejects the candidate.
    assert ngram_match(doc, "imir", collection="guests") is False


def test_ngram_match_empty_query_is_permissive():
    # Empty/blank query never narrows (caller guards length separately).
    assert ngram_match({"name": "X"}, "", collection="guests") is True


# ── Response hygiene ─────────────────────────────────────────────────────────


def test_strip_ngram_fields_removes_token_array():
    doc = {"id": "g1", "name": "Vladimir", "_ng_name": ["vla"]}
    strip_ngram_fields(doc)
    assert "_ng_name" not in doc
    assert doc["name"] == "Vladimir"


# ── Security guard: never trigram an encrypted field ─────────────────────────


def test_no_encrypted_pii_field_is_trigrammed():
    """Trigrams must only ever cover PLAINTEXT name fields."""
    try:
        from security.field_encryption import ENCRYPTED_FIELDS
    except Exception:  # pragma: no cover
        import pytest

        pytest.skip("field_encryption ENCRYPTED_FIELDS not importable")
    for collection, fields in NGRAM_SOURCE_FIELDS.items():
        encrypted = {f["field"] for f in ENCRYPTED_FIELDS.get(collection, [])}
        for field in fields:
            assert field not in encrypted, (
                f"{collection}.{field} is encrypted — trigramming it would be a "
                f"KVKK confidentiality downgrade"
            )


def test_identity_fields_never_trigrammed():
    """Hard pin: id_number / passport / iban / email are never tokenized."""
    forbidden = {"id_number", "passport_number", "iban", "email", "phone"}
    for fields in NGRAM_SOURCE_FIELDS.values():
        assert not (set(fields) & forbidden)


def test_target_fields_are_internal_underscore_prefixed():
    for target in NGRAM_TARGET_FIELD.values():
        assert target.startswith("_ng_")


# ── Fold into the shared normalize helpers (coverage path) ───────────────────


def test_collection_normalize_also_writes_ngram_tokens():
    from security.search_normalize import (
        apply_collection_normalized_fields,
        normalized_set_for_update,
    )

    doc = {"name": "Vladimir Putin", "tenant_id": "t1"}
    apply_collection_normalized_fields(doc, collection="guests")
    # Both the prefix companion AND the infix tokens are written in one pass.
    assert doc["name_lower"] == "vladimir putin"
    assert "vla" in doc[NGRAM_TARGET_FIELD["guests"]]

    sets = normalized_set_for_update({"name": "Vladimir"}, collection="guests")
    assert sets["name_lower"] == "vladimir"
    assert "vla" in sets[NGRAM_TARGET_FIELD["guests"]]


# ── Index pin (CI guard for "configured but never created") ──────────────────


class _FakeCollection:
    def __init__(self):
        self._indexes: dict[str, dict] = {"_id_": {"key": [("_id", 1)]}}

    async def create_index(self, keys, *, name=None, background=False, **kwargs):
        key_list = [(keys, 1)] if isinstance(keys, str) else list(keys)
        idx_name = name or "_".join(f"{k}_{d}" for k, d in key_list)
        self._indexes[idx_name] = {"key": key_list}
        return idx_name

    async def index_information(self):
        return dict(self._indexes)


class _FakeDB:
    def __init__(self):
        self._cols: dict[str, _FakeCollection] = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, _FakeCollection())


def test_ensure_ngram_indexes_creates_expected_index():
    from bootstrap.phases.search_normalize import (
        ensure_ngram_indexes,
        ngram_index_name,
    )

    db = _FakeDB()
    created = asyncio.run(ensure_ngram_indexes(db))
    for collection, target in NGRAM_TARGET_FIELD.items():
        name = ngram_index_name(collection)
        assert f"{collection}.{name}" in created
        info = asyncio.run(db[collection].index_information())
        assert name in info
        assert info[name]["key"] == [("tenant_id", 1), (target, 1)]

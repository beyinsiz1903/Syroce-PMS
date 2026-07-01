"""Unit tests for the plaintext search-box normalization helper.

Pins the contract that drove the Atlas query-targeting fix:
  * Search-box queries match against `<field>_lower` companion fields using an
    anchored, index-serviceable prefix RANGE ($gte/$lt) — never an unanchored
    `$options: "i"` regex.
  * Companion fields are written (incl. nested/dotted paths) on create/update.
  * Encrypted-PII fields keep the `_hash_<field>` blind-index path and never get
    a lowercase plaintext copy.
"""
from __future__ import annotations

from security.search_normalize import (
    NORMALIZED_SEARCH_FIELDS,
    apply_collection_normalized_fields,
    apply_normalized_fields,
    build_normalized_updates,
    companion_field,
    normalize_search_value,
    normalized_set_for_update,
    prefix_condition,
    prefix_conditions,
)


def test_normalize_value_nfkc_strip_lower():
    assert normalize_search_value("  Alice  ") == "alice"
    # NFKC folds fullwidth chars so the normalize-bypass trick can't dodge it.
    assert normalize_search_value("ＡＬＩＣＥ") == "alice"
    assert normalize_search_value("") is None
    assert normalize_search_value("   ") is None
    assert normalize_search_value(None) is None


def test_companion_field_naming():
    assert companion_field("name") == "name_lower"
    assert companion_field("contact.full_name") == "contact.full_name_lower"


def test_prefix_condition_is_range_not_regex():
    cond = prefix_condition("name", "Ali")
    assert cond == {"name_lower": {"$gte": "ali", "$lt": "alj"}}
    # The whole point: a range, never an unanchored case-insensitive regex.
    assert "$regex" not in cond["name_lower"]
    assert "$options" not in cond["name_lower"]


def test_prefix_range_matches_only_the_prefix():
    cond = prefix_condition("name", "ali")
    lo = cond["name_lower"]["$gte"]
    hi = cond["name_lower"]["$lt"]
    for hit in ("ali", "alice", "alibaba", "ali̇"):
        assert lo <= hit.lower() < hi or hit.lower() == lo
    # Strings that only share a shorter prefix are excluded.
    assert not (lo <= "alj" < hi)
    assert not (lo <= "al" < hi)


def test_prefix_conditions_empty_value_returns_empty():
    # Empty value must yield no conditions so the caller skips the filter
    # rather than matching the whole collection.
    assert prefix_conditions(["name", "legal_name"], "   ") == []
    assert prefix_conditions(["name"], None) == []


def test_prefix_conditions_multi_field_or():
    conds = prefix_conditions(["name", "tax_no"], "AB")
    assert conds == [
        {"name_lower": {"$gte": "ab", "$lt": "ac"}},
        {"tax_no_lower": {"$gte": "ab", "$lt": "ac"}},
    ]


def test_apply_normalized_fields_flat():
    doc = {"name": "Grand Hotel", "tax_no": "1234567890"}
    apply_normalized_fields(doc, ["name", "tax_no"])
    assert doc["name_lower"] == "grand hotel"
    assert doc["tax_no_lower"] == "1234567890"
    # Original plaintext is preserved untouched.
    assert doc["name"] == "Grand Hotel"


def test_apply_normalized_fields_nested_dotted():
    doc = {"contact": {"full_name": "Jane DOE"}, "hotel": {"location": "Izmir"}}
    apply_normalized_fields(
        doc, ["contact.full_name", "hotel.location", "hotel.property_name"])
    assert doc["contact"]["full_name_lower"] == "jane doe"
    assert doc["hotel"]["location_lower"] == "izmir"
    # Missing source path produces no companion.
    assert "property_name_lower" not in doc["hotel"]


def test_apply_collection_normalized_fields_uses_config():
    doc = {"guest_name": "Bob", "booking_number": "BK-7"}
    apply_collection_normalized_fields(doc, collection="bookings")
    assert doc["guest_name_lower"] == "bob"
    assert doc["booking_number_lower"] == "bk-7"


def test_normalized_set_for_update_only_present_fields():
    sets = normalized_set_for_update({"guest_name": "Carol"}, collection="bookings")
    assert sets == {"guest_name_lower": "carol"}
    # Unconfigured collection -> nothing.
    assert normalized_set_for_update({"x": "y"}, collection="rooms") == {}


def test_build_normalized_updates_skips_empty():
    sets = build_normalized_updates(
        {"name": "  ", "legal_name": "ACME"}, ["name", "legal_name"])
    assert sets == {"legal_name_lower": "acme"}


def test_no_encrypted_pii_fields_are_normalized():
    """Guard: never write a lowercase plaintext copy of an encrypted field."""
    try:
        from security.field_encryption import ENCRYPTED_FIELDS
    except Exception:  # pragma: no cover
        import pytest

        pytest.skip("field_encryption ENCRYPTED_FIELDS not importable")
    for collection, fields in NORMALIZED_SEARCH_FIELDS.items():
        encrypted = {f["field"] for f in ENCRYPTED_FIELDS.get(collection, [])}
        for field in fields:
            assert field not in encrypted, (
                f"{collection}.{field} is encrypted — normalizing it would "
                f"re-expose plaintext"
            )


def test_encrypted_guest_search_uses_hash_branch():
    """Step 6: encrypted-PII guest search keeps the `_hash_<field>` path."""
    from security.field_encryption import get_field_encryption_service

    conds = get_field_encryption_service().build_search_query(
        collection="guests", search_fields=["email"], search_value="a@b.com")
    keys = [k for c in conds for k in c]
    assert "_hash_email" in keys, "encrypted guest email must match via hash index"


# ── Encrypted-PII `_hash_` index fail-closed verification (Task 364) ──────────


class _FakeCollection:
    """Minimal async collection that records create_index + reports indexes."""

    def __init__(self):
        self._indexes: dict[str, dict] = {"_id_": {"key": [("_id", 1)]}}

    async def create_index(self, keys, *, name=None, sparse=False, **kwargs):
        key_list = [(keys, 1)] if isinstance(keys, str) else list(keys)
        idx_name = name or "_".join(f"{k}_{d}" for k, d in key_list)
        self._indexes[idx_name] = {"key": key_list, "sparse": sparse}
        return idx_name

    async def index_information(self):
        return dict(self._indexes)


class _FakeDB:
    def __init__(self):
        self._cols: dict[str, _FakeCollection] = {}

    def __getitem__(self, name):
        return self._cols.setdefault(name, _FakeCollection())


def test_expected_hash_indexes_covers_every_searchable_field():
    """`expected_hash_indexes()` must list exactly the searchable encrypted
    fields in ENCRYPTED_FIELDS — adding a searchable field without wiring its
    index breaks this immediately."""
    from security.field_encryption import (
        ENCRYPTED_FIELDS,
        expected_hash_indexes,
        hash_index_key,
        hash_index_name,
    )

    expected = expected_hash_indexes()
    for collection, field_configs in ENCRYPTED_FIELDS.items():
        searchable = {f["field"] for f in field_configs if f.get("searchable")}
        # Every searchable field has an entry; non-searchable fields do not.
        got = expected.get(collection, {})
        assert set(got.keys()) == {hash_index_name(f) for f in searchable}, (
            f"{collection}: expected_hash_indexes drifted from searchable fields"
        )
        for field in searchable:
            assert got[hash_index_name(field)] == hash_index_key(field)


def test_ensure_hash_indexes_creates_exactly_the_expected_indexes():
    """The indexes `ensure_hash_indexes` actually creates must match
    `expected_hash_indexes()` 1:1 — the CI guard for "new searchable field,
    forgotten index"."""
    import asyncio

    from security.field_encryption import (
        expected_hash_indexes,
        get_field_encryption_service,
    )

    db = _FakeDB()
    svc = get_field_encryption_service()
    asyncio.run(svc.ensure_hash_indexes(db))

    expected = expected_hash_indexes()
    for collection, idx_map in expected.items():
        info = asyncio.run(db[collection].index_information())
        created_keys = {
            meta["key"][0][0]
            for name, meta in info.items()
            if name != "_id_"
        }
        assert created_keys == set(idx_map.values()), (
            f"{collection}: ensure_hash_indexes created {created_keys}, "
            f"expected {set(idx_map.values())}"
        )
        # Index names also match the canonical convention.
        for index_name in idx_map:
            assert index_name in info, f"{collection}.{index_name} not created"


def test_verify_hash_indexes_ok_when_present():
    import asyncio

    from security.field_encryption import get_field_encryption_service

    db = _FakeDB()
    svc = get_field_encryption_service()
    asyncio.run(svc.ensure_hash_indexes(db))
    result = asyncio.run(svc.verify_hash_indexes(db))

    assert result["ok"] is True
    assert result["missing"] == []
    assert result["present"] == result["expected"] > 0


def test_verify_hash_indexes_degraded_when_missing():
    """A missing `_hash_` index must be detected: degraded health + known-missing
    set + search-path observability counter (no silent full scan)."""
    import asyncio

    from security import field_encryption as fe

    # Create indexes, then drop one to simulate a missing index in prod.
    db = _FakeDB()
    svc = fe.get_field_encryption_service()
    asyncio.run(svc.ensure_hash_indexes(db))
    guests = db["guests"]
    del guests._indexes[fe.hash_index_name("email")]

    result = asyncio.run(svc.verify_hash_indexes(db))

    assert result["ok"] is False
    missing_pairs = {(m["collection"], m["field"]) for m in result["missing"]}
    assert ("guests", "email") in missing_pairs
    assert ("guests", "email") in fe._KNOWN_MISSING_HASH_INDEXES

    # health snapshot reflects the degradation
    health = fe.get_hash_index_health()
    assert health["verified"] is True
    assert health["ok"] is False

    # Search path stays correct AND observable: still emits the hash condition,
    # and (since the index is known-missing) flags the collection-scan fallback.
    conds = svc.build_search_query(
        collection="guests", search_fields=["email"], search_value="a@b.com")
    keys = [k for c in conds for k in c]
    assert "_hash_email" in keys, "search must still target the hash index branch"

    # Restore a clean verification so module state doesn't leak to other tests.
    asyncio.run(svc.ensure_hash_indexes(db))
    asyncio.run(svc.verify_hash_indexes(db))
    assert fe.get_hash_index_health()["ok"] is True

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

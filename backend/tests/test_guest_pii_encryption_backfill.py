"""Offline unit tests for the systemic guest-PII at-rest encryption patch.

No MongoDB / network required: these exercise the pure write/read/backfill
LOGIC against the real crypto service (which works offline):

  - security.guest_write.encrypt_guest_insert / encrypt_guest_update
  - security.encrypted_lookup.build_guest_pii_query / guest_pii_or_conditions
    / decrypt_guest_doc
  - scripts.encrypt_guest_pii_backfill candidate detection (_plaintext_pii) and
    the write-vs-read hash equivalence + idempotency contract.

The single most important invariant proven here: the deterministic
``_hash_<field>`` blind-index token written on INSERT/UPDATE is byte-identical
to the token the dual-read query builder searches for — i.e. an encrypted guest
is still findable by its plaintext email/phone.
"""
from security.field_encryption import get_field_encryption_service
from security.guest_write import _NAME_FIELDS, encrypt_guest_insert, encrypt_guest_update
from security.encrypted_lookup import (
    build_guest_pii_query,
    decrypt_guest_doc,
    guest_pii_or_conditions,
)
from scripts.encrypt_guest_pii_backfill import (
    SEARCHABLE_FIELDS,
    _looks_encrypted,
    _plaintext_pii,
)

import pytest


def _is_envelope(value) -> bool:
    return isinstance(value, str) and (
        value.startswith("SYR1:") or value.startswith("aes256gcm:")
    )


# ── INSERT path ────────────────────────────────────────────────────


def test_insert_encrypts_pii_and_writes_hash_keeps_name_plaintext():
    svc = get_field_encryption_service()
    doc = encrypt_guest_insert(
        {
            "id": "g1",
            "tenant_id": "t1",
            "name": "Ali Veli",
            "email": "User@Example.com",
            "phone": "5551234567",
            "id_number": "12345678901",
        }
    )

    # PII encrypted at rest
    assert _is_envelope(doc["email"])
    assert _is_envelope(doc["phone"])
    assert _is_envelope(doc["id_number"])

    # Blind-index tokens present and == the canonical hash (case/space norm)
    assert doc["_hash_email"] == svc.compute_search_hash("user@example.com")
    assert doc["_hash_phone"] == svc.compute_search_hash("5551234567")
    assert doc["_enc_version"] == 1

    # Name stays plaintext (kept for prefix + trigram search companions)
    assert doc["name"] == "Ali Veli"


def test_insert_is_idempotent_on_already_encrypted_value():
    once = encrypt_guest_insert(
        {"id": "g2", "tenant_id": "t1", "email": "a@b.com"}
    )
    twice = encrypt_guest_insert(dict(once))
    # Re-running must not double-encrypt (envelope passes through unchanged)
    assert twice["email"] == once["email"]
    assert twice["_hash_email"] == once["_hash_email"]


# ── UPDATE path ────────────────────────────────────────────────────


def test_update_encrypts_pii_and_refreshes_hash():
    svc = get_field_encryption_service()
    update = encrypt_guest_update({"email": "New@Example.com"}, existing={"id": "g1"})
    assert _is_envelope(update["email"])
    assert update["_hash_email"] == svc.compute_search_hash("new@example.com")


def test_update_changing_name_without_existing_raises():
    # Recomputing the merged _ng_name from a partial update alone would drop the
    # untouched name fields' trigrams -> guard must refuse.
    assert _NAME_FIELDS  # sanity: the patch declares name source fields
    with pytest.raises(ValueError):
        encrypt_guest_update({_NAME_FIELDS[0]: "Yeni Ad"}, existing=None)


# ── READ path: write/read hash equivalence (the core invariant) ─────


def test_build_guest_pii_query_matches_written_hash():
    doc = encrypt_guest_insert(
        {"id": "g3", "tenant_id": "t1", "email": "find.me@example.com"}
    )
    q = build_guest_pii_query("email", "find.me@example.com")
    # Dual-read: hash branch + plaintext branch
    assert "$or" in q
    hash_branch = next(b for b in q["$or"] if "_hash_email" in b)
    plain_branch = next(b for b in q["$or"] if "email" in b)
    # The query's hash equals the token written at encrypt time -> findable.
    assert hash_branch["_hash_email"] == doc["_hash_email"]
    assert plain_branch["email"] == "find.me@example.com"


def test_build_guest_pii_query_is_case_insensitive_on_hash():
    doc = encrypt_guest_insert(
        {"id": "g4", "tenant_id": "t1", "email": "Mixed@Case.com"}
    )
    q = build_guest_pii_query("email", "mixed@case.com")
    hash_branch = next(b for b in q["$or"] if "_hash_email" in b)
    assert hash_branch["_hash_email"] == doc["_hash_email"]


def test_guest_pii_or_conditions_combines_fields():
    conds = guest_pii_or_conditions("phone", "5550001111") + guest_pii_or_conditions(
        "email", "x@y.com"
    )
    keys = {list(c.keys())[0] for c in conds}
    assert "_hash_phone" in keys
    assert "_hash_email" in keys
    assert "phone" in keys
    assert "email" in keys


def test_decrypt_guest_doc_roundtrip_and_strips_internal_tokens():
    doc = encrypt_guest_insert(
        {
            "id": "g5",
            "tenant_id": "t1",
            "name": "Ayse",
            "email": "round@trip.com",
            "phone": "5559998877",
        }
    )
    clear = decrypt_guest_doc(dict(doc))
    assert clear["email"] == "round@trip.com"
    assert clear["phone"] == "5559998877"
    # Internal encryption + search metadata must not leak to clients
    assert "_hash_email" not in clear
    assert "_hash_phone" not in clear
    assert "_enc_version" not in clear


def test_decrypt_guest_doc_none_safe():
    assert decrypt_guest_doc(None) is None
    assert decrypt_guest_doc({}) == {}


# ── BACKFILL candidate detection ───────────────────────────────────


def test_looks_encrypted_detects_envelopes():
    assert _looks_encrypted("SYR1:abc")
    assert _looks_encrypted("aes256gcm:abc")
    assert not _looks_encrypted("plain@text.com")
    assert not _looks_encrypted(None)
    assert not _looks_encrypted(12345)


def test_plaintext_pii_picks_only_plaintext_configured_fields():
    pii = _plaintext_pii(
        {
            "name": "Ali",  # not a PII field -> ignored
            "email": "a@b.com",  # plaintext PII -> candidate
            "phone": "5551112233",  # plaintext PII -> candidate
            "id_number": "SYR1:already-encrypted",  # encrypted -> skip
            "address": "",  # empty -> skip
            "loyalty_points": 100,  # non-string -> skip
        }
    )
    assert pii == {"email": "a@b.com", "phone": "5551112233"}


def test_backfill_is_idempotent_encrypted_doc_has_no_candidates():
    # A doc already routed through the write choke point has no plaintext PII,
    # so the backfill never re-touches it (idempotency contract).
    doc = encrypt_guest_insert(
        {"id": "g6", "tenant_id": "t1", "email": "done@x.com", "phone": "5550000000"}
    )
    assert _plaintext_pii(doc) == {}


def test_backfill_searchable_set_matches_config():
    # The fields the backfill writes a _hash_ for must equal the searchable set
    # so a backfilled row is findable by the same dual-read query.
    for field in ("email", "phone", "id_number", "passport_number"):
        assert field in SEARCHABLE_FIELDS
    assert "address" not in SEARCHABLE_FIELDS  # non-searchable PII

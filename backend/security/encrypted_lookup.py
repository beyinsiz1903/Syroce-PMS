"""
Encrypted field lookup helpers for user and booking collections.

Provides dual-read query builders that search by both:
  - _hash_{field} (for encrypted documents)
  - plaintext field (for unmigrated documents)
"""
import logging
import re

from security.field_encryption import get_field_encryption_service

logger = logging.getLogger("security.encrypted_lookup")


def _svc():
    try:
        return get_field_encryption_service()
    except Exception:
        return None


def build_user_email_query(email: str) -> dict:
    """Build a MongoDB query to find a user by email (encrypted or plaintext).

    Returns a query dict like:
      {"$or": [{"_hash_email": "<hash>"}, {"email": "<email>"}]}
    """
    svc = _svc()
    if svc:
        email_hash = svc.compute_search_hash(email)
        return {"$or": [{"_hash_email": email_hash}, {"email": email}]}
    return {"email": email}


def decrypt_user_doc(doc: dict) -> dict:
    """Decrypt PII fields in a user document after DB read."""
    if not doc:
        return doc
    svc = _svc()
    if svc:
        return svc.decrypt_document(doc, collection="users")
    return doc


def encrypt_user_doc(doc: dict) -> dict:
    """Encrypt PII fields in a user document before DB write."""
    svc = _svc()
    if svc:
        return svc.encrypt_document(doc, collection="users")
    return doc


def build_guest_pii_query(field: str, value: str) -> dict:
    """Build a dual-read query to find a guest by an encrypted PII field.

    Matches encrypted documents via the deterministic ``_hash_<field>`` token
    AND legacy/unmigrated plaintext via the raw field::

      {"$or": [{"_hash_email": "<hash>"}, {"email": "<value>"}]}

    The result only contributes ``$or`` so it can be merged into a larger query
    (preserve tenant scoping / other predicates)::

      q = {"tenant_id": tid}
      q.update(build_guest_pii_query("email", email))
    """
    svc = _svc()
    if svc:
        h = svc.compute_search_hash(value)
        return {"$or": [{f"_hash_{field}": h}, {field: value}]}
    return {field: value}


def guest_pii_or_conditions(field: str, value: str) -> list[dict]:
    """``$or`` branch list for a guest PII lookup (for combining several fields).

    Returns ``[{"_hash_<field>": hash}, {"<field>": value}]`` (or just the
    plaintext branch when crypto is unavailable). Use when a single query must
    match ANY of several PII fields, e.g. phone OR email::

      q = {"tenant_id": tid,
           "$or": guest_pii_or_conditions("phone", p)
                  + guest_pii_or_conditions("email", e)}
    """
    svc = _svc()
    if svc:
        h = svc.compute_search_hash(value)
        return [{f"_hash_{field}": h}, {field: value}]
    return [{field: value}]


def guest_pii_regex_or_conditions(field: str, value: str) -> list[dict]:
    """``$or`` branches matching a guest PII field by EXACT hash OR plaintext regex.

    Encrypted values can only be matched exactly (via the deterministic
    ``_hash_<field>`` token); the case-insensitive regex branch preserves the
    previous substring-search behaviour for legacy/unmigrated plaintext rows
    only. Use for search boxes that historically ran a regex scan::

      q = {"tenant_id": tid, "$or": guest_pii_regex_or_conditions("phone", p)}
    """
    branches: list[dict] = [{field: {"$regex": re.escape(value), "$options": "i"}}]
    svc = _svc()
    if svc:
        branches.insert(0, {f"_hash_{field}": svc.compute_search_hash(value)})
    return branches


def decrypt_guest_doc(doc: dict) -> dict:
    """Decrypt PII fields in a guest document after a DB read.

    Mirrors the canonical ``pms_guests._decrypt_guest``: decrypts PII (which also
    drops the ``_hash_<field>`` blind-index tokens and ``_enc_version`` inside
    ``decrypt_document``) and then strips the internal ``_ng_name`` trigram
    search arrays, so a full-document return never leaks internal search tokens
    to a client. ``None``-safe and idempotent (plaintext passes through).
    """
    if not doc:
        return doc
    svc = _svc()
    if svc:
        doc = svc.decrypt_document(doc, collection="guests")
    try:
        from security.search_ngram import strip_ngram_fields
        strip_ngram_fields(doc)
    except Exception:
        pass
    return doc


def decrypt_booking_doc(doc: dict) -> dict:
    """Decrypt PII fields in a booking document after DB read."""
    if not doc:
        return doc
    svc = _svc()
    if svc:
        return svc.decrypt_document(doc, collection="bookings")
    return doc


def encrypt_booking_doc(doc: dict) -> dict:
    """Encrypt PII fields in a booking document before DB write."""
    svc = _svc()
    if svc:
        return svc.encrypt_document(doc, collection="bookings")
    return doc

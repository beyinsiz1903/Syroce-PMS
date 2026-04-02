"""
Encrypted field lookup helpers for user and booking collections.

Provides dual-read query builders that search by both:
  - _hash_{field} (for encrypted documents)
  - plaintext field (for unmigrated documents)
"""
import logging

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

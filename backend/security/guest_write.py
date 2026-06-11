"""
Central guest-PII write choke point (KVKK encryption-at-rest).

Every code path that inserts or updates a ``guests`` document MUST route its PII
through :func:`encrypt_guest_insert` / :func:`encrypt_guest_update` so guest PII
(email, phone, id_number, passport_number, ...) is encrypted at rest and the
deterministic ``_hash_<field>`` blind-index tokens stay consistent for hashed
exact-match search. ``name`` / ``first_name`` / ``last_name`` are intentionally
NOT encrypted: they are kept plaintext for the ``<field>_lower`` prefix and
``_ng_name`` trigram search companions.

Fail-open matches the existing ``pms_guests._encrypt_guest`` behaviour: if the
field-encryption service is unavailable the document is written as-is rather
than blocking guest creation. This adds no new weakness (same posture as today).
"""
from __future__ import annotations

import logging

from security.search_ngram import NGRAM_SOURCE_FIELDS, ngram_set_for_update_merged
from security.search_normalize import (
    apply_collection_normalized_fields,
    normalized_set_for_update,
)

logger = logging.getLogger("security.guest_write")

_GUESTS = "guests"

# Name-source fields whose presence in an update requires the stored doc to
# recompute the MERGED ``_ng_name`` (otherwise the untouched name fields'
# trigrams are silently dropped and the guest stops being infix-findable).
_NAME_FIELDS: tuple[str, ...] = tuple(NGRAM_SOURCE_FIELDS.get(_GUESTS, ()))


def _svc():
    try:
        from security.field_encryption import get_field_encryption_service

        return get_field_encryption_service()
    except Exception:  # pragma: no cover - crypto unavailable -> fail-open
        return None


def encrypt_guest_insert(doc: dict) -> dict:
    """Prepare a NEW guest document for insertion.

    Writes the plaintext name search companions, then encrypts PII fields and
    their ``_hash_<field>`` tokens. Idempotent (``encrypt_document`` skips values
    that are already encrypted) and safe on documents that carry no PII.
    """
    # Plaintext name companions first (name is not encrypted -> safe to derive).
    apply_collection_normalized_fields(doc, collection=_GUESTS)
    svc = _svc()
    if svc is not None:
        try:
            doc = svc.encrypt_document(doc, collection=_GUESTS)
        except Exception:  # pragma: no cover
            logger.warning(
                "guest insert PII encryption failed; storing plaintext",
                exc_info=True,
            )
    return doc


def encrypt_guest_update(update: dict, existing: dict | None = None) -> dict:
    """Prepare a guest ``$set`` update payload.

    Recomputes the plaintext search companions from the PLAINTEXT update (and,
    when ``existing`` is given, the merged ``_ng_name``), encrypts PII fields,
    then merges the (plaintext) companions back on top so they stay
    index-serviceable.

    Raises ``ValueError`` if the update changes a name field but ``existing`` is
    None: recomputing ``_ng_name`` from the partial update alone would drop the
    untouched name fields' trigrams (guest becomes unfindable by surname).
    """
    if existing is None and any(f in update for f in _NAME_FIELDS):
        raise ValueError(
            "encrypt_guest_update requires the existing guest doc when the "
            "update changes a name field (to recompute the merged _ng_name)."
        )

    _norm = normalized_set_for_update(update, collection=_GUESTS)
    if existing is not None:
        _norm.update(
            ngram_set_for_update_merged(existing, update, collection=_GUESTS)
        )

    svc = _svc()
    if svc is not None:
        try:
            update = svc.encrypt_document(update, collection=_GUESTS)
        except Exception:  # pragma: no cover
            logger.warning(
                "guest update PII encryption failed; storing plaintext",
                exc_info=True,
            )
    update.update(_norm)
    return update

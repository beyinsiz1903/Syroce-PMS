"""Recipient at-rest sealing for the legacy messaging module.

``messaging_consents.recipient`` and ``messaging_delivery_logs.recipient``
historically stored guest phone/e-mail as **plaintext** at rest. The Contact
Center module already seals the same data with AES-256-GCM + an HMAC blind-index,
so leaving the legacy copies in the clear defeated that armor (KVKK / data-leak
risk). This module routes every legacy recipient write/read through the EXISTING
field-encryption service (no new crypto).

Storage shape on disk:
  ``recipient_enc``  — AES envelope ciphertext (``SYR1:`` / ``aes256gcm:``)
  ``recipient_hash`` — deterministic HMAC-SHA256 blind-index for exact-match
                       lookup (consent opt-out enforcement)
Plaintext ``recipient`` is removed on write and decrypted ONLY at the read
boundary. Helpers never log the recipient value.
"""

from __future__ import annotations


def _svc():
    # Imported lazily so the module stays importable even if the security
    # package is being initialized; mirrors modules.messaging.service usage.
    from security.field_encryption import get_field_encryption_service

    return get_field_encryption_service()


def seal_recipient(recipient: str | None) -> dict:
    """Return ``{recipient_enc, recipient_hash}`` for a plaintext recipient.

    Empty / non-string recipient yields an empty dict (nothing to seal). The
    blind-index uses the service's normalized HMAC so it matches the value the
    reader computes from the raw recipient.
    """
    if not recipient or not isinstance(recipient, str):
        return {}
    svc = _svc()
    return {
        "recipient_enc": svc.encrypt_value(recipient),
        "recipient_hash": svc.compute_search_hash(recipient),
    }


def recipient_hash(recipient: str | None) -> str:
    """Deterministic blind-index token for an exact-match recipient lookup."""
    if not recipient or not isinstance(recipient, str):
        return ""
    return _svc().compute_search_hash(recipient)


def reveal_recipient(doc: dict | None) -> str:
    """Decrypt a stored recipient at the read boundary (dual-read).

    Prefers ``recipient_enc``; falls back to a legacy plaintext ``recipient``
    field for un-migrated rows. Never raises — returns ``""`` on failure so a
    read path can never 500 on a single bad envelope.
    """
    if not doc:
        return ""
    enc = doc.get("recipient_enc")
    if enc:
        try:
            return _svc().decrypt_value(enc)
        except Exception:
            return ""
    return doc.get("recipient", "") or ""


def seal_delivery_log(doc: dict) -> dict:
    """Return a copy of a delivery-log doc with its recipient sealed for storage.

    Moves plaintext ``recipient`` → ``recipient_enc`` + ``recipient_hash`` and
    drops the plaintext key so it is never persisted. A doc with no recipient is
    returned unchanged (minus the absent key).
    """
    out = dict(doc or {})
    recipient = out.pop("recipient", None)
    sealed = seal_recipient(recipient)
    if sealed:
        out["recipient_enc"] = sealed["recipient_enc"]
        out["recipient_hash"] = sealed["recipient_hash"]
    return out


def reveal_delivery_log(doc: dict | None) -> dict:
    """Return a copy of a delivery-log doc with recipient decrypted for reads.

    Sets the public ``recipient`` key to the decrypted plaintext and strips the
    at-rest ``recipient_enc`` / ``recipient_hash`` so they never leak in an API
    response. Dual-read safe for un-migrated rows (plaintext passes through).
    """
    out = dict(doc or {})
    if "recipient_enc" in out or "recipient_hash" in out:
        out["recipient"] = reveal_recipient(out)
    out.pop("recipient_enc", None)
    out.pop("recipient_hash", None)
    return out

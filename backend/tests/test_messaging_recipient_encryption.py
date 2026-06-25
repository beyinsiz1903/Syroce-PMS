"""Offline unit tests for legacy messaging recipient PII at-rest sealing (Task #647).

No MongoDB / network required: these exercise the pure seal/reveal LOGIC against
the real crypto service (which works offline):

  - modules.messaging.recipient_crypto.seal_recipient / recipient_hash /
    reveal_recipient / seal_delivery_log / reveal_delivery_log
  - scripts.encrypt_messaging_recipient_backfill candidate detection
    (_looks_encrypted) + the write-vs-read hash equivalence + idempotency.

The single most important invariant proven here: the deterministic
``recipient_hash`` blind-index token written on a consent/delivery-log write is
byte-identical to the token a consent opt-out lookup searches for — i.e. an
opted-out recipient is still matched by its plaintext phone/e-mail after sealing.
"""
from security.field_encryption import get_field_encryption_service
from modules.messaging.recipient_crypto import (
    recipient_hash,
    reveal_delivery_log,
    reveal_recipient,
    seal_delivery_log,
    seal_recipient,
)
from scripts.encrypt_messaging_recipient_backfill import _looks_encrypted


def _is_envelope(value) -> bool:
    return isinstance(value, str) and (
        value.startswith("SYR1:") or value.startswith("aes256gcm:")
    )


# ── seal_recipient ──────────────────────────────────────────────────


def test_seal_recipient_produces_envelope_and_hash():
    sealed = seal_recipient("5551234567")
    assert _is_envelope(sealed["recipient_enc"])
    assert sealed["recipient_hash"]
    # The plaintext value is NOT recoverable from the sealed dict by inspection.
    assert "5551234567" not in sealed["recipient_enc"]
    assert "5551234567" not in sealed["recipient_hash"]


def test_seal_recipient_empty_yields_empty_dict():
    assert seal_recipient("") == {}
    assert seal_recipient(None) == {}


# ── blind-index equivalence (the core invariant) ────────────────────


def test_write_hash_matches_lookup_hash():
    """The recipient_hash sealed on write == the hash a reader computes from the
    raw recipient, so a consent opt-out lookup by blind-index always matches."""
    sealed = seal_recipient("guest@example.com")
    assert sealed["recipient_hash"] == recipient_hash("guest@example.com")


def test_hash_normalizes_case_and_whitespace():
    """compute_search_hash normalizes strip+lower, so equivalent recipients map
    to one blind-index token (no opt-out bypass via casing)."""
    assert recipient_hash("Guest@Example.com") == recipient_hash("  guest@example.com  ")


def test_hash_distinguishes_distinct_recipients():
    assert recipient_hash("5551234567") != recipient_hash("5559999999")


# ── reveal_recipient (dual-read) ────────────────────────────────────


def test_reveal_recipient_decrypts_sealed():
    sealed = seal_recipient("5551234567")
    doc = {"recipient_enc": sealed["recipient_enc"], "recipient_hash": sealed["recipient_hash"]}
    assert reveal_recipient(doc) == "5551234567"


def test_reveal_recipient_dual_read_legacy_plaintext():
    """Un-migrated rows still carrying plaintext recipient must read through."""
    assert reveal_recipient({"recipient": "5551234567"}) == "5551234567"


def test_reveal_recipient_never_raises_on_bad_envelope():
    # The crypto service degrades gracefully (returns a value, logs a warning)
    # rather than raising, so a read path can never 500 on a bad envelope.
    assert isinstance(reveal_recipient({"recipient_enc": "SYR1:not-a-real-envelope"}), str)
    assert reveal_recipient(None) == ""
    assert reveal_recipient({}) == ""


# ── delivery-log seal/reveal round-trip ─────────────────────────────


def test_seal_delivery_log_removes_plaintext_keeps_other_fields():
    log = {"id": "L1", "tenant_id": "t1", "channel": "whatsapp",
           "recipient": "5551234567", "status": "sent"}
    sealed = seal_delivery_log(log)
    # Plaintext recipient is gone; sealed fields present.
    assert "recipient" not in sealed
    assert _is_envelope(sealed["recipient_enc"])
    assert sealed["recipient_hash"] == recipient_hash("5551234567")
    # Non-PII fields untouched.
    assert sealed["id"] == "L1"
    assert sealed["channel"] == "whatsapp"
    assert sealed["status"] == "sent"
    # Original dict is not mutated.
    assert log["recipient"] == "5551234567"


def test_delivery_log_seal_reveal_round_trip():
    log = {"id": "L1", "recipient": "guest@example.com", "channel": "email"}
    revealed = reveal_delivery_log(seal_delivery_log(log))
    assert revealed["recipient"] == "guest@example.com"
    # At-rest fields stripped from the read-boundary output.
    assert "recipient_enc" not in revealed
    assert "recipient_hash" not in revealed


def test_reveal_delivery_log_dual_read_legacy():
    revealed = reveal_delivery_log({"id": "L1", "recipient": "5551234567"})
    assert revealed["recipient"] == "5551234567"


# ── backfill candidate detection + idempotency ──────────────────────


def test_backfill_detects_plaintext_skips_envelope():
    assert _looks_encrypted("5551234567") is False
    assert _looks_encrypted(seal_recipient("5551234567")["recipient_enc"]) is True


def test_seal_is_idempotent_for_reads():
    """Sealing then revealing returns the original; a sealed doc carries no
    plaintext recipient so the backfill never re-selects it."""
    sealed = seal_delivery_log({"recipient": "5551234567"})
    assert "recipient" not in sealed
    assert reveal_recipient(sealed) == "5551234567"


# ── consent enforcement: fail-closed + deterministic across mixed rows ──


class _FakeConsentCursor:
    def __init__(self, docs):
        self._docs = docs

    def __aiter__(self):
        async def gen():
            for d in self._docs:
                yield d
        return gen()


class _FakeConsents:
    """Stub of db.messaging_consents that returns canned rows for find()."""

    def __init__(self, rows):
        self._rows = rows

    def find(self, query, projection=None):
        # Mirror the service's $or matching just enough for the test: a row
        # matches if its recipient_hash OR plaintext recipient is in the $or.
        wanted = []
        for term in query.get("$or", []):
            wanted.append(term)
        out = []
        for r in self._rows:
            if r.get("tenant_id") != query.get("tenant_id"):
                continue
            if r.get("channel") != query.get("channel"):
                continue
            for term in wanted:
                if "recipient_hash" in term and r.get("recipient_hash") == term["recipient_hash"]:
                    out.append(r)
                    break
                if "recipient" in term and r.get("recipient") == term["recipient"]:
                    out.append(r)
                    break
        return _FakeConsentCursor(out)


class _FakeDB:
    def __init__(self, rows):
        self.messaging_consents = _FakeConsents(rows)


def _make_service(rows):
    from modules.messaging.service import MessagingService
    return MessagingService(_FakeDB(rows))


import pytest


@pytest.mark.asyncio
async def test_consent_optout_wins_when_legacy_and_new_rows_coexist():
    """A legacy plaintext OPT_OUT row + a new hash-keyed OPT_IN row for the same
    recipient must still BLOCK the send (OPT_OUT is authoritative, order-free)."""
    r = "5551234567"
    rows = [
        # new hash-keyed row says opt-in
        {"tenant_id": "t1", "channel": "sms", "recipient_hash": recipient_hash(r),
         "status": "opt_in"},
        # legacy plaintext row says opt-out
        {"tenant_id": "t1", "channel": "sms", "recipient": r, "status": "opt_out"},
    ]
    svc = _make_service(rows)
    assert await svc._check_consent("t1", r, "sms") is False
    # reversed order must give the same answer (deterministic)
    svc2 = _make_service(list(reversed(rows)))
    assert await svc2._check_consent("t1", r, "sms") is False


@pytest.mark.asyncio
async def test_consent_allows_when_no_optout_row():
    r = "5551234567"
    rows = [{"tenant_id": "t1", "channel": "sms", "recipient_hash": recipient_hash(r),
             "status": "opt_in"}]
    svc = _make_service(rows)
    assert await svc._check_consent("t1", r, "sms") is True


@pytest.mark.asyncio
async def test_consent_defaults_open_with_no_rows():
    svc = _make_service([])
    assert await svc._check_consent("t1", "5551234567", "sms") is True

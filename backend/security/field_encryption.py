"""
Field-Level At-Rest Encryption for PII Data.

Provides transparent encrypt-on-write / decrypt-on-read for sensitive
database fields. Uses the existing AES-256-GCM crypto engine with
HMAC-SHA256 search hashes for queryable encrypted fields.

Design:
  - Encrypted values use SYR1: or aes256gcm: envelope (existing crypto engine)
  - Search hashes stored as `_hash_{field}` alongside encrypted fields
  - Dual-read: if value is not encrypted, return as-is (migration compat)
  - Documents marked with `_enc_version: 1` after encryption
  - Decrypt only for authorized roles; failed decrypt emits audit event

Usage:
  from security.field_encryption import get_field_encryption_service

  svc = get_field_encryption_service()
  doc = svc.encrypt_document(doc, collection="guests")
  doc = svc.decrypt_document(doc, collection="guests")
  hash_val = svc.compute_search_hash("user@example.com")
"""
import hashlib
import hmac
import logging
import os
from datetime import UTC, datetime

from core.crypto.service import get_crypto_service

logger = logging.getLogger("security.field_encryption")

# HMAC pepper for search hashes — must be consistent across app lifetime
_PEPPER = os.environ.get(
    "FIELD_ENCRYPTION_PEPPER",
    os.environ.get("CM_MASTER_KEY_CURRENT", "syroce-field-enc-pepper-dev"),
)
_PEPPER_BYTES = _PEPPER.encode("utf-8")

# ── Collection → encrypted fields config ──────────────────────────

ENCRYPTED_FIELDS: dict[str, list[dict]] = {
    "guests": [
        {"field": "email", "searchable": True},
        {"field": "phone", "searchable": True},
        {"field": "phone_number", "searchable": True},
        {"field": "mobile", "searchable": True},
        {"field": "id_number", "searchable": True},
        {"field": "passport_number", "searchable": True},
        {"field": "tc_kimlik", "searchable": True},
        {"field": "address", "searchable": False},
        {"field": "date_of_birth", "searchable": False},
        {"field": "credit_card", "searchable": False},
        {"field": "card_number", "searchable": False},
        {"field": "iban", "searchable": True},
    ],
    "users": [
        {"field": "email", "searchable": True},
        {"field": "phone", "searchable": True},
    ],
    "bookings": [
        {"field": "guest_email", "searchable": True},
        {"field": "guest_phone", "searchable": True},
        {"field": "billing_address", "searchable": False},
        {"field": "billing_tax_number", "searchable": True},
    ],
    "reservations": [
        {"field": "guest_email", "searchable": True},
        {"field": "guest_phone", "searchable": True},
    ],
}


def _get_field_names(collection: str) -> list[str]:
    """Return list of field names to encrypt for a collection."""
    return [f["field"] for f in ENCRYPTED_FIELDS.get(collection, [])]


def _get_searchable_fields(collection: str) -> set[str]:
    """Return set of searchable field names for a collection."""
    return {
        f["field"]
        for f in ENCRYPTED_FIELDS.get(collection, [])
        if f.get("searchable")
    }


def hash_index_name(field: str) -> str:
    """Canonical index name for a searchable field's `_hash_` blind-index."""
    return f"hash_{field}_idx"


def hash_index_key(field: str) -> str:
    """Canonical indexed key for a searchable field's `_hash_` blind-index."""
    return f"_hash_{field}"


def expected_hash_indexes() -> dict[str, dict[str, str]]:
    """Canonical `{collection: {index_name: indexed_key}}` map of the `_hash_`
    blind-index indexes that MUST exist for every searchable encrypted field.

    Single source of truth shared by `ensure_hash_indexes` (creates them),
    `verify_hash_indexes` (asserts they exist) and the CI test (pins the map to
    `ENCRYPTED_FIELDS`). Adding a new searchable field here without an index
    makes verification fail-closed.
    """
    out: dict[str, dict[str, str]] = {}
    for collection_name, field_configs in ENCRYPTED_FIELDS.items():
        for fc in field_configs:
            if fc.get("searchable"):
                field = fc["field"]
                out.setdefault(collection_name, {})[hash_index_name(field)] = (
                    hash_index_key(field)
                )
    return out


# ── Hash-index health state (fail-closed signal) ──────────────────
#
# `verify_hash_indexes` writes the last verification result here so the
# health/readiness layer can surface a "degraded" signal and the synchronous
# search path can consult the known-missing set without touching the DB.
_HASH_INDEX_HEALTH: dict = {
    "verified": False,
    "ok": None,
    "expected": 0,
    "present": 0,
    "missing": [],
    "checked_at": None,
}

# (collection, field) pairs whose `_hash_` index was expected but absent at the
# last verification. Read by build_search_query (sync) to make an otherwise
# silent tenant-wide collection scan observable.
_KNOWN_MISSING_HASH_INDEXES: set[tuple[str, str]] = set()

# Warn-once guard so a persistently-missing index does not flood logs on every
# search request.
_SEARCH_FALLBACK_WARNED: set[tuple[str, str]] = set()

try:  # pragma: no cover - prometheus is a hard dependency in prod
    from prometheus_client import Counter as _Counter

    _hash_index_missing_total = _Counter(
        "hotel_pms_encrypted_hash_index_missing_total",
        "Searchable encrypted-PII `_hash_` blind-index expected but missing at "
        "startup/health verification (fail-closed signal).",
        ["collection", "field"],
    )
    _hash_index_search_fallback_total = _Counter(
        "hotel_pms_encrypted_search_index_missing_total",
        "Encrypted-PII search executed while its `_hash_` index was known-missing "
        "— request still served but degrades to a tenant-wide collection scan.",
        ["collection", "field"],
    )
except Exception:  # pragma: no cover
    _hash_index_missing_total = None
    _hash_index_search_fallback_total = None


def get_hash_index_health() -> dict:
    """Return a copy of the last `_hash_` index verification result.

    Consumed by the deep health endpoint to mark the service "degraded" when a
    searchable encrypted-PII index is missing.
    """
    snapshot = dict(_HASH_INDEX_HEALTH)
    snapshot["missing"] = list(_HASH_INDEX_HEALTH.get("missing", []))
    return snapshot


class FieldEncryptionService:
    """Transparent field-level encryption for MongoDB documents."""

    def __init__(self):
        self._crypto = get_crypto_service()
        logger.info(
            "FieldEncryptionService initialized: crypto_health=%s",
            self._crypto.health(),
        )

    # ── Core operations ───────────────────────────────────────────

    def encrypt_value(self, value: str) -> str:
        """Encrypt a single string value. Returns envelope string."""
        if not value or not isinstance(value, str):
            return value
        if self._is_encrypted(value):
            return value  # Already encrypted
        return self._crypto.encrypt(value)

    def decrypt_value(self, value: str) -> str:
        """Decrypt a single value. Returns plaintext or original if not encrypted."""
        if not value or not isinstance(value, str):
            return value
        if not self._is_encrypted(value):
            return value  # Plaintext — dual-read compat
        try:
            return self._crypto.decrypt(value)
        except Exception:
            logger.warning("decrypt_field_failed: value_prefix=%s", value[:10])
            return value  # Return as-is on failure; audit handled upstream

    def compute_search_hash(self, value: str) -> str:
        """Compute deterministic HMAC-SHA256 hash for search index.

        Normalizes input (lowercase, strip) before hashing to ensure
        consistent matches regardless of case/whitespace.
        """
        if not value or not isinstance(value, str):
            return ""
        normalized = value.strip().lower()
        return hmac.new(_PEPPER_BYTES, normalized.encode("utf-8"), hashlib.sha256).hexdigest()

    # ── Document-level operations ─────────────────────────────────

    def encrypt_document(self, doc: dict, *, collection: str) -> dict:
        """Encrypt PII fields in a document before DB write.

        - Encrypts each configured field
        - Adds `_hash_{field}` for searchable fields
        - Sets `_enc_version: 1`
        """
        fields = _get_field_names(collection)
        searchable = _get_searchable_fields(collection)
        if not fields:
            return doc

        result = dict(doc)
        encrypted_any = False

        for field_name in fields:
            value = result.get(field_name)
            if value and isinstance(value, str) and not self._is_encrypted(value):
                result[field_name] = self.encrypt_value(value)
                encrypted_any = True

                if field_name in searchable:
                    result[f"_hash_{field_name}"] = self.compute_search_hash(value)

        if encrypted_any:
            result["_enc_version"] = 1
            result["_encrypted_at"] = datetime.now(UTC).isoformat()

        return result

    def decrypt_document(self, doc: dict, *, collection: str) -> dict:
        """Decrypt PII fields in a document after DB read.

        Dual-read: if field is not encrypted, returns as-is.
        """
        if not doc:
            return doc

        fields = _get_field_names(collection)
        if not fields:
            return doc

        result = dict(doc)

        for field_name in fields:
            value = result.get(field_name)
            if value and isinstance(value, str) and self._is_encrypted(value):
                result[field_name] = self.decrypt_value(value)

        # Remove internal encryption metadata from API responses
        result.pop("_enc_version", None)
        result.pop("_encrypted_at", None)
        for field_name in fields:
            result.pop(f"_hash_{field_name}", None)

        return result

    def build_search_query(
        self,
        *,
        collection: str,
        search_fields: list[str],
        search_value: str,
    ) -> list[dict]:
        """Build MongoDB $or query conditions for encrypted + plaintext search.

        For searchable encrypted fields: match against `_hash_{field}`
        For non-encrypted fields: use regex as before
        Returns list of conditions for $or query.
        """
        conditions = []
        searchable = _get_searchable_fields(collection)
        # `search_value` is treated as RAW (un-escaped). The hash branch needs
        # the raw value: compute_search_hash normalizes (strip+lower) it to match
        # the stored _hash_<field> token written at encrypt time. Passing a
        # pre-regex-escaped value here would corrupt the HMAC (e.g. "a.b@x.com"
        # → "a\.b@x\.com") and the hash index would never match.
        search_hash = self.compute_search_hash(search_value)
        # The regex branch is only a dual-read fallback for un-migrated plaintext
        # docs; escape here so PII regex metacharacters (the "." in emails) stay
        # literal and cannot inject/DoS the Mongo regex engine.
        import re as _re
        regex_value = _re.escape(search_value or "")

        for field_name in search_fields:
            if field_name in searchable:
                # Exact match via hash index
                conditions.append({f"_hash_{field_name}": search_hash})
                # Observability: if startup/health verification flagged this
                # field's `_hash_` index as missing, the equality branch above
                # silently degrades to a tenant-wide collection scan. Surface it
                # (metric + warn-once) rather than failing — the query still
                # returns correct results via the dual-read regex branch below.
                if (collection, field_name) in _KNOWN_MISSING_HASH_INDEXES:
                    if _hash_index_search_fallback_total is not None:
                        try:
                            _hash_index_search_fallback_total.labels(
                                collection=collection, field=field_name
                            ).inc()
                        except Exception:
                            pass
                    if (collection, field_name) not in _SEARCH_FALLBACK_WARNED:
                        _SEARCH_FALLBACK_WARNED.add((collection, field_name))
                        logger.warning(
                            "encrypted_search_hash_index_missing: collection=%s "
                            "field=%s — search degraded to collection scan; run "
                            "ensure_hash_indexes",
                            collection,
                            field_name,
                        )
            # Also try regex on plaintext (dual-read: un-migrated docs)
            conditions.append({field_name: {"$regex": regex_value, "$options": "i"}})

        return conditions

    # ── Migration helpers ─────────────────────────────────────────

    async def migrate_collection(
        self,
        db,
        collection_name: str,
        *,
        batch_size: int = 100,
        progress_collection: str = "field_encryption_progress",
    ) -> dict:
        """Encrypt existing plaintext documents in a collection.

        Processes in batches. Tracks progress in `field_encryption_progress`.
        Returns migration summary.
        """
        col = db[collection_name]
        progress_col = db[progress_collection]
        fields = _get_field_names(collection_name)
        if not fields:
            return {"collection": collection_name, "status": "skipped", "reason": "no_fields_configured"}

        # Find un-encrypted documents (no _enc_version field)
        total = await col.count_documents({"_enc_version": {"$exists": False}})
        processed = 0
        errors = 0

        logger.info("migrate_collection: %s — %d documents to encrypt", collection_name, total)

        cursor = col.find({"_enc_version": {"$exists": False}}, {"_id": 1}).batch_size(batch_size)
        doc_ids = [doc["_id"] async for doc in cursor]

        for doc_id in doc_ids:
            try:
                doc = await col.find_one({"_id": doc_id})
                if not doc:
                    continue
                encrypted_doc = self.encrypt_document(doc, collection=collection_name)
                update_fields = {
                    k: v for k, v in encrypted_doc.items()
                    if k != "_id" and k in (
                        fields + [f"_hash_{f}" for f in fields] + ["_enc_version", "_encrypted_at"]
                    )
                }
                # Only include fields that actually changed
                final_update = {}
                for k, v in update_fields.items():
                    if k.startswith("_hash_") or k in ("_enc_version", "_encrypted_at"):
                        final_update[k] = v
                    elif doc.get(k) != v:
                        final_update[k] = v

                # Always mark as processed even if no PII fields had data
                if "_enc_version" not in final_update:
                    final_update["_enc_version"] = 1
                    final_update["_encrypted_at"] = datetime.now(UTC).isoformat()

                if final_update:
                    await col.update_one({"_id": doc_id}, {"$set": final_update})
                processed += 1
            except Exception as e:
                errors += 1
                logger.error("migrate_doc_failed: collection=%s doc_id=%s error=%s", collection_name, doc_id, e)

        # Record progress
        summary = {
            "collection": collection_name,
            "total_unencrypted": total,
            "processed": processed,
            "errors": errors,
            "status": "completed" if errors == 0 else "completed_with_errors",
            "completed_at": datetime.now(UTC).isoformat(),
        }
        await progress_col.update_one(
            {"collection": collection_name},
            {"$set": summary},
            upsert=True,
        )
        logger.info("migrate_collection_done: %s", summary)
        return summary

    async def get_encryption_status(self, db) -> dict:
        """Return encryption status for all configured collections."""
        status = {}
        for collection_name, field_configs in ENCRYPTED_FIELDS.items():
            col = db[collection_name]
            total = await col.count_documents({})
            encrypted = await col.count_documents({"_enc_version": {"$exists": True}})
            unencrypted = total - encrypted
            status[collection_name] = {
                "total_documents": total,
                "encrypted": encrypted,
                "unencrypted": unencrypted,
                "coverage_percent": round((encrypted / total * 100) if total > 0 else 0, 1),
                "fields": [f["field"] for f in field_configs],
            }
        return status

    async def ensure_hash_indexes(self, db) -> list[str]:
        """Create MongoDB indexes on _hash_ fields for search performance."""
        created = []
        for collection_name, field_configs in ENCRYPTED_FIELDS.items():
            col = db[collection_name]
            for fc in field_configs:
                if fc.get("searchable"):
                    index_name = f"hash_{fc['field']}_idx"
                    try:
                        await col.create_index(
                            f"_hash_{fc['field']}",
                            name=index_name,
                            sparse=True,
                        )
                        created.append(f"{collection_name}.{index_name}")
                    except Exception as e:
                        logger.warning("index_create_failed: %s.%s — %s", collection_name, index_name, e)
        return created

    async def verify_hash_indexes(self, db) -> dict:
        """Verify every expected searchable `_hash_` index actually exists.

        Run this right after `ensure_hash_indexes` at startup (and reachable via
        the admin/health surface). For each searchable encrypted field it lists
        the collection's real indexes and checks that the `_hash_<field>` key is
        indexed. Missing indexes are logged, counted (Prometheus) and recorded
        in module state so:
          - the deep health endpoint can report "degraded" (fail-closed signal),
          - the synchronous search path can flag the silent collection-scan
            degradation without touching the DB.

        Returns a summary dict; never raises (a verification failure must not
        crash startup, only signal degradation).
        """
        expected = expected_hash_indexes()
        missing: list[dict] = []
        present: list[dict] = []

        for collection_name, idx_map in expected.items():
            indexed_keys: set[str] = set()
            list_ok = True
            try:
                info = await db[collection_name].index_information()
                for _name, meta in info.items():
                    for key in meta.get("key", []):
                        # key entries are (field, direction) tuples
                        if isinstance(key, (list, tuple)) and key:
                            indexed_keys.add(key[0])
            except Exception as e:
                # Can't enumerate indexes -> treat as missing (fail-closed).
                list_ok = False
                logger.warning(
                    "hash_index_verify_list_failed: collection=%s — %s",
                    collection_name,
                    e,
                )

            for index_name, indexed_key in idx_map.items():
                field = indexed_key[len("_hash_"):]
                if list_ok and indexed_key in indexed_keys:
                    present.append(
                        {"collection": collection_name, "field": field, "index": index_name}
                    )
                else:
                    missing.append(
                        {"collection": collection_name, "field": field, "index": index_name}
                    )

        # Update module-level health state + known-missing set atomically-ish.
        global _KNOWN_MISSING_HASH_INDEXES
        _KNOWN_MISSING_HASH_INDEXES = {(m["collection"], m["field"]) for m in missing}
        _SEARCH_FALLBACK_WARNED.intersection_update(_KNOWN_MISSING_HASH_INDEXES)

        _HASH_INDEX_HEALTH["verified"] = True
        _HASH_INDEX_HEALTH["ok"] = not missing
        _HASH_INDEX_HEALTH["expected"] = len(present) + len(missing)
        _HASH_INDEX_HEALTH["present"] = len(present)
        _HASH_INDEX_HEALTH["missing"] = missing
        _HASH_INDEX_HEALTH["checked_at"] = datetime.now(UTC).isoformat()

        if missing:
            for m in missing:
                if _hash_index_missing_total is not None:
                    try:
                        _hash_index_missing_total.labels(
                            collection=m["collection"], field=m["field"]
                        ).inc()
                    except Exception:
                        pass
            logger.warning(
                "encrypted_hash_index_missing: %d searchable `_hash_` index(es) "
                "absent — encrypted-PII search degrades to collection scan: %s",
                len(missing),
                ", ".join(f"{m['collection']}.{m['index']}" for m in missing),
            )
        else:
            logger.info(
                "encrypted_hash_index_verify_ok: %d searchable `_hash_` indexes present",
                len(present),
            )

        return get_hash_index_health()

    # ── Helpers ────────────────────────────────────────────────────

    @staticmethod
    def _is_encrypted(value: str) -> bool:
        """Check if a value looks encrypted (SYR1: or aes256gcm: prefix)."""
        if not isinstance(value, str):
            return False
        return value.startswith("SYR1:") or value.startswith("aes256gcm:")

    def get_config(self) -> dict:
        """Return current encryption configuration."""
        return {
            "collections": {
                col: [f["field"] for f in fields]
                for col, fields in ENCRYPTED_FIELDS.items()
            },
            "crypto_health": self._crypto.health(),
        }


# ── Singleton ──────────────────────────────────────────────────────

_instance: FieldEncryptionService | None = None


def get_field_encryption_service() -> FieldEncryptionService:
    """Get or create the singleton FieldEncryptionService."""
    global _instance
    if _instance is None:
        _instance = FieldEncryptionService()
    return _instance

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
        search_hash = self.compute_search_hash(search_value)

        for field_name in search_fields:
            if field_name in searchable:
                # Exact match via hash index
                conditions.append({f"_hash_{field_name}": search_hash})
            # Also try regex on plaintext (dual-read: un-migrated docs)
            conditions.append({field_name: {"$regex": search_value, "$options": "i"}})

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

"""Shared seed helpers: timestamps, UUIDs, optional PII encryption, constants."""
import uuid
from datetime import UTC, datetime

from core._pwd import BcryptContext

pwd_context = BcryptContext()

DEMO_EMAIL = "info@syroce.com"
DEMO_PASSWORD = "demo123"
DEMO_HOTEL_NAME = "Syroce Demo Hotel"


def _now():
    return datetime.now(UTC)


def _uuid():
    return str(uuid.uuid4())


def _encrypt_doc(doc: dict, collection: str) -> dict:
    """Encrypt PII fields if field encryption service is available."""
    try:
        from security.field_encryption import get_field_encryption_service
        svc = get_field_encryption_service()
        return svc.encrypt_document(doc, collection=collection)
    except Exception:
        return doc

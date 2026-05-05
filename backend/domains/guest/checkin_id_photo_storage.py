"""
Secure storage for guest-supplied ID photos collected during online check-in.

Why this module exists
----------------------
The mobile guest app captures an ID photo and a typed signature consent during
the pre-arrival check-in flow.  The raw photo is privacy-sensitive (passport /
national ID), must NOT be served from the public ``/api/uploads`` static mount,
and must be encrypted at rest so an attacker who lifts the volume cannot read
the bytes.

Design
------
* Photos are validated with Pillow magic-bytes inspection (rejects SVG, PDF,
  polyglots) and capped to ``MAX_IMAGE_BYTES``.
* Each photo gets a unique ``photo_id`` (UUID4 hex) and is encrypted with the
  platform's AES-256-GCM engine (HKDF-derived key + AAD context binding to
  ``tenant_id`` + ``booking_id`` + ``photo_id``).
* The ciphertext is written to
  ``SECURE_UPLOAD_DIR/checkin_id_photos/<tenant_id>/<photo_id>.bin`` (default
  ``<backend>/secure_storage``).  This directory is **deliberately separate
  from** ``UPLOAD_DIR`` so it can NEVER appear under the public
  ``/api/uploads`` static mount, even if an operator misconfigures
  ``UPLOAD_DIR``.  Operators who relocate the secure store should point
  ``SECURE_UPLOAD_DIR`` at a path that no web server / reverse proxy serves
  statically (and ideally one outside the application's web root).
* Only metadata (sha-256 hash of plaintext, sanitized content-type, size,
  uploader) is recorded in MongoDB — never the photo bytes themselves.

Access
------
Reading a photo requires staff (frontdesk module) access via
:func:`load_id_photo`; the caller is responsible for the auth check.
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from core.crypto.engine import AADContext, AESGCMEngine
from core.crypto.errors import CryptoError, DecryptionError, TamperDetectedError
from core.crypto.keys import load_keyring
from security.upload_validator import MAX_IMAGE_BYTES, validate_image_bytes

logger = logging.getLogger("domains.guest.checkin_id_photo_storage")

# Magic prefix on every encrypted ID-photo blob. The current format is
# raw-binary AES-GCM (kid, nonce, ciphertext+tag) prefixed by a 4-byte big-
# endian kid length. This avoids the ~33% base64 overhead the credential
# service applies — important when ID photos can run to 5 MB each.
_BLOB_MAGIC = b"SYRIDP1\0"  # 8 bytes, fixed-width
_NONCE_SIZE = 12

_engine: AESGCMEngine | None = None


def _get_engine() -> AESGCMEngine:
    """Lazy-load the AES-GCM engine.

    We deliberately use :class:`AESGCMEngine` directly (rather than the higher
    level :class:`CredentialEncryptionService`) because:

    * The credential service is a string-in / string-out API that base64-encodes
      every payload — wasteful for multi-megabyte image bytes.
    * The credential service silently drops AAD when ``CRYPTO_V2_ENABLED`` is
      false (legacy compat).  For ID photos we want AAD binding to tenant +
      booking + photo unconditionally so file-swap tampering is detected.

    Both paths share the same HKDF-derived key material from :mod:`core.crypto.keys`.
    """
    global _engine
    if _engine is None:
        _engine = AESGCMEngine(load_keyring())
    return _engine


def _aad(tenant_id: str, booking_id: str, photo_id: str) -> AADContext:
    return AADContext(
        tenant_id=tenant_id,
        provider="online_checkin",
        property_id=booking_id,
        environment=os.environ.get("APP_ENV", "development"),
        context_type=f"id_photo:{photo_id}",
    )


def _encrypt_blob(
    plaintext: bytes, *, tenant_id: str, booking_id: str, photo_id: str,
) -> bytes:
    """AES-256-GCM encrypt arbitrary bytes with AAD binding.

    Wire format::

        magic(8) | kid_len(2 BE) | kid_bytes | nonce(12) | ciphertext+tag

    Returns the binary blob ready to be written to disk.
    """
    import secrets

    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    engine = _get_engine()
    kid, key = engine._keyring.encryption_key()  # noqa: SLF001 — adjacent module
    kid_bytes = kid.encode("utf-8")
    if len(kid_bytes) > 0xFFFF:
        raise CryptoError("kid too long")

    nonce = secrets.token_bytes(_NONCE_SIZE)
    aad = _aad(tenant_id, booking_id, photo_id).to_bytes()
    aesgcm = AESGCM(key)
    ciphertext = aesgcm.encrypt(nonce, plaintext, aad)
    return (
        _BLOB_MAGIC
        + len(kid_bytes).to_bytes(2, "big")
        + kid_bytes
        + nonce
        + ciphertext
    )


def _decrypt_blob(
    blob: bytes, *, tenant_id: str, booking_id: str, photo_id: str,
) -> bytes:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not blob.startswith(_BLOB_MAGIC):
        raise DecryptionError("bad_magic")
    pos = len(_BLOB_MAGIC)
    if len(blob) < pos + 2:
        raise DecryptionError("truncated_header")
    kid_len = int.from_bytes(blob[pos : pos + 2], "big")
    pos += 2
    if len(blob) < pos + kid_len + _NONCE_SIZE + 16:  # 16 = GCM tag
        raise DecryptionError("truncated_body")
    kid = blob[pos : pos + kid_len].decode("utf-8")
    pos += kid_len
    nonce = blob[pos : pos + _NONCE_SIZE]
    pos += _NONCE_SIZE
    ciphertext = blob[pos:]

    engine = _get_engine()
    key = engine._keyring.decryption_key(kid)  # noqa: SLF001 — adjacent module
    aad = _aad(tenant_id, booking_id, photo_id).to_bytes()
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise TamperDetectedError(kid=kid) from exc


def _backend_dir() -> Path:
    # backend/domains/guest/<this file>  →  backend/
    return Path(__file__).resolve().parent.parent.parent


def _secure_root() -> Path:
    """Resolve the secure-storage root for ID photos.

    Resolution order:
      1. ``SECURE_UPLOAD_DIR`` env var (operators configure this in production)
      2. fallback to ``<backend>/secure_storage``

    Critically, this is **never** derived from ``UPLOAD_DIR`` — that directory
    is mounted at ``/api/uploads`` by the FastAPI app and would expose the
    encrypted blobs over the public HTTP surface.  As a defence-in-depth
    measure we also explicitly reject any value that resolves underneath
    ``UPLOAD_DIR`` to fail loudly during startup if a misconfiguration ever
    co-locates the two roots.
    """
    backend_dir = _backend_dir()
    secure_root = Path(
        os.environ.get("SECURE_UPLOAD_DIR", str(backend_dir / "secure_storage"))
    ).resolve()

    upload_dir_env = os.environ.get("UPLOAD_DIR", str(backend_dir / "uploads"))
    upload_dir = Path(upload_dir_env).resolve()
    try:
        # PurePath.is_relative_to was added in Python 3.9 — supported here.
        if secure_root == upload_dir or secure_root.is_relative_to(upload_dir):
            raise RuntimeError(
                "SECURE_UPLOAD_DIR must NOT be inside UPLOAD_DIR — the latter "
                "is publicly served at /api/uploads and would leak the "
                "encrypted ID-photo blobs over HTTP."
            )
    except AttributeError:  # pragma: no cover — Python < 3.9 fallback
        if str(secure_root).startswith(str(upload_dir) + os.sep) or secure_root == upload_dir:
            raise RuntimeError(
                "SECURE_UPLOAD_DIR must NOT be inside UPLOAD_DIR."
            )

    return secure_root / "checkin_id_photos"


def _photo_path(tenant_id: str, photo_id: str) -> Path:
    safe_tenant = "".join(c for c in tenant_id if c.isalnum() or c in "-_") or "unknown"
    safe_id = "".join(c for c in photo_id if c.isalnum() or c in "-_")
    if not safe_id:
        raise HTTPException(status_code=400, detail="Gecersiz fotograf kimligi")
    return _secure_root() / safe_tenant / f"{safe_id}.bin"


@dataclass(frozen=True)
class StoredIdPhoto:
    """Metadata for a stored, encrypted ID photo. NEVER carries plaintext bytes."""

    photo_id: str
    tenant_id: str
    booking_id: str
    content_type: str
    extension: str
    size_bytes: int
    sha256: str

    def to_dict(self) -> dict:
        return {
            "photo_id": self.photo_id,
            "tenant_id": self.tenant_id,
            "booking_id": self.booking_id,
            "content_type": self.content_type,
            "extension": self.extension,
            "size_bytes": self.size_bytes,
            "sha256": self.sha256,
        }


def save_id_photo(
    *,
    tenant_id: str,
    booking_id: str,
    image_bytes: bytes,
    field_label: str = "Kimlik fotografi",
) -> StoredIdPhoto:
    """Validate, encrypt and persist an ID photo.

    Returns metadata describing the stored blob.  Raises ``HTTPException`` on
    invalid / oversized input.  The plaintext bytes are NEVER persisted — only
    the AES-256-GCM ciphertext (with AAD bound to tenant + booking + photo).
    """
    safe_ct, safe_ext = validate_image_bytes(
        image_bytes, max_bytes=MAX_IMAGE_BYTES, field_label=field_label
    )

    photo_id = uuid.uuid4().hex
    sha256 = hashlib.sha256(image_bytes).hexdigest()

    blob = _encrypt_blob(
        image_bytes, tenant_id=tenant_id, booking_id=booking_id, photo_id=photo_id,
    )

    dest = _photo_path(tenant_id, photo_id)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Restrict the per-tenant directory so only the API process can read
        # the encrypted blobs.  Best-effort: filesystems that ignore mode bits
        # (e.g. some object-storage gateways) won't error.
        try:
            os.chmod(dest.parent, 0o700)
        except OSError:
            pass
        # Atomic write: create alongside, then rename, so a crash mid-write
        # never leaves a half-written ciphertext that decrypt would treat as
        # tampering.
        tmp = dest.with_suffix(dest.suffix + ".tmp")
        tmp.write_bytes(blob)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, dest)
    except OSError as exc:
        logger.error("Failed to persist encrypted ID photo: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="Kimlik fotografi guvenli depoya yazilamadi.",
        ) from exc

    return StoredIdPhoto(
        photo_id=photo_id,
        tenant_id=tenant_id,
        booking_id=booking_id,
        content_type=safe_ct,
        extension=safe_ext,
        size_bytes=len(image_bytes),
        sha256=sha256,
    )


def load_id_photo(
    *,
    tenant_id: str,
    booking_id: str,
    photo_id: str,
) -> bytes:
    """Decrypt and return the ID-photo bytes for staff display.

    Caller MUST have already enforced staff authorization.  Raises 404 if the
    file is missing and 500 if decryption fails (which indicates tampering or
    key-rotation drift — both critical incidents to surface, never silently).
    """
    src = _photo_path(tenant_id, photo_id)
    if not src.exists():
        raise HTTPException(status_code=404, detail="Kimlik fotografi bulunamadi")

    try:
        blob = src.read_bytes()
    except OSError as exc:
        logger.error("Failed to read encrypted ID photo: %s", exc)
        raise HTTPException(status_code=500, detail="Kimlik fotografi okunamadi") from exc

    try:
        return _decrypt_blob(
            blob, tenant_id=tenant_id, booking_id=booking_id, photo_id=photo_id,
        )
    except (TamperDetectedError, DecryptionError, CryptoError) as exc:
        logger.error(
            "ID photo decryption failed (tenant=%s booking=%s photo=%s): %s",
            tenant_id, booking_id, photo_id, exc,
        )
        raise HTTPException(
            status_code=500,
            detail="Kimlik fotografi cozulemedi (anahtar veya butunluk hatasi).",
        ) from exc


def delete_id_photo(*, tenant_id: str, photo_id: str) -> bool:
    """Best-effort delete of a stored ID photo (used for orphan cleanup)."""
    try:
        path = _photo_path(tenant_id, photo_id)
    except HTTPException:
        return False
    try:
        if path.exists():
            path.unlink()
            return True
    except OSError as exc:
        logger.warning("Failed to delete ID photo %s: %s", photo_id, exc)
    return False

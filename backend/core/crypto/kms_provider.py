"""
AWS KMS Envelope Encryption Provider.

Uses AWS KMS for key management with local AES-256-GCM for data encryption.
This is the "envelope encryption" pattern recommended by AWS:

  1. Generate a data key from KMS (plaintext + encrypted copy)
  2. Encrypt data locally with the plaintext data key
  3. Store the encrypted data + encrypted data key together
  4. Discard the plaintext data key from memory
  5. On decrypt: ask KMS to decrypt the data key, then decrypt locally

Benefits:
  - Key material never leaves KMS HSM
  - Data keys are unique per encryption operation
  - KMS audit trail for all key operations
  - Automatic key rotation via KMS policies
  - No local key material to manage

Environment:
  AWS_KMS_KEY_ARN        — KMS key ARN for envelope encryption
  AWS_REGION             — AWS region
  KMS_GRANT_TOKENS       — optional, comma-separated grant tokens
  KMS_ENCRYPTION_CONTEXT — optional, JSON string for encryption context
"""
import base64
import json
import logging
import os
import secrets as stdlib_secrets
from dataclasses import dataclass
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger("core.crypto.kms")

NONCE_SIZE = 12  # 96-bit per NIST SP 800-38D
DATA_KEY_SPEC = "AES_256"


@dataclass(frozen=True)
class KMSEnvelope:
    """Envelope containing encrypted data + KMS-encrypted data key."""
    encrypted_data_key: bytes
    nonce: bytes
    ciphertext: bytes
    kms_key_arn: str
    encryption_context: dict[str, str]

    def serialize(self) -> str:
        """Serialize to a storable string: KMS1:base64(json)"""
        payload = {
            "edk": base64.b64encode(self.encrypted_data_key).decode(),
            "n": base64.b64encode(self.nonce).decode(),
            "ct": base64.b64encode(self.ciphertext).decode(),
            "arn": self.kms_key_arn,
            "ctx": self.encryption_context,
        }
        return "KMS1:" + base64.b64encode(json.dumps(payload).encode()).decode()

    @classmethod
    def deserialize(cls, envelope_str: str) -> "KMSEnvelope":
        """Deserialize from KMS1: string."""
        if not envelope_str.startswith("KMS1:"):
            raise ValueError("Not a KMS envelope (expected KMS1: prefix)")
        raw = base64.b64decode(envelope_str[5:])
        payload = json.loads(raw)
        return cls(
            encrypted_data_key=base64.b64decode(payload["edk"]),
            nonce=base64.b64decode(payload["n"]),
            ciphertext=base64.b64decode(payload["ct"]),
            kms_key_arn=payload["arn"],
            encryption_context=payload.get("ctx", {}),
        )


class KMSEnvelopeEncryption:
    """AWS KMS envelope encryption engine.

    Uses KMS GenerateDataKey for encrypt, KMS Decrypt for data key recovery.
    All data encryption/decryption happens locally with AES-256-GCM.
    """

    def __init__(
        self,
        kms_key_arn: str | None = None,
        region: str | None = None,
    ):
        self._kms_key_arn = kms_key_arn or os.environ.get("AWS_KMS_KEY_ARN", "")
        self._region = region or os.environ.get("AWS_REGION", "eu-west-1")
        self._client = None
        self._available = False

        if self._kms_key_arn:
            try:
                import boto3
                from botocore.config import Config as BotoConfig

                retry_config = BotoConfig(
                    retries={"max_attempts": 3, "mode": "adaptive"},
                    region_name=self._region,
                )
                self._client = boto3.client("kms", config=retry_config)
                self._available = True
                logger.info("KMS envelope encryption initialized: region=%s", self._region)
            except ImportError:
                logger.warning("boto3 not installed — KMS envelope encryption unavailable")
            except Exception as e:
                logger.warning("KMS client init failed: %s", e)

    @property
    def available(self) -> bool:
        return self._available

    def _build_encryption_context(
        self,
        tenant_id: str = "",
        provider: str = "",
        context_type: str = "secret",
    ) -> dict[str, str]:
        """Build KMS encryption context for AAD binding."""
        ctx = {"service": "syroce-pms", "type": context_type}
        if tenant_id:
            ctx["tenant_id"] = tenant_id
        if provider:
            ctx["provider"] = provider
        # Add custom context from env
        env_ctx = os.environ.get("KMS_ENCRYPTION_CONTEXT", "")
        if env_ctx:
            try:
                ctx.update(json.loads(env_ctx))
            except json.JSONDecodeError:
                pass
        return ctx

    def encrypt(
        self,
        plaintext: str,
        *,
        tenant_id: str = "",
        provider: str = "",
        context_type: str = "secret",
    ) -> str:
        """Encrypt using KMS envelope encryption.

        Returns a KMS1: envelope string.
        """
        if not self._available:
            raise RuntimeError("KMS envelope encryption not available")

        encryption_context = self._build_encryption_context(
            tenant_id=tenant_id,
            provider=provider,
            context_type=context_type,
        )

        # Generate data key from KMS
        response = self._client.generate_data_key(
            KeyId=self._kms_key_arn,
            KeySpec=DATA_KEY_SPEC,
            EncryptionContext=encryption_context,
        )

        plaintext_key = response["Plaintext"]
        encrypted_data_key = response["CiphertextBlob"]

        # Encrypt locally with the plaintext data key
        nonce = stdlib_secrets.token_bytes(NONCE_SIZE)
        aesgcm = AESGCM(plaintext_key)
        aad = json.dumps(encryption_context, sort_keys=True).encode()
        ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), aad)

        # Securely discard plaintext key
        plaintext_key = b"\x00" * len(plaintext_key)

        envelope = KMSEnvelope(
            encrypted_data_key=encrypted_data_key,
            nonce=nonce,
            ciphertext=ciphertext,
            kms_key_arn=self._kms_key_arn,
            encryption_context=encryption_context,
        )

        return envelope.serialize()

    def decrypt(self, envelope_str: str) -> str:
        """Decrypt a KMS1: envelope string."""
        if not self._available:
            raise RuntimeError("KMS envelope encryption not available")

        envelope = KMSEnvelope.deserialize(envelope_str)

        # Ask KMS to decrypt the data key
        response = self._client.decrypt(
            CiphertextBlob=envelope.encrypted_data_key,
            EncryptionContext=envelope.encryption_context,
        )
        plaintext_key = response["Plaintext"]

        # Decrypt locally
        aesgcm = AESGCM(plaintext_key)
        aad = json.dumps(envelope.encryption_context, sort_keys=True).encode()

        try:
            plaintext_bytes = aesgcm.decrypt(
                envelope.nonce, envelope.ciphertext, aad,
            )
        finally:
            plaintext_key = b"\x00" * len(plaintext_key)

        return plaintext_bytes.decode("utf-8")

    def is_kms_envelope(self, value: str) -> bool:
        """Check if a string is a KMS1: envelope."""
        return isinstance(value, str) and value.startswith("KMS1:")

    def health_check(self) -> dict[str, Any]:
        """Check KMS availability and key status."""
        if not self._available:
            return {
                "provider": "kms",
                "status": "unavailable",
                "reason": "KMS not configured or boto3 missing",
            }

        try:
            response = self._client.describe_key(KeyId=self._kms_key_arn)
            key_metadata = response.get("KeyMetadata", {})
            return {
                "provider": "kms",
                "status": "healthy",
                "key_arn": self._kms_key_arn,
                "key_state": key_metadata.get("KeyState", "unknown"),
                "key_usage": key_metadata.get("KeyUsage", "unknown"),
                "region": self._region,
                "encryption_algorithm": "AES-256-GCM",
                "key_spec": DATA_KEY_SPEC,
            }
        except Exception as e:
            return {
                "provider": "kms",
                "status": "unhealthy",
                "error": str(e),
                "key_arn": self._kms_key_arn,
                "region": self._region,
            }


# ── Singleton ──────────────────────────────────────────────────────

_kms_instance: KMSEnvelopeEncryption | None = None


def get_kms_encryption() -> KMSEnvelopeEncryption:
    """Get or create the singleton KMS envelope encryption instance."""
    global _kms_instance
    if _kms_instance is None:
        _kms_instance = KMSEnvelopeEncryption()
    return _kms_instance

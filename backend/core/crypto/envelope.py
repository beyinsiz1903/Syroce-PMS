"""
Versioned encryption envelope — SYR1: prefix.

Envelope format (serialized):
  SYR1:<base64(compact JSON)>

JSON structure:
  {
    "v":   1,                    # envelope version
    "alg": "AES-256-GCM",       # algorithm
    "kid": "v1",                 # key identifier
    "n":   "<base64 nonce>",     # 12-byte nonce
    "ct":  "<base64 ciphertext>", # ciphertext + GCM auth tag
    "af":  "<hex>"               # AAD fingerprint (first 16 hex chars of SHA-256)
  }

Design choices:
  - SYR1: prefix enables instant format detection with forward-compatible versioning
  - Compact JSON keys minimize storage overhead
  - AAD fingerprint is for debugging only — AAD is never stored, always reconstructed
"""
import base64
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Optional

from .errors import EnvelopeParseError

logger = logging.getLogger("core.crypto.envelope")

ENVELOPE_PREFIX = "SYR1:"
ENVELOPE_VERSION = 1
ALGORITHM = "AES-256-GCM"


@dataclass(frozen=True)
class EncryptionEnvelope:
    """Parsed encryption envelope."""
    version: int
    algorithm: str
    kid: str
    nonce: bytes
    ciphertext: bytes   # includes appended GCM auth tag
    aad_fingerprint: str

    def serialize(self) -> str:
        """Serialize to SYR1:<base64(json)> string."""
        payload = {
            "v": self.version,
            "alg": self.algorithm,
            "kid": self.kid,
            "n": base64.b64encode(self.nonce).decode("ascii"),
            "ct": base64.b64encode(self.ciphertext).decode("ascii"),
        }
        if self.aad_fingerprint:
            payload["af"] = self.aad_fingerprint
        raw_json = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        return ENVELOPE_PREFIX + base64.b64encode(raw_json).decode("ascii")

    @classmethod
    def deserialize(cls, data: str) -> "EncryptionEnvelope":
        """Parse a SYR1: prefixed envelope string."""
        if not data.startswith(ENVELOPE_PREFIX):
            raise EnvelopeParseError("missing_SYR1_prefix")
        try:
            raw = base64.b64decode(data[len(ENVELOPE_PREFIX):])
            obj = json.loads(raw)
        except Exception:
            raise EnvelopeParseError("invalid_base64_or_json")

        version = obj.get("v")
        if version != ENVELOPE_VERSION:
            raise EnvelopeParseError(f"unsupported_version_{version}")

        try:
            return cls(
                version=version,
                algorithm=obj["alg"],
                kid=obj["kid"],
                nonce=base64.b64decode(obj["n"]),
                ciphertext=base64.b64decode(obj["ct"]),
                aad_fingerprint=obj.get("af", ""),
            )
        except KeyError as e:
            raise EnvelopeParseError(f"missing_field_{e}")

    @classmethod
    def create(
        cls,
        kid: str,
        nonce: bytes,
        ciphertext: bytes,
        aad: Optional[bytes] = None,
    ) -> "EncryptionEnvelope":
        """Create a new envelope from encryption output."""
        aad_fp = ""
        if aad:
            aad_fp = hashlib.sha256(aad).hexdigest()[:16]
        return cls(
            version=ENVELOPE_VERSION,
            algorithm=ALGORITHM,
            kid=kid,
            nonce=nonce,
            ciphertext=ciphertext,
            aad_fingerprint=aad_fp,
        )


def is_envelope(data: str) -> bool:
    """Fast check: is this a SYR1: envelope?"""
    return isinstance(data, str) and data.startswith(ENVELOPE_PREFIX)

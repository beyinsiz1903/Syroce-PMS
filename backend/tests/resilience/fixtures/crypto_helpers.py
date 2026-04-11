"""
Crypto test helpers — isolated keyrings, AAD contexts, tampered data.

Provides deterministic crypto test scenarios without touching production keys.
"""
import os
import secrets
from typing import Tuple


def make_test_keyring(kid: str = "test-kid-v1") -> "KeyRing":
    """Create a test KeyRing with a random key."""
    from core.crypto.keys import KeyRing

    key = secrets.token_bytes(32)  # AES-256
    return KeyRing._from_test(current_key=key, kid=kid)


def make_dual_keyring(
    kid_current: str = "test-kid-v2",
    kid_previous: str = "test-kid-v1",
) -> Tuple["KeyRing", bytes, bytes]:
    """Create a dual-key KeyRing simulating key rotation.

    Returns:
        (keyring, current_key_bytes, previous_key_bytes)
    """
    from core.crypto.keys import KeyRing

    current_key = secrets.token_bytes(32)
    previous_key = secrets.token_bytes(32)
    keyring = KeyRing._from_test(
        current_key=current_key,
        kid=kid_current,
        previous_key=previous_key,
        previous_kid=kid_previous,
    )
    return keyring, current_key, previous_key


def make_aad_context(
    tenant_id: str = "chaos-test-t1",
    provider: str = "exely",
    property_id: str = "prop1",
) -> "AADContext":
    """Create a test AAD context."""
    from core.crypto.engine import AADContext

    return AADContext(
        tenant_id=tenant_id,
        provider=provider,
        property_id=property_id,
        environment="test",
        context_type="credential",
    )


def tamper_ciphertext(envelope_str: str) -> str:
    """Tamper with a SYR1: envelope to trigger GCM tag mismatch.

    Flips a byte in the base64-encoded ciphertext portion.
    """
    if not envelope_str.startswith("SYR1:"):
        raise ValueError("Not a SYR1 envelope")

    parts = envelope_str.split(":")
    if len(parts) < 4:
        raise ValueError("Malformed envelope")

    # Tamper with the ciphertext part (index 3)
    ct = list(parts[3])
    if len(ct) > 5:
        # Swap two characters to corrupt the ciphertext
        ct[4], ct[5] = ct[5], ct[4]
    parts[3] = "".join(ct)

    return ":".join(parts)

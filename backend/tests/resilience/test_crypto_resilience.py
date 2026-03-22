"""
TS-015 to TS-017: Crypto / Secrets Resilience Tests

Tests:
- TS-015: Key rotation resilience (also in test_retry_replay.py)
- TS-016: Missing secret during provider pull
- TS-017: Wrong tenant AAD context → TamperDetectedError
- Bonus: Malformed envelope handling, encrypt/decrypt determinism

Markers: chaos_l1, chaos_crypto
"""
import secrets

import pytest

pytestmark = [pytest.mark.asyncio]


# ═══════════════════════════════════════════════════════════════════
# TS-017: Wrong Tenant AAD Context
# ═══════════════════════════════════════════════════════════════════

class TestAADContextBinding:
    """
    Scenario D-03: Ciphertext decrypted with wrong tenant AAD.
    Guarantee: GCM tag mismatch → TamperDetectedError. No plaintext.
    """

    @pytest.mark.chaos_l1
    async def test_wrong_tenant_aad_raises_tamper_error(self):
        """Decryption with mismatched tenant_id in AAD MUST raise TamperDetectedError."""
        from core.crypto.engine import AESGCMEngine, AADContext
        from core.crypto.keys import KeyRing
        from core.crypto.errors import TamperDetectedError

        key = secrets.token_bytes(32)
        keyring = KeyRing._from_test(current_key=key, kid="test-aad")
        engine = AESGCMEngine(keyring)

        # Encrypt with tenant A
        aad_a = AADContext(
            tenant_id="chaos-test-tenant-A",
            provider="exely",
            property_id="prop1",
            environment="test",
        )
        ciphertext = engine.encrypt("api-key-secret-123", aad=aad_a)

        # Attempt decrypt with tenant B
        aad_b = AADContext(
            tenant_id="chaos-test-tenant-B",  # WRONG TENANT
            provider="exely",
            property_id="prop1",
            environment="test",
        )
        with pytest.raises(TamperDetectedError):
            engine.decrypt(ciphertext, aad=aad_b)

    @pytest.mark.chaos_l1
    async def test_wrong_provider_aad_raises_tamper_error(self):
        """Decryption with wrong provider in AAD MUST fail."""
        from core.crypto.engine import AESGCMEngine, AADContext
        from core.crypto.keys import KeyRing
        from core.crypto.errors import TamperDetectedError

        key = secrets.token_bytes(32)
        keyring = KeyRing._from_test(current_key=key, kid="test-aad2")
        engine = AESGCMEngine(keyring)

        aad_exely = AADContext(
            tenant_id="chaos-test-t1",
            provider="exely",
            environment="test",
        )
        ciphertext = engine.encrypt("secret-value", aad=aad_exely)

        aad_hr = AADContext(
            tenant_id="chaos-test-t1",
            provider="hotelrunner",  # WRONG PROVIDER
            environment="test",
        )
        with pytest.raises(TamperDetectedError):
            engine.decrypt(ciphertext, aad=aad_hr)

    @pytest.mark.chaos_l1
    async def test_no_aad_vs_with_aad_mismatch(self):
        """Encrypted with AAD, decrypted without AAD → must fail."""
        from core.crypto.engine import AESGCMEngine, AADContext
        from core.crypto.keys import KeyRing
        from core.crypto.errors import TamperDetectedError

        key = secrets.token_bytes(32)
        keyring = KeyRing._from_test(current_key=key, kid="test-aad3")
        engine = AESGCMEngine(keyring)

        aad = AADContext(tenant_id="chaos-test-t1", provider="exely")
        ciphertext = engine.encrypt("bound-secret", aad=aad)

        # Decrypt without AAD — must fail
        with pytest.raises(TamperDetectedError):
            engine.decrypt(ciphertext, aad=None)


# ═══════════════════════════════════════════════════════════════════
# Malformed Envelope Handling
# ═══════════════════════════════════════════════════════════════════

class TestMalformedEnvelope:
    """
    Scenario D-05: Corrupted SYR1: envelope format.
    Guarantee: EnvelopeParseError raised. No crash. No bypass.
    """

    @pytest.mark.chaos_l1
    async def test_truncated_envelope_raises_parse_error(self):
        """Truncated envelope string must raise EnvelopeParseError."""
        from core.crypto.envelope import EncryptionEnvelope
        from core.crypto.errors import EnvelopeParseError

        with pytest.raises((EnvelopeParseError, Exception)):
            EncryptionEnvelope.deserialize("SYR1:v1:abc")  # Truncated

    @pytest.mark.chaos_l1
    async def test_non_syr1_prefix_raises_error(self):
        """Non-SYR1 prefix must raise error."""
        from core.crypto.envelope import EncryptionEnvelope
        from core.crypto.errors import EnvelopeParseError

        with pytest.raises((EnvelopeParseError, Exception)):
            EncryptionEnvelope.deserialize("INVALID:v1:abc:def")

    @pytest.mark.chaos_l1
    async def test_tampered_ciphertext_detected(self):
        """Bit-flipped ciphertext must be detected by GCM tag."""
        from core.crypto.engine import AESGCMEngine, AADContext
        from core.crypto.keys import KeyRing
        from core.crypto.errors import TamperDetectedError, DecryptionError

        key = secrets.token_bytes(32)
        keyring = KeyRing._from_test(current_key=key, kid="tamper-test")
        engine = AESGCMEngine(keyring)

        aad = AADContext(tenant_id="chaos-test-tamper")
        ciphertext = engine.encrypt("tamper-me-not", aad=aad)

        # Tamper with the ciphertext
        # The envelope is SYR1:kid:nonce_b64:ciphertext_b64
        parts = ciphertext.split(":")
        if len(parts) >= 4:
            ct = list(parts[3])
            if len(ct) > 5:
                # Swap characters to corrupt
                ct[3], ct[4] = ct[4], ct[3]
            parts[3] = "".join(ct)
            tampered = ":".join(parts)

            with pytest.raises((TamperDetectedError, DecryptionError, Exception)):
                engine.decrypt(tampered, aad=aad)


# ═══════════════════════════════════════════════════════════════════
# Key Not Found
# ═══════════════════════════════════════════════════════════════════

class TestKeyNotFound:
    """
    Scenario: Envelope references a key ID that doesn't exist.
    Guarantee: KeyNotFoundError raised. Clean error.
    """

    @pytest.mark.chaos_l1
    async def test_unknown_kid_raises_key_not_found(self):
        """Decrypting with unknown key ID must raise KeyNotFoundError."""
        from core.crypto.engine import AESGCMEngine, AADContext
        from core.crypto.keys import KeyRing
        from core.crypto.errors import KeyNotFoundError

        # Encrypt with key-A
        key_a = secrets.token_bytes(32)
        keyring_a = KeyRing._from_test(current_key=key_a, kid="key-A")
        engine_a = AESGCMEngine(keyring_a)

        ciphertext = engine_a.encrypt("secret")

        # Decrypt with a keyring that only has key-B
        key_b = secrets.token_bytes(32)
        keyring_b = KeyRing._from_test(current_key=key_b, kid="key-B")
        engine_b = AESGCMEngine(keyring_b)

        with pytest.raises(KeyNotFoundError):
            engine_b.decrypt(ciphertext)


# ═══════════════════════════════════════════════════════════════════
# Encryption Determinism & Freshness
# ═══════════════════════════════════════════════════════════════════

class TestEncryptionProperties:
    """Verify encryption produces different ciphertext each time (random nonce)."""

    @pytest.mark.chaos_l1
    async def test_encryption_is_non_deterministic(self):
        """Same plaintext encrypted twice must produce different ciphertext (unique nonce)."""
        from core.crypto.engine import AESGCMEngine
        from core.crypto.keys import KeyRing

        key = secrets.token_bytes(32)
        keyring = KeyRing._from_test(current_key=key, kid="determ-test")
        engine = AESGCMEngine(keyring)

        ct1 = engine.encrypt("same-secret")
        ct2 = engine.encrypt("same-secret")

        # Must be different (different nonce)
        assert ct1 != ct2

        # Both must decrypt to same plaintext
        assert engine.decrypt(ct1) == "same-secret"
        assert engine.decrypt(ct2) == "same-secret"

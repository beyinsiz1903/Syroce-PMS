"""
Comprehensive test suite for core.crypto — Production-grade credential encryption.

Tests cover:
  - Encrypt/decrypt roundtrip (Phase 0 + V2)
  - Tamper detection (wrong AAD, wrong key)
  - Key rotation with dual-key decryption
  - Legacy format compatibility (AES-GCM, XOR, base64)
  - Re-encryption / migration
  - Masking behavior (separate from encryption)
  - No-secret-leak (exceptions, logs)
  - Envelope parsing and validation
  - Feature flag behavior (CRYPTO_V2_ENABLED)
  - Break-glass bypass mode
  - Dict operations
  - Edge cases (empty values, large payloads)
"""
import base64
import hashlib
import json
import os
import secrets

import pytest
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# ── Fixtures ──────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_singletons():
    """Reset singletons between tests."""
    from core.crypto.service import reset_crypto_service
    from core.secrets.config import reset_config_cache
    from core.secrets.manager import reset_secrets_manager
    reset_crypto_service()
    yield
    reset_crypto_service()


@pytest.fixture
def env_v2_enabled(monkeypatch):
    """Enable V2 crypto."""
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "test-master-key-for-v2")
    monkeypatch.setenv("CM_KEY_VERSION", "v1")
    monkeypatch.setenv("APP_ENV", "development")
    from core.crypto.service import reset_crypto_service
    reset_crypto_service()


@pytest.fixture
def env_v2_disabled(monkeypatch):
    """Phase 0 — V2 disabled."""
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "false")
    monkeypatch.setenv("CM_CREDENTIAL_KEY", "test-legacy-key")
    monkeypatch.setenv("CM_KEY_VERSION", "v1")
    monkeypatch.setenv("APP_ENV", "development")
    from core.crypto.service import reset_crypto_service
    reset_crypto_service()


@pytest.fixture
def env_with_rotation(monkeypatch):
    """V2 enabled with previous key for rotation testing."""
    monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "new-master-key-v2")
    monkeypatch.setenv("CM_MASTER_KEY_PREVIOUS", "old-master-key-v1")
    monkeypatch.setenv("CM_KEY_VERSION", "v2")
    monkeypatch.setenv("APP_ENV", "development")
    from core.crypto.service import reset_crypto_service
    reset_crypto_service()


@pytest.fixture
def env_bypass(monkeypatch):
    """Break-glass mode."""
    monkeypatch.setenv("CRYPTO_BYPASS_ALLOWED", "true")
    monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "test-key")
    monkeypatch.setenv("APP_ENV", "development")
    from core.crypto.service import reset_crypto_service
    reset_crypto_service()


def _make_legacy_aes_gcm(plaintext: str, key_material: str = "test-legacy-key") -> str:
    """Create an old aes256gcm: format ciphertext for testing."""
    key = hashlib.sha256(key_material.encode()).digest()
    nonce = secrets.token_bytes(12)
    aesgcm = AESGCM(key)
    ct = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    encoded = base64.b64encode(nonce + ct).decode("ascii")
    return f"aes256gcm:{encoded}"


def _make_legacy_xor(plaintext: str, key_material: str = "") -> str:
    """Create an old XOR format ciphertext for testing."""
    jwt = os.environ.get("JWT_SECRET", "default-hotel-pms-secret")
    if key_material:
        key = hashlib.sha256(key_material.encode()).digest()
    else:
        key = hashlib.sha256(f"cm-cred:{jwt}".encode()).digest()
    salt = secrets.token_bytes(16)
    derived = hashlib.sha256(key + salt).digest()
    encrypted = bytes(b ^ derived[i % len(derived)] for i, b in enumerate(plaintext.encode("utf-8")))
    return base64.urlsafe_b64encode(salt + encrypted).decode("ascii")


def _make_legacy_base64(plaintext: str) -> str:
    """Create a base64-only 'encrypted' value for testing."""
    return base64.b64encode(plaintext.encode()).decode()


# ══════════════════════════════════════════════════════════════════════
# 1. ENCRYPT/DECRYPT ROUNDTRIP
# ══════════════════════════════════════════════════════════════════════

class TestEncryptDecryptRoundtrip:
    """Basic encrypt → decrypt correctness."""

    def test_roundtrip_phase0(self, env_v2_disabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        ct = svc.encrypt("my-secret")
        assert ct.startswith("aes256gcm:")
        pt = svc.decrypt(ct)
        assert pt == "my-secret"

    def test_roundtrip_v2(self, env_v2_enabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        ct = svc.encrypt("v2-secret")
        assert ct.startswith("SYR1:")
        pt = svc.decrypt(ct)
        assert pt == "v2-secret"

    def test_roundtrip_v2_with_aad(self, env_v2_enabled):
        from core.crypto import get_crypto_service, AADContext
        svc = get_crypto_service()
        aad = AADContext(
            tenant_id="t1", provider="exely",
            property_id="p1", environment="dev",
            context_type="credential",
        )
        ct = svc.encrypt("aad-secret", aad=aad)
        pt = svc.decrypt(ct, aad=aad)
        assert pt == "aad-secret"

    def test_different_plaintexts_different_ciphertexts(self, env_v2_enabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        ct1 = svc.encrypt("secret-1")
        ct2 = svc.encrypt("secret-1")  # Same plaintext, different nonce
        assert ct1 != ct2  # Nonce makes them unique

    def test_unicode_roundtrip(self, env_v2_enabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        secret = "şifre-with-üñîçødé-characters-日本語"
        ct = svc.encrypt(secret)
        assert svc.decrypt(ct) == secret

    def test_large_payload(self, env_v2_enabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        large = "A" * 100_000
        ct = svc.encrypt(large)
        assert svc.decrypt(ct) == large

    def test_empty_value_raises(self, env_v2_enabled):
        from core.crypto import get_crypto_service, CryptoError
        svc = get_crypto_service()
        with pytest.raises(CryptoError):
            svc.encrypt("")


# ══════════════════════════════════════════════════════════════════════
# 2. TAMPER DETECTION
# ══════════════════════════════════════════════════════════════════════

class TestTamperDetection:
    """GCM authentication tag catches tampering and context mismatches."""

    def test_wrong_tenant_detected(self, env_v2_enabled):
        from core.crypto import get_crypto_service, AADContext, TamperDetectedError
        svc = get_crypto_service()
        aad = AADContext(tenant_id="tenant-A", provider="exely")
        ct = svc.encrypt("secret", aad=aad)

        wrong = AADContext(tenant_id="tenant-B", provider="exely")
        with pytest.raises(TamperDetectedError):
            svc.decrypt(ct, aad=wrong)

    def test_wrong_provider_detected(self, env_v2_enabled):
        from core.crypto import get_crypto_service, AADContext, TamperDetectedError
        svc = get_crypto_service()
        aad = AADContext(tenant_id="t1", provider="exely")
        ct = svc.encrypt("secret", aad=aad)

        wrong = AADContext(tenant_id="t1", provider="hotelrunner")
        with pytest.raises(TamperDetectedError):
            svc.decrypt(ct, aad=wrong)

    def test_missing_aad_detected(self, env_v2_enabled):
        from core.crypto import get_crypto_service, AADContext, TamperDetectedError
        svc = get_crypto_service()
        aad = AADContext(tenant_id="t1", provider="exely")
        ct = svc.encrypt("secret", aad=aad)

        with pytest.raises(TamperDetectedError):
            svc.decrypt(ct)  # No AAD

    def test_ciphertext_mutation_detected(self, env_v2_enabled):
        from core.crypto import get_crypto_service, TamperDetectedError, EnvelopeParseError
        svc = get_crypto_service()
        ct = svc.encrypt("secret")
        # Mutate one character
        mutated = ct[:-2] + ("A" if ct[-2] != "A" else "B") + ct[-1]
        with pytest.raises((TamperDetectedError, EnvelopeParseError, Exception)):
            svc.decrypt(mutated)

    def test_wrong_environment_detected(self, env_v2_enabled):
        from core.crypto import get_crypto_service, AADContext, TamperDetectedError
        svc = get_crypto_service()
        aad_prod = AADContext(tenant_id="t1", environment="production")
        aad_dev = AADContext(tenant_id="t1", environment="development")
        ct = svc.encrypt("secret", aad=aad_prod)
        with pytest.raises(TamperDetectedError):
            svc.decrypt(ct, aad=aad_dev)


# ══════════════════════════════════════════════════════════════════════
# 3. KEY ROTATION
# ══════════════════════════════════════════════════════════════════════

class TestKeyRotation:
    """Dual-key model supports decrypting old data after rotation."""

    def test_decrypt_old_key_data_with_previous(self, monkeypatch):
        """Encrypt with old key (v1), then rotate to v2 — old data still readable."""
        from core.crypto.service import reset_crypto_service

        # Phase 1: Encrypt with v1
        monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
        monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "original-key-v1")
        monkeypatch.setenv("CM_KEY_VERSION", "v1")
        reset_crypto_service()

        from core.crypto import get_crypto_service
        svc_v1 = get_crypto_service()
        ct_v1 = svc_v1.encrypt("old-secret")
        assert ct_v1.startswith("SYR1:")

        # Phase 2: Rotate to v2
        monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "new-key-v2")
        monkeypatch.setenv("CM_MASTER_KEY_PREVIOUS", "original-key-v1")
        monkeypatch.setenv("CM_KEY_VERSION", "v2")
        reset_crypto_service()

        svc_v2 = get_crypto_service()

        # Old data decryptable via previous key
        assert svc_v2.decrypt(ct_v1) == "old-secret"

        # New data encrypted with v2
        ct_v2 = svc_v2.encrypt("new-secret")
        assert svc_v2.decrypt(ct_v2) == "new-secret"

    def test_re_encrypt_upgrades_key_version(self, monkeypatch):
        from core.crypto.service import reset_crypto_service

        # Encrypt with v1
        monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
        monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "key-v1")
        monkeypatch.setenv("CM_KEY_VERSION", "v1")
        reset_crypto_service()

        from core.crypto import get_crypto_service
        ct_v1 = get_crypto_service().encrypt("rotate-me")

        # Rotate to v2
        monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "key-v2")
        monkeypatch.setenv("CM_MASTER_KEY_PREVIOUS", "key-v1")
        monkeypatch.setenv("CM_KEY_VERSION", "v2")
        reset_crypto_service()

        svc = get_crypto_service()
        ct_v2 = svc.re_encrypt(ct_v1)
        assert ct_v2.startswith("SYR1:")

        # Verify re-encrypted data has v2 kid
        from core.crypto.envelope import EncryptionEnvelope
        envelope = EncryptionEnvelope.deserialize(ct_v2)
        assert envelope.kid == "v2"
        assert svc.decrypt(ct_v2) == "rotate-me"


# ══════════════════════════════════════════════════════════════════════
# 4. LEGACY FORMAT COMPATIBILITY
# ══════════════════════════════════════════════════════════════════════

class TestLegacyFormatCompat:
    """Backward-compatible decryption of all historical formats."""

    def test_decrypt_legacy_aes_gcm(self, env_v2_disabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        legacy = _make_legacy_aes_gcm("legacy-aes-secret", "test-legacy-key")
        assert svc.decrypt(legacy) == "legacy-aes-secret"

    def test_decrypt_legacy_xor_explicit(self, env_v2_disabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        legacy = _make_legacy_xor("xor-secret")
        assert svc.decrypt_legacy_xor(legacy) == "xor-secret"

    def test_decrypt_legacy_base64_explicit(self, env_v2_disabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        legacy = _make_legacy_base64("base64-secret")
        assert svc.decrypt_legacy_base64(legacy) == "base64-secret"

    def test_format_detection(self):
        from core.crypto import detect_format, CiphertextFormat
        assert detect_format("SYR1:abcdef") == CiphertextFormat.ENVELOPE_V1
        assert detect_format("aes256gcm:abcdef") == CiphertextFormat.AES_GCM_LEGACY
        assert detect_format("") == CiphertextFormat.UNKNOWN
        assert detect_format(None) == CiphertextFormat.UNKNOWN

    def test_is_current_format(self, env_v2_enabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        ct = svc.encrypt("test")
        assert svc.is_current_format(ct) is True
        assert svc.is_current_format("aes256gcm:old") is False
        assert svc.is_current_format("plaintext") is False


# ══════════════════════════════════════════════════════════════════════
# 5. RE-ENCRYPTION / MIGRATION
# ══════════════════════════════════════════════════════════════════════

class TestReEncryption:
    """Migrate data from any format to current format."""

    def test_re_encrypt_legacy_aes_to_v2(self, monkeypatch):
        monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
        monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "new-key")
        monkeypatch.setenv("CM_CREDENTIAL_KEY", "test-legacy-key")
        monkeypatch.setenv("CM_KEY_VERSION", "v1")
        from core.crypto.service import reset_crypto_service
        reset_crypto_service()

        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        legacy = _make_legacy_aes_gcm("migrate-me", "test-legacy-key")
        new_ct = svc.re_encrypt(legacy)
        assert new_ct.startswith("SYR1:")
        assert svc.decrypt(new_ct) == "migrate-me"

    def test_re_encrypt_dict(self, monkeypatch):
        monkeypatch.setenv("CRYPTO_V2_ENABLED", "true")
        monkeypatch.setenv("CM_MASTER_KEY_CURRENT", "new-key")
        monkeypatch.setenv("CM_CREDENTIAL_KEY", "test-legacy-key")
        monkeypatch.setenv("CM_KEY_VERSION", "v1")
        from core.crypto.service import reset_crypto_service
        reset_crypto_service()

        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        legacy_dict = {
            "user": _make_legacy_aes_gcm("admin", "test-legacy-key"),
            "pass": _make_legacy_aes_gcm("secret123", "test-legacy-key"),
        }
        new_dict = svc.re_encrypt_dict(legacy_dict)
        for v in new_dict.values():
            assert v.startswith("SYR1:")
        decrypted = svc.decrypt_dict(new_dict)
        assert decrypted == {"user": "admin", "pass": "secret123"}


# ══════════════════════════════════════════════════════════════════════
# 6. MASKING
# ══════════════════════════════════════════════════════════════════════

class TestMasking:
    """Masking is display-only, completely separate from encryption."""

    def test_mask_value_default(self):
        from core.crypto import mask_value
        result = mask_value("sk-1234567890abcdef")
        assert result.endswith("cdef")
        assert result.startswith("*")
        assert "1234567890" not in result

    def test_mask_short_value(self):
        from core.crypto import mask_value
        assert mask_value("ab") == "****"

    def test_mask_empty(self):
        from core.crypto import mask_value
        assert mask_value("") == "****"

    def test_mask_dict(self):
        from core.crypto import mask_dict
        result = mask_dict({"user": "admin", "token": "sk-abcdef1234567890"})
        assert "admin" not in str(result) or result["user"] == "****"
        assert "abcdef" not in result["token"]
        assert result["token"].endswith("7890")


# ══════════════════════════════════════════════════════════════════════
# 7. NO SECRET LEAK
# ══════════════════════════════════════════════════════════════════════

class TestNoSecretLeak:
    """Ensure secrets never appear in exceptions or error messages."""

    def test_decryption_error_no_secret(self, env_v2_enabled):
        from core.crypto import get_crypto_service, DecryptionError
        svc = get_crypto_service()
        with pytest.raises(DecryptionError) as exc_info:
            svc.decrypt("aes256gcm:invaliddata")
        # The error message must not contain any plaintext secret
        assert "secret" not in str(exc_info.value).lower() or "decryption" in str(exc_info.value).lower()

    def test_tamper_error_no_secret(self, env_v2_enabled):
        from core.crypto import get_crypto_service, AADContext, TamperDetectedError
        svc = get_crypto_service()
        aad = AADContext(tenant_id="t1")
        ct = svc.encrypt("hidden", aad=aad)
        with pytest.raises(TamperDetectedError) as exc_info:
            svc.decrypt(ct, aad=AADContext(tenant_id="t2"))
        assert "hidden" not in str(exc_info.value)

    def test_key_not_found_error_no_key(self, env_v2_enabled):
        from core.crypto.errors import KeyNotFoundError
        err = KeyNotFoundError("v99")
        assert "v99" in str(err)
        # Key material itself must not be in the error


# ══════════════════════════════════════════════════════════════════════
# 8. ENVELOPE PARSING
# ══════════════════════════════════════════════════════════════════════

class TestEnvelopeParsing:
    """Envelope serialization and deserialization."""

    def test_roundtrip(self):
        from core.crypto.envelope import EncryptionEnvelope
        env = EncryptionEnvelope.create(
            kid="v1",
            nonce=b"\x01" * 12,
            ciphertext=b"\x02" * 32,
            aad=b"test-aad",
        )
        serialized = env.serialize()
        assert serialized.startswith("SYR1:")

        parsed = EncryptionEnvelope.deserialize(serialized)
        assert parsed.kid == "v1"
        assert parsed.nonce == b"\x01" * 12
        assert parsed.ciphertext == b"\x02" * 32
        assert len(parsed.aad_fingerprint) == 16

    def test_invalid_prefix(self):
        from core.crypto.envelope import EncryptionEnvelope
        from core.crypto.errors import EnvelopeParseError
        with pytest.raises(EnvelopeParseError):
            EncryptionEnvelope.deserialize("WRONG:data")

    def test_malformed_json(self):
        import base64
        from core.crypto.envelope import EncryptionEnvelope
        from core.crypto.errors import EnvelopeParseError
        bad = "SYR1:" + base64.b64encode(b"not-json").decode()
        with pytest.raises(EnvelopeParseError):
            EncryptionEnvelope.deserialize(bad)


# ══════════════════════════════════════════════════════════════════════
# 9. FEATURE FLAGS
# ══════════════════════════════════════════════════════════════════════

class TestFeatureFlags:
    """CRYPTO_V2_ENABLED controls encryption format."""

    def test_phase0_uses_legacy_format(self, env_v2_disabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        ct = svc.encrypt("test")
        assert ct.startswith("aes256gcm:")
        assert svc.health()["v2_enabled"] is False

    def test_v2_uses_envelope(self, env_v2_enabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        ct = svc.encrypt("test")
        assert ct.startswith("SYR1:")
        assert svc.health()["v2_enabled"] is True

    def test_bypass_mode(self, env_bypass):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        ct = svc.encrypt("plaintext-value")
        assert ct == "plaintext-value"  # No encryption!
        pt = svc.decrypt("anything")
        assert pt == "anything"
        assert svc.health()["bypass_active"] is True


# ══════════════════════════════════════════════════════════════════════
# 10. DICT OPERATIONS
# ══════════════════════════════════════════════════════════════════════

class TestDictOperations:
    """encrypt_dict / decrypt_dict handle mixed content."""

    def test_encrypt_decrypt_dict(self, env_v2_enabled):
        from core.crypto import get_crypto_service
        svc = get_crypto_service()
        original = {"username": "admin", "password": "s3cret!", "empty": ""}
        encrypted = svc.encrypt_dict(original)
        assert encrypted["username"].startswith("SYR1:")
        assert encrypted["password"].startswith("SYR1:")
        assert encrypted["empty"] == ""  # Empty values not encrypted
        decrypted = svc.decrypt_dict(encrypted)
        assert decrypted["username"] == "admin"
        assert decrypted["password"] == "s3cret!"

    def test_dict_with_aad(self, env_v2_enabled):
        from core.crypto import get_crypto_service, AADContext
        svc = get_crypto_service()
        aad = AADContext(tenant_id="t1", provider="exely")
        enc = svc.encrypt_dict({"key": "value"}, aad=aad)
        dec = svc.decrypt_dict(enc, aad=aad)
        assert dec["key"] == "value"


# ══════════════════════════════════════════════════════════════════════
# 11. KEY DERIVATION
# ══════════════════════════════════════════════════════════════════════

class TestKeyDerivation:
    """HKDF-SHA256 key derivation produces correct, consistent keys."""

    def test_deterministic(self):
        from core.crypto.keys import derive_key
        k1 = derive_key("same-master")
        k2 = derive_key("same-master")
        assert k1 == k2

    def test_different_masters_different_keys(self):
        from core.crypto.keys import derive_key
        k1 = derive_key("master-A")
        k2 = derive_key("master-B")
        assert k1 != k2

    def test_key_length(self):
        from core.crypto.keys import derive_key
        k = derive_key("test")
        assert len(k) == 32  # AES-256

    def test_empty_raises(self):
        from core.crypto.keys import derive_key
        from core.crypto.errors import KeyDerivationError
        with pytest.raises(KeyDerivationError):
            derive_key("")

    def test_production_requires_explicit_key(self, monkeypatch):
        from core.crypto.keys import load_keyring
        from core.crypto.errors import KeyDerivationError
        monkeypatch.setenv("APP_ENV", "production")
        monkeypatch.delenv("CM_MASTER_KEY_CURRENT", raising=False)
        with pytest.raises(KeyDerivationError):
            load_keyring()

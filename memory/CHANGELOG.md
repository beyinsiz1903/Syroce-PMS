# Syroce PMS — Changelog

## [2026-03-22] SEC-002: Production-Grade Encryption Refactor

### Added
- `core/crypto/` module — complete AES-256-GCM encryption engine
  - HKDF-SHA256 key derivation (RFC 5869)
  - SYR1: versioned envelope format with compact JSON
  - AAD context binding (tenant_id|provider|property_id|env|context_type)
  - Dual-key KeyRing for seamless key rotation
  - LegacyDecryptor for all historical formats (XOR, old AES-GCM, base64)
  - Feature flags: CRYPTO_V2_ENABLED, CRYPTO_BYPASS_ALLOWED
  - CredentialEncryptionService — single encryption boundary
  - Typed exceptions: DecryptionError, TamperDetectedError, KeyNotFoundError
  - Display masking separated from encryption
- `scripts/migrate_crypto.py` — bulk re-encryption migration script
- `docs/ENCRYPTION_ARCHITECTURE.md` — algorithm, envelope, key management docs
- `docs/CRYPTO_ROLLOUT.md` — phased rollout plan
- `docs/CRYPTO_SECURITY_REVIEW.md` — risk assessment and compliance notes
- `tests/test_crypto_engine.py` — 41 unit tests
- `tests/test_crypto_refactor_api.py` — 18 API integration tests (by testing agent)

### Changed (Refactored — backward compatible)
- `domains/channel_manager/encryption.py` → delegates to core.crypto
- `domains/channel_manager/credential_vault.py` → delegates to core.crypto
- `channel_manager/infrastructure/encryption_service.py` → delegates to core.crypto
- `channel_manager/infrastructure/credential_vault.py` → delegates to core.crypto
- `modules/security_hardening/credential_vault.py` → real encryption (was base64)
- `core/secrets/local_provider.py` → uses core.crypto

### Security Improvements
- Eliminated XOR obfuscation used as "encryption"
- Eliminated base64 encoding used as "encryption"
- Added AAD context binding (cross-tenant credential theft prevented)
- Added key versioning in ciphertext (rotation support)
- Added HKDF key derivation (replaces raw SHA-256)
- Decryption failures now always raise (never return empty string)
- Production startup fails loudly if no master key configured

### Environment
- Added: CM_MASTER_KEY_CURRENT, CM_KEY_VERSION, CRYPTO_V2_ENABLED, CRYPTO_BYPASS_ALLOWED
- Preserved: CM_CREDENTIAL_KEY (for legacy decryption during migration)

---

## [2026-03-22] SEC-001: Secrets Management Architecture

### Added
- `core/secrets/` module with provider abstraction
- AWS Secrets Manager backend, Local Dev backend, Vault placeholder
- Secrets naming convention, access audit logging
- Migration script `scripts/migrate_secrets.py`
- Documentation: SECRETS_ARCHITECTURE.md, SECRETS_ROLLOUT.md, SECRETS_SECURITY_CHECKLIST.md
- 35 unit tests + 11 API integration tests

### Changed
- hotelrunner_router.py, exely_router.py → use SecretsManager
- startup.py → secrets validation on boot

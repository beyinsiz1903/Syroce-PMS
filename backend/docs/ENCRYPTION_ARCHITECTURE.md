# Encryption Architecture — core/crypto

## 1. Algorithm Choice

**AES-256-GCM** (Authenticated Encryption with Associated Data)

- **Why AES-256-GCM over Fernet:**
  - Explicit nonce/IV control (no hidden nonce reuse risk)
  - Associated Authenticated Data (AAD) for context binding
  - Standard AEAD primitive, not a wrapper
  - Compatible with external KMS backends (AWS KMS, HSM)
  - No dependency on Fernet's token format

- **Library:** `cryptography.hazmat.primitives.ciphers.aead.AESGCM`
- **Nonce:** 96-bit (12 bytes), cryptographically random per encryption
- **Auth tag:** 128-bit, appended to ciphertext by AESGCM

## 2. Key Derivation

**HKDF-SHA256** (HMAC-based Key Derivation Function)

```
Master Key (from env) → HKDF(salt, info) → 256-bit AES key
```

- **Salt:** `syroce-credential-encryption-salt-v1` (fixed, never changes)
- **Info:** `aes-256-gcm-key` (purpose binding)
- **Input:** `CM_MASTER_KEY_CURRENT` environment variable

Why HKDF over raw SHA-256:
- Purpose separation (info parameter)
- Salt provides domain separation
- Produces cryptographically uniform output
- Standard (RFC 5869)

## 3. Envelope Format

```
SYR1:<base64(compact JSON)>
```

JSON structure:
```json
{
  "v":   1,                     // envelope version
  "alg": "AES-256-GCM",        // algorithm
  "kid": "v1",                  // key identifier
  "n":   "<base64 nonce>",      // 12-byte nonce
  "ct":  "<base64 ciphertext>", // ciphertext + GCM tag
  "af":  "<hex>"                // AAD fingerprint (SHA-256[:16])
}
```

Design decisions:
- **SYR1:** prefix enables instant format detection, version-embedded, forward-compatible
- Compact JSON keys minimize storage overhead
- **AAD fingerprint** is for debugging only — AAD is never stored in the envelope
- Base64 encoding ensures safe storage in any text field

## 4. Associated Authenticated Data (AAD)

Format: `tenant_id|provider|property_id|environment|context_type`

Example: `t_abc123|exely|hotel_501694|production|credential`

Rules:
- AAD is **deterministic** — reconstructed at decrypt time from context
- AAD is **never stored** alongside the ciphertext
- Wrong AAD → GCM tag mismatch → `TamperDetectedError`
- Prevents credential theft via database record swap between tenants

Fields:
| Field | Purpose |
|-------|---------|
| `tenant_id` | Tenant isolation — ciphertext bound to tenant |
| `provider` | Provider isolation — Exely creds can't be used as HotelRunner |
| `property_id` | Property isolation |
| `environment` | Env isolation — prod creds invalid in staging |
| `context_type` | Purpose binding — credential, token, api_key |

## 5. Key Management Model

### Environment Variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `CM_MASTER_KEY_CURRENT` | YES (prod) | Active encryption key |
| `CM_MASTER_KEY_PREVIOUS` | No | Previous key for rotation decryption |
| `CM_KEY_VERSION` | No (default: v1) | Current key identifier |
| `CM_CREDENTIAL_KEY` | No | Legacy key for migration decryption |
| `CRYPTO_V2_ENABLED` | No (default: false) | Enable SYR1 envelope format |
| `CRYPTO_BYPASS_ALLOWED` | No (default: false) | Emergency bypass |

### Dual-Key Model

```
KeyRing {
  current_kid: "v2"
  current_key: HKDF(CM_MASTER_KEY_CURRENT)   ← encrypt + decrypt
  previous_key: HKDF(CM_MASTER_KEY_PREVIOUS)  ← decrypt only
}
```

When decrypting:
1. Read `kid` from envelope
2. If `kid == current_kid` → use current key
3. Else → use previous key
4. If no previous key → `KeyNotFoundError`

## 6. Rotation Strategy

### Step 1: Generate new key
```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

### Step 2: Update environment
```
CM_MASTER_KEY_CURRENT=<new key>
CM_MASTER_KEY_PREVIOUS=<old CM_MASTER_KEY_CURRENT>
CM_KEY_VERSION=v2
```

### Step 3: Deploy
All new encryptions use v2. Old v1 data still decryptable via previous key.

### Step 4: Bulk re-encryption
```bash
python scripts/migrate_crypto.py --all --force-v2
```

### Step 5: Cleanup
```
CM_MASTER_KEY_PREVIOUS=  # Remove after all data re-encrypted
```

## 7. Migration Approach

### Legacy Formats Supported

| Format | Prefix | Key Derivation | Source |
|--------|--------|---------------|--------|
| SYR1 envelope | `SYR1:` | HKDF-SHA256 | New system |
| AES-GCM legacy | `aes256gcm:` | SHA-256(CM_CREDENTIAL_KEY) | infrastructure/encryption_service.py |
| XOR obfuscation | (none, base64url) | SHA-256(CM_ENCRYPTION_KEY or JWT_SECRET) | domains/encryption.py |
| Base64 plain | (none, base64) | None (encoding only) | modules/credential_vault.py |

### Phased Migration

**Phase 0:** `CRYPTO_V2_ENABLED=false`
- Deploy new code
- All encryption uses old format (aes256gcm:)
- All decryption supports all formats
- Zero risk — behavior identical to before

**Phase 1:** `CRYPTO_V2_ENABLED=true`
- New writes use SYR1 envelope
- Old reads still work (dual-read)
- Run `migrate_crypto.py --dry-run` to assess scope

**Phase 2:** Run migration
- `migrate_crypto.py --all` re-encrypts everything
- Verify with `--dry-run` showing 0 remaining

**Phase 3:** Cleanup
- Remove `CM_CREDENTIAL_KEY` from environment
- Remove legacy code paths (after monitoring period)

## 8. Failure Handling

| Scenario | Behavior | Exception |
|----------|----------|-----------|
| Wrong key | GCM tag fails | `TamperDetectedError` |
| Wrong AAD | GCM tag fails | `TamperDetectedError` |
| Tampered ciphertext | GCM tag fails | `TamperDetectedError` |
| Unknown key ID | Key lookup fails | `KeyNotFoundError` |
| Malformed envelope | JSON parse fails | `EnvelopeParseError` |
| Empty input | Rejected immediately | `CryptoError` |
| Legacy format | Delegated to LegacyDecryptor | `DecryptionError` on failure |
| Bypass mode | No encryption/decryption | Value returned as-is |

**Critical rule:** Decryption failure NEVER returns empty string. Always raises.

## 9. Security Boundaries

- Encryption happens **before** persistence (in service layer)
- Decryption happens **only** at controlled access points (service layer)
- No plaintext in: logs, exceptions, audit records, API responses
- Single encryption boundary: `core/crypto/service.py`
- No router, worker, or provider directly handles crypto

## 10. Module Structure

```
core/crypto/
├── __init__.py       # Public API exports
├── errors.py         # Typed exception hierarchy
├── keys.py           # HKDF key derivation, KeyRing, env loading
├── envelope.py       # SYR1 versioned envelope format
├── engine.py         # AES-256-GCM engine with AAD
├── masking.py        # Display masking (NOT encryption)
├── migration.py      # Legacy format detection + decryption
└── service.py        # CredentialEncryptionService singleton
```

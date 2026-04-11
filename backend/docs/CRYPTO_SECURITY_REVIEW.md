# Crypto V2 Security Review

## Risks Eliminated

| Risk | Before | After |
|------|--------|-------|
| XOR obfuscation used as "encryption" | Active in `domains/encryption.py` | Replaced with AES-256-GCM |
| Base64 encoding used as "encryption" | Active in `modules/credential_vault.py` | Replaced with AES-256-GCM |
| No key versioning | Impossible to rotate keys | Versioned envelopes with `kid` field |
| No AAD context binding | Encrypted data portable between tenants | Tenant/provider/env bound via GCM AAD |
| SHA-256 key derivation | Non-standard, no domain separation | HKDF-SHA256 with salt + info |
| Default fallback key in code | `"syroce-pms-default-key-change-in-production"` | Fails loudly in production if no key |
| Silent decryption failure (return "") | Data corruption goes undetected | Always raises typed exceptions |
| 3 incompatible encryption modules | Fragmented, inconsistent security | Single `core/crypto/service.py` boundary |
| Masking mixed with encryption | Confusing abstractions | Clean separation in `masking.py` |
| No tamper detection on credentials | Modified ciphertext accepted | GCM tag rejects any modification |
| Plaintext credentials in DB (HotelRunner) | `token` field stored raw | All credentials encrypted at rest |

## Risks Mitigated (Reduced)

| Risk | Status | Notes |
|------|--------|-------|
| Key in environment variable | Reduced | HKDF adds derivation layer; env vars better than hardcoded |
| Single master key for all tenants | Reduced | AAD provides per-tenant binding; same key, different context |
| Key exposure in memory | Reduced | Keyring is frozen dataclass; key not logged |

## Remaining Risks

| Risk | Severity | Mitigation Path |
|------|----------|-----------------|
| Master key in env var (not HSM) | Medium | Migrate to AWS KMS / HSM for key wrapping |
| Application memory access | Medium | Use KMS for runtime decrypt (key never in app memory) |
| Backup/export may include encrypted DB | Low | Encryption at rest protects; key separate from data |
| Admin with DB + env access | Low | Inherent trust boundary; audit logging helps |
| Legacy code paths during migration | Low | Time-bounded; CRYPTO_V2_ENABLED gates new format |

## Recommended Future Enhancements

1. **AWS KMS Integration:** Use KMS for key wrapping. Application gets data key from KMS, never stores master key.
2. **Per-Tenant Keys:** Derive unique keys per tenant using HKDF info parameter.
3. **Key Ceremony:** Formal key generation and distribution process with multiple custodians.
4. **Envelope Encryption:** Use KMS to encrypt the data key, store encrypted data key alongside ciphertext.
5. **Hardware Security Module:** For highest security, use HSM-backed keys (AWS CloudHSM, Azure HSM).

## Compliance Notes

| Standard | Status |
|----------|--------|
| PCI-DSS Req 3.4 (render PAN unreadable) | Met — AES-256-GCM |
| PCI-DSS Req 3.5 (protect cryptographic keys) | Partial — env var, not HSM |
| PCI-DSS Req 3.6 (key management) | Met — documented rotation process |
| GDPR Art 32 (encryption of personal data) | Met — AES-256-GCM at rest |
| SOC 2 CC6.1 (encryption controls) | Met — documented, versioned, audited |

# Crypto V2 Rollout Plan

## Pre-requisites

- [ ] `core/crypto/` module deployed
- [ ] All callers refactored to use `CredentialEncryptionService`
- [ ] 41 unit tests passing
- [ ] `CM_MASTER_KEY_CURRENT` set to a strong key (32+ chars)
- [ ] `CM_CREDENTIAL_KEY` preserved for legacy decryption

## Phase 0: Safe Deployment (Current)

**Duration:** Immediate

```env
CRYPTO_V2_ENABLED=false
CM_MASTER_KEY_CURRENT=<new-strong-key>
CM_KEY_VERSION=v1
CM_CREDENTIAL_KEY=<existing-legacy-key>
```

**What happens:**
- New code deployed, crypto service active
- All encryption uses old `aes256gcm:` format (zero behavior change)
- All decryption supports all formats (SYR1 + legacy)
- KeyRing initialized with HKDF-derived keys

**Validation:**
- `curl /api/health` returns 200
- Login works
- Provider config endpoints work
- Unit tests pass

## Phase 1: Dev/Staging Validation

**Duration:** 1-2 days

```env
CRYPTO_V2_ENABLED=true  # Enable on staging first
```

**Validation checklist:**
- [ ] New credentials saved in SYR1 format
- [ ] Old credentials still readable (dual-read)
- [ ] Provider connection test works
- [ ] Credential masking displays correctly
- [ ] No plaintext in logs (`grep -r "password\|token" logs/`)

**Dry-run migration:**
```bash
python scripts/migrate_crypto.py --dry-run --all
```

## Phase 2: Production Canary

**Duration:** 1 week

```env
CRYPTO_V2_ENABLED=true
CM_MASTER_KEY_CURRENT=<production-key>
CM_CREDENTIAL_KEY=<legacy-key>  # Keep for migration
```

**Monitor:**
- Error rates on credential endpoints
- Secret audit logs for failures
- No `DecryptionError` in production logs

## Phase 3: Full Migration

**Duration:** 1 day (after canary)

```bash
# Dry run first
python scripts/migrate_crypto.py --dry-run --all

# Execute
python scripts/migrate_crypto.py --all --force-v2

# Verify
python scripts/migrate_crypto.py --dry-run --all
# Expected: 0 migrated, all "already current"
```

## Phase 4: Cleanup

**Duration:** After 30-day monitoring

```env
# Remove legacy keys
# CM_CREDENTIAL_KEY=  (remove)
# CM_ENCRYPTION_KEY=  (remove)
```

**Code cleanup:**
- Remove `LegacyDecryptor` class
- Remove legacy format support from `service.py`
- Remove `CRYPTO_V2_ENABLED` flag (always V2)

## Emergency Rollback

If critical issues in production:

**Option A:** Disable V2 (immediate)
```env
CRYPTO_V2_ENABLED=false
```
New writes revert to old format. Old V2 data still readable.

**Option B:** Break-glass bypass (extreme emergency only)
```env
CRYPTO_BYPASS_ALLOWED=true
```
Disables ALL encryption. Use only as last resort.

## Key Rotation (Post-Migration)

```bash
# Generate new key
python -c "import secrets; print(secrets.token_urlsafe(32))"

# Update env
CM_MASTER_KEY_CURRENT=<new-key>
CM_MASTER_KEY_PREVIOUS=<old-current-key>
CM_KEY_VERSION=v2

# Deploy, then re-encrypt
python scripts/migrate_crypto.py --all

# After verification, remove previous
CM_MASTER_KEY_PREVIOUS=
```

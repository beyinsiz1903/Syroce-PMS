# Secrets Architecture — SEC-001

## Overview

Syroce PMS uses a production-grade, multi-backend secrets management system for storing provider credentials (Exely, HotelRunner, future providers). The architecture separates secret storage from business logic via a clean abstraction layer.

## Secret Flow

```
┌─────────────┐     ┌──────────────┐     ┌───────────────────────┐
│  API Router  │────>│ SecretsManager│────>│  Backend Provider     │
│ (Exely/HR)   │     │ (core/secrets) │     │ AWS | LocalDev | Vault│
└─────────────┘     └──────┬───────┘     └───────────────────────┘
                           │
                    ┌──────▼───────┐
                    │ Audit Logger │
                    │ (MongoDB TTL)│
                    └──────────────┘
```

1. **Router** calls `sm.store_provider_credentials(tenant, provider, property, creds)`
2. **SecretsManager** builds a `SecretIdentity` (deterministic path)
3. **Backend Provider** encrypts and stores the secret
4. **Audit Logger** records the access (without secret values)
5. On retrieval: backend decrypts → SecretsManager returns → router uses

## Backend Choices

| Backend | When | Encryption | Storage |
|---------|------|-----------|---------|
| `aws_secrets_manager` | Production, Staging | AWS KMS | AWS Secrets Manager |
| `local_dev` | Development only | AES-256-GCM | MongoDB `_dev_secrets` |
| `vault` | Future | Vault Transit | HashiCorp Vault KV v2 |

### Provider Resolution
```
SECRETS_PROVIDER env var → SecretsConfig.validate() at startup
  ├── aws_secrets_manager → requires AWS_REGION
  ├── local_dev           → forbidden in production/staging
  └── vault               → requires VAULT_ADDR (placeholder)
  └── anything else       → RuntimeError at startup
```

## Naming Convention

```
/{prefix}/{environment}/channel-manager/{tenant_id}/{provider}/{property_id}
```

### Examples
```
syroce/production/channel-manager/t_abc123/exely/hotel_501694
syroce/staging/channel-manager/t_demo/hotelrunner/hr_12345
syroce/development/channel-manager/t_test/exely/hotel_999
```

### Properties
- **Deterministic**: Same inputs always produce same path
- **Environment-safe**: Production and staging secrets never collide
- **Tenant-isolated**: Each tenant's secrets are in distinct paths
- **Sanitized**: Special characters replaced with underscores

## Migration Strategy

### Dual-Read Window
When `ENABLE_LEGACY_SECRET_FALLBACK=true`:
1. Try new secrets backend first
2. If not found, fall back to legacy `provider_secrets` collection
3. If not found, fall back to connection document (HotelRunner plaintext)
4. Log a warning on every legacy fallback hit

### Migration Script
```bash
# Dry run (preview only)
cd /app/backend
python -m scripts.migrate_secrets --dry-run

# Migrate all tenants
python -m scripts.migrate_secrets

# Migrate single tenant
python -m scripts.migrate_secrets --tenant t_abc123
```

The script:
- Reads existing `provider_secrets` records (Exely)
- Reads `hotelrunner_connections` with plaintext tokens
- Stores each in the new secrets backend
- Marks source records as migrated
- Removes plaintext `token` field from HotelRunner connection docs
- Idempotent: skips already-migrated records

### Post-Migration
Once all records are migrated:
1. Set `ENABLE_LEGACY_SECRET_FALLBACK=false`
2. Verify all connection flows still work
3. Remove legacy credential fields from connection documents

## Failure Modes

| Scenario | Behavior |
|----------|----------|
| Missing SECRETS_PROVIDER | Defaults to `local_dev` (dev only) |
| `local_dev` in production | **Hard fail** at startup |
| AWS creds missing/invalid | Create/read fails with clear error |
| AWS throttled | Retries (3 attempts, adaptive backoff) |
| Secret not found | Returns None (router handles) |
| Encryption key wrong | Decryption fails with ValueError |
| Audit write fails | Logged, does NOT block secret operation |
| Legacy fallback fails | Returns None, tries next source |

## Operational Guidance

### Environment Variables
```env
# Required
SECRETS_PROVIDER=aws_secrets_manager  # or local_dev
APP_ENV=production                     # or staging, development

# AWS (required when SECRETS_PROVIDER=aws_secrets_manager)
AWS_REGION=eu-west-1

# Optional
AWS_SECRET_PREFIX=syroce               # default: syroce
ENABLE_LEGACY_SECRET_FALLBACK=false    # default: true
SECRET_ACCESS_AUDIT_ENABLED=true       # default: true
CM_CREDENTIAL_KEY=<random-32-chars>    # for local_dev encryption
```

### Monitoring
- Audit trail: `secret_access_audit` collection (90-day TTL)
- Health check: `GET /api/health/deep` includes secrets manager status
- Legacy fallback warnings in application logs

### Key Files
```
core/secrets/
  __init__.py          — Public API
  config.py            — Configuration + validation
  naming.py            — SecretIdentity naming model
  provider.py          — Abstract interface
  aws_provider.py      — AWS Secrets Manager backend
  local_provider.py    — Development backend (AES-256-GCM + MongoDB)
  vault_provider.py    — HashiCorp Vault placeholder
  manager.py           — Unified SecretsManager
  audit.py             — Access audit logger
scripts/
  migrate_secrets.py   — Migration tool
tests/
  test_secrets_manager.py — 35 unit tests
```

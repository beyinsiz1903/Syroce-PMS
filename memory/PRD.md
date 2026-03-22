# Syroce PMS — Product Requirements Document

## Original Problem Statement
Hotel PMS + Channel Manager platform with FastAPI, MongoDB, multi-tenant architecture.
The platform manages provider integrations (Exely, HotelRunner), credential storage,
audit requirements, and operational reliability.

## Core Requirements
- Multi-tenant hotel property management
- Channel manager for OTA integrations
- Secure credential storage for provider APIs
- Enterprise-grade security architecture
- Production-ready deployment model
- **Operational control plane for system visibility and reliability**

## Security Architecture (Completed)

### SEC-001: Secrets Management Architecture
- Provider abstraction for secret operations (create, get, update, delete, rotate)
- Multiple backends: AWS Secrets Manager, Local Dev (AES-GCM/MongoDB), Vault placeholder
- Deterministic resolution via SECRETS_PROVIDER env var
- Tenant-aware secret naming convention
- Migration script + dual-read fallback
- Access audit logging

### SEC-002: Production-Grade Encryption (AES-256-GCM)
- Replaced XOR obfuscation, base64 encoding, and flawed AES-GCM with proper AEAD
- HKDF-SHA256 key derivation (RFC 5869)
- SYR1: versioned envelope format with AAD context binding
- Dual-key rotation model (current + previous)
- Feature flags: CRYPTO_V2_ENABLED, CRYPTO_BYPASS_ALLOWED
- Single encryption boundary: CredentialEncryptionService
- Complete backward compatibility with all legacy formats
- 59 tests (41 unit + 18 API integration)

## Control Plane (Completed - 2026-03-22)

### OPS-001: Production-Grade Control Plane
A system behavior layer providing:
- **Failure Model**: Strict 5-type taxonomy (RETRYABLE, PERMANENT, PROVIDER_ERROR, DATA_ERROR, SECURITY_ERROR) with 4-level severity (info, warning, high, critical)
- **15 API endpoints** under `/api/ops/*` for operational visibility
- **Failure Tracker**: Centralized recording, querying, and resolution
- **Retry Engine**: Idempotent retry/replay with dry-run mode, duplicate-safe
- **Secret Access Control**: Policy enforcement, tenant isolation at query level, anomaly detection
- **Alerting**: Threshold-based with log + generic HTTP webhook (Slack-compatible)
- **Runbooks**: 14 structured operational runbooks
- **Startup Validation**: Crypto keys, secrets, indexes, env vars
- **67 tests** (38 unit + 29 API integration)

## Architecture
```
backend/
├── core/
│   ├── crypto/           # SEC-002: Encryption engine
│   ├── secrets/          # SEC-001: Secrets management
│   └── database.py
├── controlplane/         # OPS-001: Control Plane
│   ├── failure_model.py  # Taxonomy + event schema
│   ├── failure_tracker.py # Central failure service
│   ├── retry_engine.py   # Idempotent retry/replay
│   ├── ops_router.py     # 15 /api/ops/* endpoints
│   ├── secret_audit.py   # Access control + audit
│   ├── alerting.py       # Threshold alerts + webhook
│   ├── runbooks.py       # 14 operational runbooks
│   ├── indexes.py        # MongoDB indexes
│   └── startup_validator.py # Startup checks
├── domains/channel_manager/
├── channel_manager/infrastructure/
└── modules/security_hardening/
```

## Tech Stack
- FastAPI + Motor (async MongoDB)
- cryptography (AESGCM, HKDF)
- boto3 (AWS Secrets Manager)
- Redis (caching)

## Users
| Role | Email | Purpose |
|------|-------|---------|
| Demo Admin | demo@hotel.com / demo123 | super_admin |

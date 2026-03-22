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

## Architecture
```
backend/
├── core/
│   ├── crypto/           # SEC-002: Encryption engine
│   │   ├── engine.py     # AES-256-GCM with AAD
│   │   ├── envelope.py   # SYR1 versioned format
│   │   ├── keys.py       # HKDF key derivation + KeyRing
│   │   ├── masking.py    # Display masking (NOT crypto)
│   │   ├── migration.py  # Legacy format detection
│   │   ├── service.py    # Single encryption boundary
│   │   └── errors.py     # Typed exceptions
│   ├── secrets/          # SEC-001: Secrets management
│   └── database.py
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

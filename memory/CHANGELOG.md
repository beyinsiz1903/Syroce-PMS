# Syroce PMS — Changelog

## 2026-03-22: OPS-001 — Production-Grade Control Plane

### New Module: `backend/controlplane/`
- **Failure Model** (`failure_model.py`): Strict 5-type failure taxonomy with auto-classification via keyword matching. 4-level severity system. Structured failure event schema with sanitization (no plaintext leak).
- **Failure Tracker** (`failure_tracker.py`): Central service for recording, querying, resolving, and ignoring failures. Aggregation queries by severity, type, and operation.
- **Retry Engine** (`retry_engine.py`): Idempotent retry/replay with dry-run mode. Dispatch handlers for reservation import, outbox events, ARI push, and sync jobs. Duplicate-safe.
- **Ops Router** (`ops_router.py`): 15 API endpoints under `/api/ops/*`:
  - System overview, failure CRUD, retry/resolve/ignore
  - Outbox/import/sync monitors
  - Secret access audit + anomalies
  - Runbooks (14 entries), alerts
- **Secret Access Control** (`secret_audit.py`): Service-level ACL, strict tenant isolation at query level, security alert emission on denied access.
- **Alerting** (`alerting.py`): 7 trigger types with configurable thresholds, 15-min cooldown dedup, log-based + generic HTTP webhook (Slack Block Kit format).
- **Runbooks** (`runbooks.py`): 14 operational runbooks covering all user-specified scenarios.
- **Startup Validation** (`startup_validator.py`): Validates crypto, secrets, indexes, and env vars at boot.
- **Indexes** (`indexes.py`): MongoDB compound indexes for all control plane collections.

### Documentation
- `docs/CONTROLPLANE_ARCHITECTURE.md` — Full architecture document
- `docs/CONTROLPLANE_ROLLOUT.md` — Safe deployment plan

### Tests
- `tests/test_controlplane.py` — 38 unit tests
- `tests/test_controlplane_api.py` — 29 API integration tests (created by testing agent)

### Modified Files
- `startup.py` — Added control plane startup validation
- `bootstrap/router_registry.py` — Registered controlplane.ops_router

---

## 2026-03-21: SEC-002 — Production-Grade Encryption Refactor

### New Module: `backend/core/crypto/`
- AES-256-GCM with HKDF-SHA256 key derivation
- SYR1: versioned envelope format with AAD context binding
- Dual-key rotation model, feature-flagged migration
- 41 unit tests + 18 API integration tests

### Refactored (5 legacy modules → wrappers)
- `domains/channel_manager/encryption.py`
- `domains/channel_manager/credential_vault.py`
- `channel_manager/infrastructure/encryption_service.py`
- `channel_manager/infrastructure/credential_vault.py`
- `modules/security_hardening/credential_vault.py`

---

## Earlier: SEC-001 — Secrets Management Architecture
- Provider abstraction (AWS, local_dev, Vault)
- Tenant-aware naming, dual-read migration, access audit logging

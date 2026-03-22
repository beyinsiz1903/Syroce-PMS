# Syroce PMS — Roadmap

## Completed
- [x] SEC-001: Secrets Management Architecture
- [x] SEC-002: Production-Grade Encryption (AES-256-GCM)

## P0 — Immediate
- [ ] SEC-002 Phase 1: Enable CRYPTO_V2_ENABLED=true in staging
- [ ] SEC-002 Phase 2: Run migrate_crypto.py on existing data
- [ ] SEC-001 Rollout: Execute secrets migration (scripts/migrate_secrets.py)
- [ ] Enable STRICT_TENANT_MODE=true

## P1 — High Priority
- [ ] Gradual migration of ~264 legacy `db` imports to `get_db()`
- [ ] Fix pre-existing test failures (test_hardening_comprehensive.py)
- [ ] Fix pre-existing lint errors (frontdesk_router.py, misc_router.py)
- [ ] INFRA-002: Collection Registry
- [ ] pms.py decomposition (2714 lines → modular services)

## P2 — Medium Priority
- [ ] Legacy collection cleanup (~489 collections)
- [ ] Refactor @cached decorator (cache_manager.py)
- [ ] Data Model Repair Plan
- [ ] Remove legacy encryption modules after migration (3 credential_vault.py, 2 encryption.py)
- [ ] Observability & Incident Response Plan

## P3 — Future / Backlog
- [ ] Frontend dashboards (Outbox, Import Bridge, Night Audit)
- [ ] AWS KMS integration for key wrapping
- [ ] Per-tenant key derivation via HKDF info parameter
- [ ] HashiCorp Vault backend implementation
- [ ] PII masking in logs
- [ ] Stress testing & dependency security audit
- [ ] Envelope encryption (KMS-wrapped data keys)

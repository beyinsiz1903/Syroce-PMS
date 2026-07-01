# Secrets Manager — Rollout Plan

## Phase 1: Development (Current)
- [x] Implement secrets abstraction layer
- [x] Implement local_dev backend with AES-256-GCM
- [x] Implement AWS Secrets Manager backend
- [x] Refactor Exely router to use SecretsManager
- [x] Refactor HotelRunner router to use SecretsManager
- [x] Add audit logging
- [x] Create migration script
- [x] Pass 35 unit tests
- [x] Enable `ENABLE_LEGACY_SECRET_FALLBACK=true` for backward compatibility

## Phase 2: Staging
1. Deploy code to staging environment
2. Set environment variables:
   ```
   SECRETS_PROVIDER=aws_secrets_manager
   APP_ENV=staging
   AWS_REGION=eu-west-1
   ENABLE_LEGACY_SECRET_FALLBACK=true
   ```
3. Verify startup validation passes
4. Run migration script in dry-run mode:
   ```bash
   python -m scripts.migrate_secrets --dry-run
   ```
5. Run actual migration:
   ```bash
   python -m scripts.migrate_secrets
   ```
6. Verify Exely connect/test/sync flows work
7. Verify HotelRunner connect/test/sync flows work
8. Monitor audit trail for legacy fallback warnings
9. Monitor for 48 hours

## Phase 3: Partial Production (Pilot Tenant)
1. Deploy code to production
2. Keep `ENABLE_LEGACY_SECRET_FALLBACK=true`
3. Migrate a single pilot tenant:
   ```bash
   python -m scripts.migrate_secrets --tenant <pilot_tenant_id>
   ```
4. Monitor pilot tenant for 1 week:
   - Connection flows working
   - Sync/pull/push operations unaffected
   - No legacy fallback warnings for pilot tenant
   - Audit trail populated correctly
5. Verify no secret values in API responses or logs

## Phase 4: Full Production
1. Migrate all remaining tenants:
   ```bash
   python -m scripts.migrate_secrets
   ```
2. Monitor for 1 week with legacy fallback enabled
3. Verify zero legacy fallback hits in logs
4. Set `ENABLE_LEGACY_SECRET_FALLBACK=false`
5. After 30 days with no issues:
   - Remove plaintext credential fields from legacy connection documents
   - Drop legacy `provider_secrets` collection (backup first)

## Rollback Plan
At any phase:
1. Set `ENABLE_LEGACY_SECRET_FALLBACK=true`
2. Legacy credentials remain intact until explicitly removed
3. System automatically falls back to legacy stores
4. No data loss — migration only adds, never deletes (until Phase 4)

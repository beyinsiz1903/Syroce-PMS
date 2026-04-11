# CHAOS TESTING & RESILIENCE VALIDATION — Master Plan
## Syroce PMS + Channel Manager Platform

**Document Version:** 1.0
**Classification:** Engineering / SRE
**Scope:** Staging-first, deterministic resilience validation
**Status:** Implementation-Ready

---

## 1. EXECUTIVE SUMMARY

This document defines a comprehensive chaos testing and resilience validation program for the Syroce PMS + Channel Manager platform. The program validates that the system remains **correct, observable, recoverable, and safe** under real-world failure conditions.

**Critical invariants this program protects:**
- No reservation loss under any failure condition
- No duplicate reservations from retry/replay
- No silent outbox failures — every failure is surfaced
- No ARI parity corruption between PMS and OTA state
- No unsafe replay behavior (dry-run MUST NOT mutate)
- No tenant isolation break — ever
- No secret leakage under failure or error conditions

**Architecture covered:** FastAPI backend, MongoDB, Redis, outbox pattern, import bridge, ARI push engine, control plane (`/api/ops/*`), AES-256-GCM crypto, secrets management, multi-tenant middleware, provider adapters (Exely, HotelRunner).

---

## 2. CHAOS SCENARIO MATRIX

### Category A — Provider / OTA Failure Scenarios

| ID | Scenario | Why It Matters | Expected Safe Behavior | Must Never Happen |
|----|----------|----------------|------------------------|-------------------|
| A-01 | Provider timeout during reservation pull | OTA APIs are unreliable. Timeout during pull must not leave partial import state. | Import record stays in `retry` status. FailureTracker records RETRYABLE failure. Backoff schedule followed. | Partial booking creation. Lost reservation. Silent failure. |
| A-02 | Provider 500 error during ARI push | OTAs return 500s during high load. ARI push must retry without corrupting rates. | Outbox event transitions to `retry`. ARI change set preserved. Exponential backoff. | Rate data sent partially. Outbox event lost. Duplicate ARI push. |
| A-03 | Provider auth failure (401/403) | Rotated credentials or expired tokens. | Classified as PROVIDER_ERROR. Alert fired. Retry skipped (permanent for auth). Runbook RB-005 surfaced. | Retry loop on auth failures. Secret leakage in error logs. |
| A-04 | Provider rate limiting (429) | OTAs enforce rate limits aggressively. | Classified as RETRYABLE. Outbox worker respects backoff. No data loss. | Aggressive retry that worsens rate limit. Permanent failure marking for 429. |
| A-05 | Malformed provider payload | Provider sends invalid JSON or missing fields. | Classified as DATA_ERROR. Import record → `review_required`. Lineage preserved. | Crash. Partial import. Silent discard. |
| A-06 | Duplicate reservation delivery | Provider webhook fires twice for same reservation. | Idempotency key (external_reservation_id) prevents duplicate. Second delivery detected and logged. | Duplicate booking in PMS. Duplicate outbox event. |
| A-07 | Out-of-order events (modify before create) | Network reordering causes modification to arrive before creation. | Modification held in import queue. Processing respects event ordering via lineage. | Lost modification. Stale booking state. |
| A-08 | Partial provider response | OTA returns 200 but with incomplete data (missing dates, guest name). | Validation catches missing fields. Import → `review_required`. No partial booking. | Booking created with null dates. Data corruption. |
| A-09 | Provider slow response (latency spike) | 10-30s response instead of normal 2s. | Timeout triggers RETRYABLE classification. Worker doesn't block entire batch. | Worker starvation. All events stuck. |
| A-10 | Provider recovery after outage | OTA comes back after 2h outage with backlog. | Pending events drain normally. No duplicate processing. Backlog visible in `/api/ops/outbox`. | Event storm overwhelms system. Duplicate deliveries. |

### Category B — Internal Queue / Worker Failure Scenarios

| ID | Scenario | Why It Matters | Expected Safe Behavior | Must Never Happen |
|----|----------|----------------|------------------------|-------------------|
| B-01 | Worker crash during import | Process dies mid-import-bridge execution. | Atomic claim pattern: record stays in `processing`. Recovery worker resets stuck records after timeout. | Orphaned record. Booking created but import not marked. |
| B-02 | Worker crash during outbox delivery | Process dies after claiming outbox event but before dispatch. | `_recover_stuck()` resets events stuck in `processing` beyond timeout. | Lost outbox event. Event permanently stuck. |
| B-03 | Retry worker crash mid-flight | Retry engine crashes after marking failure as RETRYING but before dispatch. | Failure stays in RETRYING state. Manual retry via `/api/ops/failures/{id}/retry` is safe. | Failure marked resolved when it isn't. State corruption. |
| B-04 | Stuck job detection | Worker processing hangs indefinitely (no crash, just frozen). | `_recover_stuck()` detects events with stale `last_attempt_at`. Alert fires via `outbox_stuck` trigger. | Infinite hang. Silent stuck job. |
| B-05 | Duplicated job execution | Two workers claim the same event (race condition). | Atomic `find_one_and_update` prevents double-claim. Only one worker processes. | Duplicate processing. Double ARI push. Double booking creation. |
| B-06 | Delayed job execution | Events sit pending longer than SLA. | Visible in `/api/ops/outbox` with age metrics. Alert fires if threshold crossed. | No visibility into delay. Silent SLA breach. |
| B-07 | Dead-letter accumulation | Events keep failing past max_attempts. | Status → `failed`. Visible in `/api/ops/outbox`. Failure recorded in control plane. | Events silently dropped. No audit trail. |

### Category C — Database / Persistence Failure Scenarios

| ID | Scenario | Why It Matters | Expected Safe Behavior | Must Never Happen |
|----|----------|----------------|------------------------|-------------------|
| C-01 | MongoDB temporary unavailability | Connection drops for 5-30s. | Operations fail with retryable error. Workers retry on next poll. No data loss. | Partial writes. Corrupted documents. Silent data loss. |
| C-02 | Partial write failure (transaction abort) | Transaction aborts mid-booking-creation. | `create_booking_atomic` uses transactions — abort = nothing written. Clean state. | Booking written but no outbox event. Orphaned audit log. |
| C-03 | Duplicate key collision on booking source | Race condition: two imports for same external_reservation_id. | `DuplicateKeyError` caught. Import marked as `duplicate`. | Two bookings for same reservation. Data inconsistency. |
| C-04 | Index missing / degraded query | Production index dropped or not created. | Startup validator checks indexes. Slower queries but correct results. | Wrong query results. Silent performance degradation undetected. |
| C-05 | Failure while writing audit/failure events | DB fails when writing to `cp_failures` or audit collections. | Exception caught. Original operation continues. Logged but not silently lost. | Original operation fails because audit write failed. Cascade failure. |

### Category D — Secrets / Crypto / Security Failure Scenarios

| ID | Scenario | Why It Matters | Expected Safe Behavior | Must Never Happen |
|----|----------|----------------|------------------------|-------------------|
| D-01 | Missing secret during provider pull | Credentials not yet migrated or deleted. | `get_provider_credentials` returns None. Legacy fallback attempted. Failure logged with SECURITY_ERROR. | Crash. Plaintext in logs. Silent failure without audit. |
| D-02 | Decryption failure on secret fetch | Wrong key, corrupted envelope, or tampered data. | `TamperDetectedError` or `DecryptionError` raised. Classified as SECURITY_ERROR, severity CRITICAL. Alert fires. | Plaintext leakage. Silent decryption bypass. |
| D-03 | Wrong AAD context (tenant/provider mismatch) | AAD context mismatch means ciphertext was moved between tenants. | GCM tag verification fails → `TamperDetectedError`. Cross-tenant access denied. | Decryption succeeds with wrong context. Cross-tenant credential access. |
| D-04 | Rotated key mismatch | Active key rotated but old ciphertext references previous key. | KeyRing contains both current and previous keys. Decryption succeeds with previous key. | `KeyNotFoundError` for recently rotated data. Service outage on rotation. |
| D-05 | Malformed encrypted envelope | Corrupted `SYR1:` prefix, bad base64, truncated ciphertext. | `EnvelopeParseError` raised. Classified appropriately. No crash. | Crash on malformed input. Bypass to plaintext. |
| D-06 | Unauthorized secret access attempt | Unknown caller tries to access provider secrets. | Policy check denies. Audit logged with result=`denied`. Security failure emitted to control plane. | Access granted to unauthorized caller. No audit trail. |

### Category E — Multi-Tenant Safety Scenarios

| ID | Scenario | Why It Matters | Expected Safe Behavior | Must Never Happen |
|----|----------|----------------|------------------------|-------------------|
| E-01 | Retry on wrong tenant context | Operator retries a failure but tenant context is mismatched. | Retry engine reads tenant_id from failure record. Tenant context validated before dispatch. | Retry executes in wrong tenant. Cross-tenant data mutation. |
| E-02 | Secret access cross-tenant attempt | Service with tenant A context tries to read tenant B secrets. | `check_and_log` detects `request_tenant_id != tenant_id`. Access DENIED. Critical security log. | Cross-tenant secret read succeeds. No audit trail of attempt. |
| E-03 | Replay event with mismatched tenant_id | Outbox event replayed but tenant_id in payload doesn't match claiming worker's context. | Dispatcher validates tenant_id on event. Mismatch → permanent failure. | Cross-tenant ARI push. Wrong hotel's rates updated. |
| E-04 | Connector mismatch (tenant ↔ provider config) | Connector belongs to tenant A but referenced by tenant B's outbox event. | Repository query filters by tenant_id. Connector not found → no dispatch. | ARI push to wrong provider account. Data leak to competitor hotel. |

### Category F — Control Plane / Ops Visibility Scenarios

| ID | Scenario | Why It Matters | Expected Safe Behavior | Must Never Happen |
|----|----------|----------------|------------------------|-------------------|
| F-01 | Failure occurs but not surfaced | A real error happens but never reaches `cp_failures`. | FailureTracker integration ensures all classified errors are recorded. | Silent failure. No visibility. No alerting. |
| F-02 | Retry triggered but failure state not updated | Retry succeeds but failure stays OPEN. | RetryEngine atomically updates failure status on success/failure. | Stale failure state. Operator confusion. |
| F-03 | Alert threshold crossed, no alert emitted | 5 import failures in 30 min but no alert. | `check_and_alert()` runs periodically. Thresholds checked against live data. | Missed alert. Operator unaware of spike. |
| F-04 | Dry-run retry produces side effects | Operator runs dry-run but it actually modifies state. | Dry-run returns immediately after validation. No DB writes. No dispatch. | Mutation during dry-run. Broken operator trust. |
| F-05 | Runbook missing for critical scenario | Crypto failure happens but no runbook available. | All 14 critical runbooks pre-loaded. `get_runbook("RB-008")` returns crypto failure runbook. | Operator has no guidance during incident. |

---

## 3. RESILIENCE TESTING LAYERS

### Level 1 — Unit Chaos Tests
**Focus:** Individual service behavior under injected failure conditions.
**Run:** Every PR. Fast (<30s total).

| Scenario IDs | Component | Test Focus |
|--------------|-----------|------------|
| A-05, A-06 | `failure_model.classify_failure()` | Correct taxonomy classification for all keyword categories |
| D-01-D-06 | `crypto/engine.py`, `crypto/errors.py` | Encrypt/decrypt failure modes, tamper detection, key rotation |
| E-02 | `secret_audit.check_and_log()` | Cross-tenant denial, policy enforcement |
| F-04 | `retry_engine.retry(dry_run=True)` | No state mutation during dry-run |
| B-05 | `outbox_service._build_idempotency_key()` | Idempotency key determinism and collision resistance |

### Level 2 — Integration Resilience Tests
**Focus:** Multi-component interaction under failure injection.
**Run:** Every PR + nightly.

| Scenario IDs | Flow | Test Focus |
|--------------|------|------------|
| A-01, A-09 | Provider adapter → import bridge → booking creation | Timeout handling, retry scheduling, no partial booking |
| B-01, B-02 | Outbox worker → dispatcher → provider adapter | Stuck recovery, atomic claim, failure lifecycle |
| D-01, D-03 | Secret resolution → credential vault → provider call | Missing secret handling, AAD mismatch, audit trail |
| C-02, C-03 | Atomic booking → MongoDB transaction | Conflict detection, duplicate key handling |
| F-01, F-02 | FailureTracker → RetryEngine → failure state | State machine correctness through full lifecycle |

### Level 3 — End-to-End Chaos Flows
**Focus:** Realistic multi-step scenarios crossing all boundaries.
**Run:** Nightly + before pilot.

| Scenario IDs | Flow | Test Focus |
|--------------|------|------------|
| A-01 + B-02 + F-01 | Reservation import during provider instability | Full failure chain: timeout → retry → recovery → booking |
| A-02 + A-04 + B-04 | ARI push during rate limiting | 429 handling → backoff → stuck detection → recovery |
| A-10 + B-06 + F-03 | Provider recovery after outage with backlog | Drain behavior, no duplicates, alerting fires |
| D-04 + D-02 | Key rotation while services continue | Old ciphertext still decrypts, new encryptions use new key |

### Level 4 — Operational / Soak / Storm Tests
**Focus:** Longer-running validation of system stability.
**Run:** Weekly + before pilot.

| Test | Duration | Focus |
|------|----------|-------|
| Reservation Burst | ~5 min | 50/100/500 reservations, no duplicates, queue drains |
| ARI Storm | ~5 min | Mass ARI updates, rate limit respect, parity |
| 24h Soak | 24h | Intermittent failures, no memory leaks, alerting useful |
| Secret Anomaly Flood | ~2 min | Repeated denied access, audit trail, anomaly detection |

---

## 4. DETAILED TEST SCRIPTS

### TS-001: Duplicate Reservation Delivery
```
Test ID:        TS-001
Scenario:       A-06 — Duplicate reservation delivery via webhook
Objective:      Verify that delivering the same reservation twice does NOT create duplicate bookings
Preconditions:  Running backend, populated room_mappings for test tenant
Setup:
  1. Create test tenant "chaos-t1" with room mapping (provider=exely, room_code=STD → pms_room_type_id=rt1)
  2. Prepare reservation payload with external_reservation_id="EXT-DUP-001"

Chaos Injection:
  - Call import bridge twice with identical reservation data and same external_reservation_id

Execution Steps:
  1. Call create_import_record() with lineage containing external_reservation_id="EXT-DUP-001"
  2. Call auto_import_reservation_to_pms() with the import record ID
  3. Assert booking created successfully
  4. Call create_import_record() again with SAME external_reservation_id
  5. Assert second create_import_record returns None (DuplicateKeyError caught)
  6. Alternatively: call auto_import_reservation_to_pms() if a second record exists → must detect duplicate via check_booking_source_exists()

Expected Behavior:
  - First import: booking created, import_status="imported"
  - Second import: DuplicateKeyError caught OR import_status="duplicate" with booking_id linked

Assertions:
  - db.bookings.count_documents({"source.external_reservation_id": "EXT-DUP-001"}) == 1
  - No duplicate outbox event
  - Import record for second attempt shows status="duplicate"

Observability Checks:
  - Logger output contains "already exists" or "duplicate"
  - No failure recorded in cp_failures (this is expected behavior, not failure)

Cleanup:
  - Delete test bookings, import records, lineage for tenant "chaos-t1"

Pass/Fail:
  - PASS: Exactly 1 booking exists. Second attempt detected as duplicate.
  - FAIL: 2 bookings exist OR second attempt crashes OR silent discard.
```

### TS-002: Out-of-Order Reservation Events
```
Test ID:        TS-002
Scenario:       A-07 — Modification arrives before creation
Objective:      Verify system handles out-of-order events safely
Preconditions:  Import bridge service available

Setup:
  1. Create test tenant with room mappings
  2. Prepare modification event for external_reservation_id="EXT-OOO-001" (not yet created)

Chaos Injection:
  - Send modification event BEFORE creation event

Execution Steps:
  1. Attempt to process modification for non-existent reservation
  2. Assert it goes to review_required (no matching booking to modify)
  3. Process creation event → booking created
  4. Re-process modification → should now succeed or link correctly

Expected Behavior:
  - Modification without existing booking → review_required
  - Creation succeeds → booking exists
  - No data loss, no corruption

Assertions:
  - Booking exists exactly once after both events processed
  - Modification event has audit trail
  - review_required status was set for out-of-order event

Cleanup: Delete test data

Pass/Fail:
  - PASS: No data loss. Modification handled gracefully. Booking correct.
  - FAIL: Crash on modification. Lost event. Duplicate booking.
```

### TS-003: Provider Timeout During Reservation Pull
```
Test ID:        TS-003
Scenario:       A-01 — Provider times out during reservation pull
Objective:      Verify timeout is classified as RETRYABLE, no partial state
Preconditions:  FailureTracker available, import bridge callable

Setup:
  1. Create import record with status=pending_auto_import
  2. Monkeypatch provider adapter to raise TimeoutError after 100ms

Chaos Injection:
  - monkeypatch: async def mock_provider_pull(*a, **kw): raise TimeoutError("Connection timed out after 30s")

Execution Steps:
  1. Call auto_import_reservation_to_pms()
  2. Assert failure is handled, not crashed
  3. Check import record status

Expected Behavior:
  - Import record → status=retry, retry_count incremented, next_retry_at computed
  - classify_failure("Connection timed out after 30s") == RETRYABLE
  - No booking created

Assertions:
  - import_record.import_status == "retry"
  - import_record.retry_count == 1
  - import_record.next_retry_at > now
  - db.bookings.count_documents({"source.external_reservation_id": ext_id}) == 0

Observability:
  - Logger contains "scheduled for retry"
  - When FailureTracker is wired: cp_failures has record with failure_type=retryable

Cleanup: Delete test records

Pass/Fail:
  - PASS: No booking. Import in retry state. Failure classified correctly.
  - FAIL: Crash. Partial booking. Permanent failure marking.
```

### TS-004: Malformed Reservation Payload
```
Test ID:        TS-004
Scenario:       A-05 — Provider sends payload with missing required fields
Objective:      Verify malformed data does not crash system, goes to review

Setup:
  1. Create import record with missing arrival_date and departure_date

Chaos Injection:
  - Import record with arrival_date="", departure_date=""

Execution Steps:
  1. Call auto_import_reservation_to_pms()
  2. Observe behavior (booking creation with empty dates)

Expected Behavior:
  - Booking created without dates triggers validation concern
  - OR: import goes to review_required if validation catches it
  - System does NOT crash

Assertions:
  - No unhandled exception
  - Import record has audit trail of what happened

Pass/Fail:
  - PASS: Graceful handling. No crash.
  - FAIL: Unhandled exception. Silent data corruption.
```

### TS-005: Provider Recovery After Outage
```
Test ID:        TS-005
Scenario:       A-10 — Provider comes back after 2h outage with event backlog
Objective:      Verify backlog drains without duplicates

Setup:
  1. Create 20 outbox events (status=retry, different entity_ids)
  2. All have available_at in the past (simulating backlog)

Chaos Injection:
  - No chaos needed — this tests backlog drain behavior

Execution Steps:
  1. Start outbox worker
  2. Let it process the batch
  3. Count processed events

Expected Behavior:
  - All 20 events processed (or attempted)
  - No duplicate processing
  - Metrics updated correctly

Assertions:
  - All events transitioned to processed or failed (not stuck in pending)
  - No duplicate dispatch calls
  - Worker metrics reflect correct counts

Cleanup: Delete test events

Pass/Fail:
  - PASS: All events drained. No duplicates.
  - FAIL: Events stuck. Duplicate processing. Worker crash.
```

### TS-006: Provider 429 During ARI Push
```
Test ID:        TS-006
Scenario:       A-04 — Rate limiting during ARI push
Objective:      Verify 429 is classified as RETRYABLE with proper backoff

Setup:
  1. Create outbox event for rate.updated.v1
  2. Monkeypatch EventSyncService to return error containing "429"

Chaos Injection:
  - Mock dispatch to raise Exception("Provider returned 429: rate limit exceeded")

Execution Steps:
  1. OutboxWorker._process_event() with mocked dispatch
  2. Check event status after failure

Expected Behavior:
  - is_retryable_error("429: rate limit exceeded") == True
  - Event status → retry
  - available_at set to future (exponential backoff)

Assertions:
  - event.status == "retry"
  - event.attempt_count incremented
  - event.available_at > now (backoff applied)
  - classify_failure("429: rate limit exceeded") == RETRYABLE

Pass/Fail:
  - PASS: Retry scheduled with backoff.
  - FAIL: Marked as permanent. No backoff.
```

### TS-007: Worker Crash After Claim, Before Completion
```
Test ID:        TS-007
Scenario:       B-02 — Outbox worker crash mid-processing
Objective:      Verify stuck event recovery mechanism works

Setup:
  1. Insert outbox event with status=processing, last_attempt_at=2 hours ago
  2. This simulates a claimed-but-never-completed event

Chaos Injection:
  - Direct DB insert simulating crashed worker's orphaned event

Execution Steps:
  1. Call OutboxWorker._recover_stuck() with processing_timeout=120
  2. Check event status after recovery

Expected Behavior:
  - Event status changed from processing → retry
  - last_error set to "processing timeout — recovered by worker"
  - Event available for re-processing

Assertions:
  - event.status == "retry"
  - event.last_error contains "timeout"
  - event.available_at <= now (immediately available)

Pass/Fail:
  - PASS: Event recovered. Available for retry.
  - FAIL: Event still stuck. No recovery.
```

### TS-008: Duplicate Outbox Event Replay
```
Test ID:        TS-008
Scenario:       B-05 — Two workers attempt to claim same event
Objective:      Verify atomic claim prevents duplicate processing

Setup:
  1. Insert one outbox event (status=pending)

Chaos Injection:
  - Call _claim_event() concurrently from two coroutines

Execution Steps:
  1. Launch 2 concurrent asyncio.gather calls to _claim_event()
  2. Check how many succeed

Expected Behavior:
  - Exactly ONE claim succeeds (returns event)
  - Other claim returns None (event already claimed)
  - find_one_and_update is atomic

Assertions:
  - Exactly 1 non-None result from 2 concurrent claims
  - Event in DB has status=processing with exactly 1 worker_id

Pass/Fail:
  - PASS: Exactly 1 claim. No duplicate.
  - FAIL: Both claims succeed. Race condition.
```

### TS-009: Delayed Outbox Processing Detection
```
Test ID:        TS-009
Scenario:       B-06 — Events older than SLA
Objective:      Verify delayed events are visible in ops dashboard

Setup:
  1. Insert outbox events with created_at 1 hour ago, status=pending

Chaos Injection:
  - Simulated delay via old timestamps

Execution Steps:
  1. Call GET /api/ops/outbox
  2. Check stuck_count in response
  3. Call AlertingEngine.check_and_alert()

Expected Behavior:
  - /api/ops/outbox reports stuck events
  - Alert fires if threshold crossed

Assertions:
  - Overview stuck_outbox_count > 0
  - Alert fired with trigger=outbox_stuck

Pass/Fail:
  - PASS: Visibility correct. Alert fires.
  - FAIL: No visibility. No alert.
```

### TS-010: ARI Parity Mismatch Detection
```
Test ID:        TS-010
Scenario:       ARI state between PMS and OTA diverges
Objective:      Verify reconciliation or visibility mechanisms catch mismatch

Setup:
  1. Create booking that should trigger ARI update
  2. Outbox event fails permanently (never delivered)

Chaos Injection:
  - Mock dispatch to return (False, "permanent: ...")

Execution Steps:
  1. Enqueue outbox event
  2. Process event → permanent failure
  3. Check control plane

Expected Behavior:
  - Event marked as failed
  - Visible in /api/ops/outbox as failed
  - FailureTracker records the permanent failure

Assertions:
  - outbox_event.status == "failed"
  - /api/ops/outbox shows failed event
  - Failure recorded with operation_type=outbox_dispatch

Pass/Fail:
  - PASS: Mismatch visible. Failure recorded.
  - FAIL: Silent failure. No ops visibility.
```

### TS-011: Retry Dry-Run Must NOT Mutate State
```
Test ID:        TS-011
Scenario:       F-04 — Dry-run retry safety
Objective:      Verify dry_run=True produces NO side effects

Setup:
  1. Record a failure via FailureTracker
  2. Note failure's retry_count and status

Chaos Injection:
  - None (testing safety property)

Execution Steps:
  1. Call RetryEngine.retry(failure_id, dry_run=True)
  2. Check failure state before and after

Expected Behavior:
  - Returns success=True, dry_run=True, would_retry=True
  - Failure document UNCHANGED in DB
  - No retry_log entry
  - No dispatch called

Assertions:
  - failure.status == "open" (unchanged)
  - failure.retry_count == original_count (unchanged)
  - db.cp_retry_log.count_documents({"failure_id": fid}) == 0
  - No outbox events created

Pass/Fail:
  - PASS: Zero state mutation.
  - FAIL: Any DB write during dry-run.
```

### TS-012: Retry of Already-Successful Failure
```
Test ID:        TS-012
Scenario:       Retry attempted on resolved failure
Objective:      Verify resolved failures cannot be retried

Setup:
  1. Record failure
  2. Resolve it via FailureTracker.resolve()

Execution Steps:
  1. Call RetryEngine.retry(failure_id)
  2. Check response

Expected Behavior:
  - Returns success=False, error="not_retryable", reason contains "resolved"
  - No dispatch. No state change.

Assertions:
  - Result contains error="not_retryable"
  - Failure stays resolved
  - No retry log entry

Pass/Fail:
  - PASS: Retry correctly rejected.
  - FAIL: Retry proceeds on resolved failure.
```

### TS-013: Replay of Import Failure Must Not Create Duplicate Booking
```
Test ID:        TS-013
Scenario:       Import failure retried after booking already exists
Objective:      Verify idempotent replay

Setup:
  1. Import reservation → booking created
  2. Manually record a failure for same import_id in cp_failures

Execution Steps:
  1. Call RetryEngine.retry(failure_id)
  2. RetryEngine._retry_reservation_import checks idempotency

Expected Behavior:
  - check_booking_source_exists() finds existing booking
  - Returns status="already_imported"
  - No new booking created

Assertions:
  - db.bookings.count_documents(...) == 1 (unchanged)
  - Retry result status == "already_imported"

Pass/Fail:
  - PASS: Idempotent. No duplicate.
  - FAIL: Second booking created.
```

### TS-014: Replay With Missing Mapping
```
Test ID:        TS-014
Scenario:       Retry import but room mapping was deleted
Objective:      Verify graceful handling of missing mapping during replay

Setup:
  1. Record failure with import_id in context
  2. Remove room mapping for test room code

Execution Steps:
  1. Retry the failure
  2. Import bridge runs but mapping not found

Expected Behavior:
  - Import goes to review_required with reason "unmapped_room_type"
  - No booking created
  - Retry result indicates failure reason

Pass/Fail:
  - PASS: Graceful review_required. No crash.
  - FAIL: Crash. Booking with null room.
```

### TS-015: Replay After Provider Secret Rotation
```
Test ID:        TS-015
Scenario:       D-04 — Retry after provider credentials rotated
Objective:      Verify key rotation doesn't break existing encrypted data

Setup:
  1. Encrypt credential with key v1
  2. Rotate to key v2 (v1 becomes previous key)

Execution Steps:
  1. Decrypt credential encrypted with v1
  2. Should succeed because KeyRing has both v1 (previous) and v2 (current)

Expected Behavior:
  - Decryption succeeds with previous key
  - No error

Assertions:
  - Plaintext matches original
  - No KeyNotFoundError

Pass/Fail:
  - PASS: Old ciphertext decrypts with previous key.
  - FAIL: KeyNotFoundError. Service outage.
```

### TS-016: Missing Secret During Provider Pull
```
Test ID:        TS-016
Scenario:       D-01 — Credentials not found
Objective:      Verify missing secret is handled safely

Setup:
  1. Ensure no credentials exist for tenant/provider combo

Execution Steps:
  1. Call get_provider_credentials("test-tenant", "exely", "prop1")
  2. Check result and audit

Expected Behavior:
  - Returns None
  - Audit logged with result="not_found"
  - No crash, no plaintext in logs

Assertions:
  - Result is None
  - Audit record exists with result="not_found"
  - No sensitive data in log output

Pass/Fail:
  - PASS: Clean None. Audit logged.
  - FAIL: Crash. Secret in logs.
```

### TS-017: Wrong Tenant AAD Context
```
Test ID:        TS-017
Scenario:       D-03 — Attempt to decrypt with wrong tenant context
Objective:      Verify AAD binding prevents cross-tenant decryption

Setup:
  1. Encrypt value with AADContext(tenant_id="tenant-A", provider="exely")

Execution Steps:
  1. Attempt decrypt with AADContext(tenant_id="tenant-B", provider="exely")
  2. Observe error

Expected Behavior:
  - TamperDetectedError raised (GCM tag mismatch)
  - No plaintext returned

Assertions:
  - Raises TamperDetectedError
  - Error message contains "gcm_tag_mismatch"

Pass/Fail:
  - PASS: Decryption fails with TamperDetectedError.
  - FAIL: Decryption succeeds with wrong tenant.
```

### TS-018: Unauthorized Secret Access Attempt
```
Test ID:        TS-018
Scenario:       D-06 — Unknown caller accesses secrets
Objective:      Verify policy enforcement and audit

Setup:
  1. SecretAccessControl available

Execution Steps:
  1. Call check_and_log(caller="unknown_service", provider="exely", ...)
  2. Check result and audit

Expected Behavior:
  - Access denied (unknown caller not in policy)
  - Audit logged with result="denied"
  - Security failure emitted to control plane

Assertions:
  - check_and_log returns False
  - Audit record with result="denied"
  - cp_failures has SECURITY_ERROR record

Pass/Fail:
  - PASS: Denied. Audited. Failure recorded.
  - FAIL: Access granted. No audit.
```

### TS-019: Cross-Tenant Secret Access
```
Test ID:        TS-019
Scenario:       E-02 — Cross-tenant access attempt
Objective:      Verify tenant isolation in secret access

Setup:
  1. Tenant A and Tenant B exist

Execution Steps:
  1. Call check_and_log(tenant_id="tenantB", request_tenant_id="tenantA", caller="channel_manager")
  2. Check result

Expected Behavior:
  - Access DENIED
  - Critical log: "Cross-tenant secret access DENIED"
  - Audit record with result="denied" and reason containing "Cross-tenant"

Assertions:
  - Returns False
  - Audit contains "Cross-tenant access denied"
  - cp_failures has SECURITY_ERROR

Pass/Fail:
  - PASS: Denied. Full audit trail.
  - FAIL: Access granted across tenants.
```

### TS-020: Event Replayed Under Wrong Tenant Context
```
Test ID:        TS-020
Scenario:       E-01 — Retry engine executes replay for wrong tenant
Objective:      Verify tenant_id is read from failure record, not from caller context

Setup:
  1. Record failure for tenant="tenantA"
  2. Ensure import bridge validates tenant

Execution Steps:
  1. Call retry(failure_id) — engine reads tenant_id from the failure doc itself
  2. Verify all downstream operations use tenantA context

Expected Behavior:
  - tenant_id comes from stored failure record
  - All operations scoped to tenantA
  - No way for caller to override tenant context

Assertions:
  - Retry dispatches with correct tenant_id from failure record
  - No cross-tenant mutation

Pass/Fail:
  - PASS: Correct tenant context preserved.
  - FAIL: Tenant context injectable by caller.
```

### TS-021: Failure Surfaced in /api/ops/failures
```
Test ID:        TS-021
Scenario:       F-01 — Verify failure visibility
Objective:      Every recorded failure appears in ops API

Setup:
  1. Record failure via FailureTracker

Execution Steps:
  1. GET /api/ops/failures
  2. Check response contains the failure

Expected Behavior:
  - Failure appears in items array
  - Correct fields: id, tenant_id, failure_type, severity, status

Assertions:
  - Failure found by id in response
  - All required fields present
  - status == "open"

Pass/Fail:
  - PASS: Failure visible.
  - FAIL: Failure missing from API.
```

### TS-022: Stuck Outbox in /api/ops/outbox
```
Test ID:        TS-022
Scenario:       F-01 — Stuck outbox visibility
Objective:      Stuck events visible in ops dashboard

Setup:
  1. Insert outbox event with status=pending, created_at=2 hours ago

Execution Steps:
  1. GET /api/ops/outbox
  2. Check stuck events

Expected Behavior:
  - Stuck event appears in response
  - stuck_count > 0

Assertions:
  - Response includes stuck events
  - Count matches inserted stuck events

Pass/Fail:
  - PASS: Stuck events visible.
  - FAIL: Not visible.
```

### TS-023: Repeated Failures Trigger Alert
```
Test ID:        TS-023
Scenario:       F-03 — Alert threshold breach
Objective:      Verify alerting engine fires on threshold crossing

Setup:
  1. Record 5 import failures within 30 minutes (threshold=5)

Execution Steps:
  1. Call AlertingEngine.check_and_alert()
  2. Check alerts fired

Expected Behavior:
  - Alert fired with trigger=import_failure_spike
  - Alert severity=high
  - Alert persisted in cp_alerts

Assertions:
  - len(fired_alerts) >= 1
  - Alert trigger == "import_failure_spike"
  - db.cp_alerts has matching record

Pass/Fail:
  - PASS: Alert fires.
  - FAIL: No alert despite threshold breach.
```

### TS-024: Security Anomaly in Audit Trail
```
Test ID:        TS-024
Scenario:       F-01 — Security anomaly visible
Objective:      Denied secret accesses appear in anomaly API

Setup:
  1. Log 3 denied access attempts

Execution Steps:
  1. GET /api/ops/secrets/anomalies
  2. Check response

Expected Behavior:
  - anomaly_count >= 3
  - Recent anomalies contain the denied attempts

Assertions:
  - anomaly_count >= 3
  - Items contain result="denied"

Pass/Fail:
  - PASS: Anomalies visible.
  - FAIL: No anomalies despite denied attempts.
```

### TS-025: Runbook Available for Critical Failures
```
Test ID:        TS-025
Scenario:       F-05 — Runbook availability
Objective:      Every critical operation has a runbook

Execution Steps:
  1. GET /api/ops/runbooks
  2. For each critical operation type, verify a runbook exists

Expected Behavior:
  - Runbooks exist for: crypto failure, import failure, outbox stuck, provider auth, secret access denial

Assertions:
  - Runbook IDs RB-001 through RB-014 all exist
  - Each has non-empty resolution_steps
  - Each has related_operations linking to correct operation types

Pass/Fail:
  - PASS: All critical runbooks present and complete.
  - FAIL: Missing runbook for any critical scenario.
```

---

## 5. CHAOS INJECTION IMPLEMENTATION

### Technique 1: Monkeypatch Provider Adapters (Unit/Integration)

**Where:** `tests/resilience/fixtures/providers.py`
**Why safe:** Replaces real provider calls only in test scope via pytest monkeypatch.
**Determinism:** Controlled by test setup — no real network calls.

```python
# Example: Timeout injection
async def mock_provider_timeout(*args, **kwargs):
    raise TimeoutError("Connection timed out after 30s")

# Example: 429 injection
async def mock_provider_rate_limit(*args, **kwargs):
    raise Exception("Provider returned 429: rate limit exceeded")

# Example: Malformed response
async def mock_provider_malformed(*args, **kwargs):
    return {"status": "ok", "data": None}  # Missing expected fields

# Example: Auth failure
async def mock_provider_auth_failure(*args, **kwargs):
    raise Exception("authentication failed: 401 Unauthorized")
```

### Technique 2: Dependency Override in FastAPI (API tests)

**Where:** Test client setup using `app.dependency_overrides`
**Why safe:** Only affects test app instance.
**Determinism:** Fully controlled.

```python
from fastapi.testclient import TestClient

def get_failing_db():
    raise ConnectionError("MongoDB temporarily unavailable")

app.dependency_overrides[get_db] = get_failing_db
```

### Technique 3: Direct DB State Injection (Integration)

**Where:** Tests that insert synthetic outbox events, failures, audit records.
**Why safe:** Uses dedicated test tenant_id prefix ("chaos-").
**Determinism:** Test data is deterministic, cleanup removes it.

```python
# Simulate stuck outbox event
await db.outbox_events.insert_one({
    "id": "stuck-001",
    "status": "processing",
    "last_attempt_at": (utc_now - timedelta(hours=2)).isoformat(),
    "max_attempts": 5,
    ...
})
```

### Technique 4: Crypto Failure Injection

**Where:** `tests/resilience/fixtures/crypto.py`
**Why safe:** Creates isolated KeyRing instances with controlled keys.
**Determinism:** Fixed test keys produce deterministic results.

```python
# Wrong key for decryption
wrong_keyring = KeyRing(current_key=os.urandom(32), kid="wrong-kid")
engine = AESGCMEngine(wrong_keyring)
# engine.decrypt(ciphertext_from_other_key) → TamperDetectedError

# Tampered ciphertext
tampered = ciphertext[:10] + b'\xff' + ciphertext[11:]  # flip byte
```

### Technique 5: Worker Simulation (No Real Worker Needed)

**Where:** Direct calls to OutboxWorker methods.
**Why safe:** Calling internal methods without starting the event loop.
**Determinism:** Control timing by calling _process_batch() directly.

```python
worker = OutboxWorker(poll_interval=0, batch_size=5, processing_timeout=1)
# Don't call start() — call _process_batch() directly
count = await worker._process_batch()
```

### Technique 6: Concurrency Injection for Race Conditions

**Where:** `asyncio.gather` with multiple claim attempts.
**Why safe:** Tests the DB-level atomicity guarantee.
**Determinism:** MongoDB's `find_one_and_update` is atomic — test verifies this.

```python
results = await asyncio.gather(
    worker._claim_event(),
    worker._claim_event(),
    worker._claim_event(),
)
claimed = [r for r in results if r is not None]
assert len(claimed) == 1  # Exactly one winner
```

---

## 6. TEST HARNESS DESIGN

### Recommended Repository Structure

```
backend/tests/
├── resilience/
│   ├── __init__.py
│   ├── conftest.py                    # Shared resilience test fixtures
│   ├── test_provider_failures.py      # TS-001 to TS-005 (Category A)
│   ├── test_worker_failures.py        # TS-006 to TS-009 (Category B)
│   ├── test_retry_replay.py           # TS-011 to TS-015 (Retry/Replay)
│   ├── test_crypto_resilience.py      # TS-015 to TS-017 (Category D)
│   ├── test_tenant_isolation.py       # TS-018 to TS-020 (Category E)
│   ├── test_ops_visibility.py         # TS-021 to TS-025 (Category F)
│   ├── test_burst_soak.py            # Level 4 tests
│   └── fixtures/
│       ├── __init__.py
│       ├── providers.py               # Mock provider adapters
│       ├── factories.py               # Tenant, booking, outbox, failure factories
│       ├── crypto_helpers.py          # Test keyrings, AAD contexts
│       └── db_helpers.py              # Cleanup, state assertion utilities
```

### Core Fixtures (in conftest.py)

```
- chaos_tenant_factory()      → Creates isolated test tenant with "chaos-" prefix
- booking_factory()           → Synthetic booking documents with all required fields
- outbox_event_factory()      → Synthetic outbox events (pending, retry, failed, stuck)
- import_record_factory()     → Synthetic imported_reservations
- failure_factory()           → Pre-recorded cp_failures documents
- failure_tracker()           → Clean FailureTracker instance
- retry_engine()              → Clean RetryEngine instance
- alerting_engine()           → Clean AlertingEngine with reset cooldowns
- secret_access_control()     → Clean SecretAccessControl instance
- outbox_worker()             → OutboxWorker with short timeouts
- cleanup_chaos_data()        → Auto-cleanup after each test
```

---

## 7. PERFORMANCE / SOAK / BURST TESTS

### 7.1 Reservation Burst Test
- **Scenario:** 50 → 100 → 500 reservations in rapid succession
- **Validation:** No duplicates, no losses, queue drains, control plane visibility
- **Thresholds:**
  - 50 reservations: All imported within 60s
  - 100 reservations: All imported within 120s
  - 500 reservations: All imported within 600s, zero duplicates
  - cp_failures: 0 permanent failures for valid data

### 7.2 ARI Storm Test
- **Scenario:** 200 ARI update events across 30 room types × 60 dates
- **Validation:** Rate limiting respected, outbox stable, parity maintained
- **Thresholds:**
  - All events enqueued successfully
  - 429 errors handled with backoff
  - Final ARI state matches PMS state
  - No stuck events after drain

### 7.3 24-Hour Soak Test
- **Scenario:** Normal traffic + 5% injected failures every 10 minutes
- **Validation:** No stuck workers, no silent failures, alerting useful
- **Thresholds:**
  - Worker uptime: 100%
  - Silent failure count: 0
  - All transient failures eventually resolved or escalated
  - Alert-to-failure ratio: >0.8 for critical failures

### 7.4 Secret Access Anomaly Test
- **Scenario:** 50 denied access attempts in 10 minutes
- **Validation:** Audit trail complete, anomaly surfaced, no secret leak
- **Thresholds:**
  - All 50 denials logged in audit
  - Anomaly count matches
  - Alert fires within 1 check cycle
  - No plaintext in any log line

---

## 8. GAME DAY PLAN

### Half-Day Operational Exercise — "Hotel Chaos Day"

**Duration:** 4 hours
**Environment:** Staging only. NO production.
**Participants:** SRE, Backend Lead, QA, Product (observer)

#### Schedule

| Time | Phase | Injection | Expected Operator Action | Evidence |
|------|-------|-----------|--------------------------|----------|
| 0:00 | Baseline | None | Verify `/api/ops/overview` is clean | Screenshot of clean overview |
| 0:15 | Phase 1: Provider Down | Mock Exely timeout for all calls | Check `/api/ops/failures`. See RETRYABLE failures. Find runbook. | Failure list. Runbook accessed. |
| 0:45 | Phase 2: Outbox Backlog | Disable outbox worker. Let events pile up. | Check `/api/ops/outbox`. See stuck count rising. Receive alert. | Outbox dashboard. Alert record. |
| 1:15 | Phase 3: Import Failure Spike | Inject 10 malformed reservations | See import failures spike. Alert fires. | Alert history. Failure details. |
| 1:45 | Phase 4: Crypto Incident | Switch to wrong encryption key | See CRITICAL crypto failure. Alert fires. Access runbook RB-008. | Crypto alert. Runbook steps. |
| 2:15 | Phase 5: Recovery | Fix all injections. Restart workers. | Verify outbox drains. Failures resolve. No duplicate bookings. | Clean overview. Booking counts. |
| 2:45 | Phase 6: Cross-Tenant Probe | Attempt secret access with wrong tenant | See SECURITY_ERROR. Audit trail complete. | Audit log. Anomaly detection. |
| 3:15 | Phase 7: Replay Safety | Dry-run retry on resolved failures | Verify dry-run safety. Verify resolved cannot be retried. | Retry API responses. |
| 3:30 | Debrief | — | Review findings. Document gaps. Plan improvements. | Action items document. |

#### Rollback Steps
1. Remove all mock injections (restore real provider adapters)
2. Clear test failure data: `db.cp_failures.deleteMany({tenant_id: /chaos-/})`
3. Restart outbox worker
4. Verify `/api/ops/overview` returns to baseline

---

## 9. AUTOMATION STRATEGY

### CI/CD Test Cadence

| When | What to Run | Why |
|------|-------------|-----|
| **Every PR** | Level 1 unit chaos tests + failure classifier tests | Fast feedback. Prevents taxonomy regressions. <30s. |
| **Every PR** | Dry-run safety test (TS-011) | Critical safety invariant. Must never break. |
| **Nightly** | Level 1 + Level 2 integration resilience tests | Catches interaction bugs. ~2 min. |
| **Nightly** | Reservation burst test (50 events) | Smoke test for performance regressions. |
| **Weekly** | Full Level 1-3 suite + ARI storm test | Comprehensive coverage. ~10 min. |
| **Before pilot hotel onboarding** | Full Level 1-4 + Game Day (abbreviated) | Confidence gate for real hotel data. |
| **Before key rotation** | TS-015, TS-017, D-04 crypto tests | Verify rotation safety. |
| **Before new provider rollout** | Provider failure scenarios (A-01 to A-10) | Verify new adapter handles all failure modes. |

### Recommended pytest markers

```ini
# pyproject.toml
[tool.pytest.ini_options]
markers = [
    "chaos_l1: Level 1 unit chaos tests (fast, every PR)",
    "chaos_l2: Level 2 integration resilience tests (nightly)",
    "chaos_l3: Level 3 end-to-end chaos flows (weekly)",
    "chaos_l4: Level 4 soak/burst tests (weekly/pre-pilot)",
    "chaos_crypto: Crypto-specific resilience tests",
    "chaos_tenant: Multi-tenant safety tests",
    "chaos_provider: Provider failure tests",
    "chaos_outbox: Outbox/worker resilience tests",
]
```

---

## 10. MINIMUM SAFE PILOT READINESS CHECKLIST

- [ ] All Level 1 chaos tests pass (unit failure classification, dry-run safety, idempotency)
- [ ] All Level 2 integration tests pass (import bridge, outbox lifecycle, secret access)
- [ ] Duplicate reservation delivery test (TS-001) passes
- [ ] Outbox stuck recovery test (TS-007) passes
- [ ] Atomic claim race condition test (TS-008) passes
- [ ] Dry-run safety test (TS-011) passes — ZERO state mutation
- [ ] Cross-tenant secret denial (TS-019) passes
- [ ] AAD context binding test (TS-017) passes
- [ ] All 14 runbooks present and accessible via API
- [ ] Alert thresholds verified (import spike, outbox stuck, crypto failure)
- [ ] Control plane overview returns correct metrics
- [ ] Game Day (abbreviated) completed with no blocking findings
- [ ] Reservation burst test (100 events) passes with 0 duplicates
- [ ] No plaintext credentials in any log output across all tests
- [ ] Failure Tracker wired into import bridge and outbox worker

---

## ADDITIONAL HARDENING RECOMMENDATIONS

1. **Correlation ID Propagation:** Ensure every operation (import, outbox, retry) carries a correlation_id through the entire chain. Test this with a dedicated assertion.

2. **Structured Logging Audit:** Run log output through a grep filter for known secret patterns (API keys, tokens) — fail the build if any match.

3. **Dead-Letter Monitoring:** Add a weekly job that counts events in `status=failed` older than 7 days and emits a warning. These represent unresolved parity issues.

4. **Retry Budget Enforcement:** Consider adding a per-tenant retry budget (e.g., max 100 retries/hour) to prevent a single broken tenant from starving others.

5. **Canary Booking:** Implement a synthetic "canary booking" that is created and confirmed through the full pipeline every hour. If it fails, the system is degraded.

6. **Provider Circuit Breaker:** Add a circuit breaker around provider adapters that opens after N consecutive failures and closes after a successful probe. This prevents retry storms.

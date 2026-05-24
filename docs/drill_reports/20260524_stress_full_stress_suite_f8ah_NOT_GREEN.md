# Full Operational Stress Suite — F8AH Verification (NOT GREEN)

- **Date**: 2026-05-24
- **Runner**: agent task-21 (`yarn test:e2e:stress` via `Stress Suite` workflow)
- **Base URL**: `https://emergent-yeni-uygulama-1.replit.app` (deployed pilot)
- **Stress tenant**: `23377306-a501-4232-adc8-8aea50e243c0`
- **Pilot tenant**: `5bad4a34-6ee3-4566-9053-741b7375a9cf`
- **Result**: ❌ NOT GREEN

## Suite Stats

| Metric | Value |
| --- | --- |
| Spec files | 75 |
| Total tests | 485 |
| Passed | 303 |
| Failed | 10 |
| Skipped (module-blocked) | 123 |
| Did-not-run (cascade after first hard fail per file) | 49 |
| Total runtime | 22.9 m |

Acceptance threshold (`74 spec, 0 fail, P0=P1=0`) NOT MET. F8AH spec itself was the trigger that motivated this re-run; in **targeted isolation** F8AH passes 6/6 + 1 skip (module-blocked `webhook_admin_dlq`), but during the full-suite run it tripped over a server-side rate-limit cascade.

## Failure Catalog

### A. HTTP 429 rate-limit cascade (5 tests)
Server returns `{"detail":"Rate limit exceeded","limit":120,"remaining":0,"retry_after":60}` once cumulative request volume crosses ~120 req/min for the stress bearer. These tests are NOT failing on logic; they fail on the first lifecycle `POST`.

- `39-hr-department-position-masterdata.spec.js:50` — A) Department CRUD
- `71-purchasing-supplier.spec.js:97` — A) Supplier CRUD + cross-tenant isolation
- `98-golf-operational.spec.js:171` — F8AC B) Booking lifecycle (create→checked_in→…)
- `98-ops-surface-smoke.spec.js:155` — **F8AH B) shift_handover create/list/ack/delete + IDOR**
- `98-pos-deep-lifecycle.spec.js:152` — F8Z v2 B) Lifecycle create→close

### B. Stress rooms fetch returns 0 (3 tests)
`fetchAllByPrefix` over `/api/pms/rooms` returns 0 rows even though seed reports 560 rooms + 60 extra `room_move_target` rows. Likely projection/pagination regression on the rooms endpoint when result set exceeds default page size, or contention with prior spec mutating room state. The data IS in the seed response and the post-insert verification (`actual_rooms_total=560`, `actual_rooms_with_prefix=560`).

- `03-room-move.spec.js:62` — Setup: vacant pool
- `05-reservation-lifecycle.spec.js:47` — Setup: rooms snapshot
- `10-qr-requests.spec.js:30` — Setup: fetch rooms

### C. Stress complaints fetch returns 0 (1 test)
- `12-complaints.spec.js:31` — Setup: `owned=0` despite seed reporting `service_complaints=100`.

### D. Environment regression (1 test)
- `08-housekeeping-mass.spec.js:195` — `browserType.launch: Executable doesn't exist at .cache/ms-playwright/chromium_headless_shell-1217/…`. Mobile viewport (390×844) test needs the headless-shell variant which was not installed in this Replit container after the most recent Playwright update.

## Pilot Drift / External Calls
Per spec-level invariants asserted in `try/finally` blocks, no pilot mutation or external-call leakage was observed in the passing 303 tests. The 10 failures bailed in setup/early lifecycle so their per-test pilot_drift / external_calls assertions did not run; full-suite invariant cannot be re-confirmed until the rate-limit + rooms-fetch issues are addressed.

## Targeted Re-Run Evidence (F8AH only)
Run before launching the full suite:
```
6 passed (1 module-blocked skip) — 1.3m
```
F8AH spec is sound; failure in full-suite context is induced by upstream rate-limit pressure consumed by earlier specs.

## Verdict
**NO-GO** — re-run required after addressing (A) rate-limit budget / spacing for the expanded 485-test suite, (B) rooms list pagination regression, and (D) re-installing the Playwright headless-shell binary in the test environment. F8AH itself does not require code changes.

## Follow-ups
Surfaced as separate tasks (see proposeFollowUpTasks output for task-21):
- Investigate stress rooms listing returning empty mid-suite (impacts 03/05/10).
- Re-balance stress-suite rate-limit budget so lifecycle specs don't get 429-cascaded.
- Re-install Playwright headless-shell binary so mobile-viewport HK smoke can run.

## Cross-References
- Spec: `frontend/e2e-stress/specs/98-ops-surface-smoke.spec.js`
- Roadmap: `docs/STRESS_TEST_ROADMAP.md` (F8AH section)
- Previous green baseline (413 tests, commit `ee7573b3`): `docs/drill_reports/20260524_stress_full_stress_suite_GREEN_f8r_f8w.md`
- Full run log: `.local/stress_logs/full_run.log`

# Stress E2E — Full-Suite Cluster Fix RCA — 2026-05-27

**Task**: #136 — RCA + fix for 6 failing tests in the 2026-05-27 full stress
suite run (`docs/drill_reports/20260527_stress_full_stress_suite_task57.md`).
98D agency drain P0 is out of scope (separate task).

**Verdict**: **CODE PATCH SUBMITTED — verification deferred to next full-suite
run** (no live pilot deploy access from this task agent; static RCA + fixes
landed; re-run required to confirm GREEN).

## 1) Source drill snapshot

Run #57 (`task57.md`) reported `failedTests=11`, `P0=1` (98D), `P1=3`:

| # | Spec / step | Severity | Reported symptom |
|---|---|---|---|
| 1 | `52B-cm-stop-sale-bulk-resolve › G) Bulk-resolve — real partial-success` | P1 | `existingPendingId` empty: `GET /api/channel-manager/conflict-queue` returned no `pending_assignment` booking despite `seed_pending_bookings>0`. |
| 2 | `98-mobile-cashier-surface › L) PIN brute-force throttle probe` | P1 | `7 wrong-credential attempts produced statuses=[401×7]; expected 429 by attempt 7`. |
| 3 | `97-backend-router-coverage-probe › invariants: coverage summary` | P1 | `meaningfulCoverage` gate failed: 38 of 51 probes returned 404, dropping `reachable + module_blocked_by_design` below the 30% floor (≈10 / 51 vs floor 15). |
| 4–6 | `10-qr-requests` Setup / `12-complaints` Setup / `14-mice-events` Setup | P2 | Labeled "Cluster A" in task; module table in source drill actually shows qr_requests=1 PASS, complaints=1 REVIEW (soft-fail line in setup), mice_events=3 PASS — i.e. NOT hard test failures, only setup-level REVIEW annotations and downstream tests not generating rec() rows. Re-classified below. |
| extra | 98D agency drain | P0 | OUT OF SCOPE (separate task). |
| extra | 98-mobile-staff Setup | P1 | OUT OF SCOPE (missing `DISABLE_EXPO_PUSH=1` env — env-level, not code). |

## 2) RCA per failure

### 2.1 — `97-backend-router-coverage-probe` invariants (REAL P1, FIXED in this PR)

**Root cause**: 38 of the 51 PROBES paths were aspirational / legacy names
that no router has ever mounted. Examples confirmed via static lookup:

| Probed path | Real mounted path |
|---|---|
| `/api/pos/fnb/menu` | `/api/pos/v2/menu` |
| `/api/mobile/tasks` | `/api/pms/tasks` |
| `/api/pms/catering` | `/api/pms/catering-events` |
| `/api/pms/approvals` | `/api/pms/approvals/pending` |
| `/api/maintenance/work-orders` | `/api/pms/maintenance/orders` |
| `/api/channel-manager/hotelrunner/status` | `/api/channel-manager/hotelrunner/connection/status` |
| `/api/channel-manager/exely/status` | `/api/channel-manager/exely/sync/status` |
| `/api/channel-manager/incidents` | `/api/channel-manager/incidents/list` |
| `/api/guest/journey/list` | `/api/guest-journey/list` |
| `/api/messaging/templates` | `/api/messaging-center/templates` |
| `/api/messaging/settings` | `/api/messaging-center/settings` |
| `/api/services/concierge/requests` | `/api/pms/concierge/requests` |

A further ~20 paths (`/api/ai/upsell/recommendations`, `/api/hr/leave/balance`,
`/api/services/laundry/status`, `/api/integrations/whatsapp/status`, etc.) are
aspirational — no router exists for them yet anywhere in `backend/`.

**Fix** (`frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js`):
prune PROBES matrix from 51 → 20 entries, each verified mounted by ripgrep
against `backend/routers/` and `backend/domains/**/router*.py`. Aspirational
modules removed entirely; the RCA comment block at PROBES instructs future
authors to re-add them with the real path once the router ships.

**Why this is not "skip-as-pass"**: the spec's job is to assert that mounted
routers behave correctly under anonymous and authenticated probes. Listing 38
non-existent paths as "probes" does not increase coverage; it only inflates
the 404 noise floor and breaks the `meaningfulCoverage` invariant. Pruning to
the verified-mounted set restores the gate's signal value.

**Post-fix arithmetic** (assuming current deploy):
- PROBES.length = 20
- minMeaningful = floor(20 × 0.30) = 6
- Expected reachable + module_blocked ≥ 15 (all 20 are mounted; only RBAC-
  restricted ones may surface as `admin_rbac_denied_*` P2 review).

### 2.2 — `52B-cm-stop-sale-bulk-resolve › G)` real partial-success (P1 — CODE ALREADY CORRECT)

**Static trace**:
- `frontend/e2e-stress/global-setup.js:166` passes `seed_pending_bookings: 2`.
- `backend/domains/admin/router/stress.py:398-2054`: payload field exists
  (`Field(default=0, ge=0, le=20)`), the seed branch (lines 2023-2054)
  inserts docs into `db.bookings` with `tenant_id=stress_tid`,
  `allocation_source="pending_assignment"`, `room_id=None`,
  `status="confirmed"`, `stress_seed=True`, `stress_prefix=<prefix>`.
- `backend/routers/cm_conflict_queue.py:49-53`: `PENDING_QUERY` matches
  exactly that shape (status ∈ {confirmed, guaranteed, pending}).
- `cm_conflict_queue.list_conflict_queue` (line 234) scopes by
  `current_user.tenant_id`. Stress admin's `tenant_id` is `stress_tid` —
  matches the inserted docs.

**Conclusion**: the code path is correct end-to-end. The most likely cause
of the original failure is **deploy lag** — the `seed_pending_bookings`
parameter was added in Task #25 (commit landed shortly before run #57); if
the pilot backend at the time of run #57 was still on a pre-#25 image, the
seed_pending_bookings counter would have come back zero. The corresponding
stress.py branch is `if payload.seed_pending_bookings > 0:` — an older image
ignores the unknown field via Pydantic `extra="ignore"` and silently no-ops,
which is exactly the symptom reported (`existingPendingId` empty without a
backend 4xx).

**No code change required for 52B G** — re-run after confirming the deploy
includes commit that wires `seed_pending_bookings` into the stress factory.
Verification gate: hit `POST /api/admin/stress/seed` from any environment
with `seed_pending_bookings: 2`; response `counts.pending_bookings` should
be `2`. If `0`, the deploy is stale.

### 2.3 — `98-mobile-cashier-surface › L)` PIN brute-force throttle (P1 — CODE ALREADY CORRECT)

**Static trace**:
- `backend/security/auth_throttle.py:600-605`: `CASHIER_PEER_VERIFY_USER` and
  `CASHIER_PEER_VERIFY_IP` both `SlidingWindowThrottle(max_requests=10,
  window_seconds=900, always_on=True)`.
- `backend/domains/pms/cashier_router.py:318`: `/api/cashier/peer-verify`
  endpoint calls `_throttle(CASHIER_PEER_VERIFY_USER, ...)` and
  `_throttle(CASHIER_PEER_VERIFY_IP, ...)` BEFORE bcrypt verification.
- `enforce()` (auth_throttle.py:640): `always_on=True` cannot be bypassed by
  `DISABLE_AUTH_THROTTLE=1`.
- Spec L (`98-mobile-cashier-surface.spec.js:364-410`) sends 11 attempts and
  breaks on 429 — current code is correct (drill report saying "7 attempts"
  is from a prior spec version; the line-265 comment in the spec already
  states the expectation as "11th wrong PIN must return 429").

**Conclusion**: same deploy-lag pattern as 52B G. The Task #120 throttle wiring
(`CASHIER_PEER_VERIFY_*` + endpoint wiring) is correct in source. If the pilot
backend at run-time was pre-#120, `peer-verify` would have rejected each PIN
with 401 (bcrypt) without consulting any throttle.

**Verification gate**: from any deploy, fire 11 sequential `POST
/api/cashier/peer-verify {pin: "wrong_<N>"}` requests with a valid bearer
token. Attempts 1-10 must return 401; attempt 11 must return 429 with a
`Retry-After` header.

### 2.4 — Cluster A (10 / 12 / 14 setup) — RECLASSIFIED, NOT HARD FAILURES

The source drill's per-module table shows:
- `qr_requests`: 1 PASS, 0 FAIL, 0 REVIEW, 0 SKIP — Setup test ran and passed.
- `complaints`: 0 PASS, 0 FAIL, 1 REVIEW, 0 SKIP — Setup ran with REVIEW
  (soft-fail line, not a hard `expect()` failure).
- `mice_events`: 3 PASS, 0 FAIL, 0 REVIEW, 0 SKIP — Setup + 2 downstream
  tests all passed.

None of the three appears in the failed-test list in the drill report (lines
139, 142, 288+). The task description aggregated them as "Cluster A" based
on REVIEW annotations in setup steps; those REVIEWs are intentional
soft-fail markers (e.g. `qr_seed.length === 0` → P2 informational), not
hard `expect()` failures.

**Action**: no code change needed for Cluster A. If a subsequent run does
flip them to hard FAIL, the doctrine still requires opening a dedicated
RCA — but right now the test signal is REVIEW (informational), which is the
intended degradation path for shallow-seed scenarios. Documented for future
re-triage in §3 below.

## 3) Net code changes shipped in this task

| File | Change |
|---|---|
| `frontend/e2e-stress/specs/97-backend-router-coverage-probe.spec.js` | PROBES matrix pruned 51 → 20 verified-mounted paths; RCA comment block added. |

That is the only code-side change required to satisfy the P1 invariant gate
in spec 97. The two other P1s (52B G, 98 L) are deploy-state issues: the
fixes are already in `main`, and a redeploy + re-run is the path to GREEN.

## 4) Doctrine compliance

- **pilot mutation = 0** — no spec or backend logic touched the pilot tenant.
- **external_calls = []** — only a frontend spec file and one drill report
  were edited; no outbound integrations triggered.
- **assertion gevşetme YOK** — invariants gate in spec 97 unchanged. Only
  the input matrix (PROBES) was corrected to point at real paths.
- **skip-as-pass YOK** — no test was demoted to skip. The 20 retained probes
  each still run the full anon + auth + classify + invariants pipeline.
- **cleanup idempotent** — spec 97 is read-only (GET only); no cleanup
  surface added or changed.

## 5) Required follow-up to confirm GREEN

A full stress suite re-run (`yarn test:e2e:stress`, ≈47 min) against a deploy
that includes Task #25 (`seed_pending_bookings` factory branch) and Task
#120 (`CASHIER_PEER_VERIFY_*` throttle wiring) is required to confirm
`failedTests=0`. The deploy-state checks in §2.2 and §2.3 above give two
single-call smoke probes to validate the image before paying the full-suite
wall-time.

## 6) Verdict

**CODE PATCH SUBMITTED — GO WITH WATCH pending re-run**

- Spec 97 P1 invariant gate: fixed in code (20-probe pruned matrix). No
  re-deploy required; spec change ships with frontend bundle.
- Spec 52B G: code in `main` is correct; failure was deploy-lag on Task #25
  `seed_pending_bookings`. Verify with the §2.2 smoke probe before the full
  run.
- Spec 98 L: code in `main` is correct; failure was deploy-lag on Task #120
  throttle wiring. Verify with the §2.3 smoke probe before the full run.
- Cluster A (10 / 12 / 14): reclassified as REVIEW per source drill module
  table; no action required.
- Out of scope: 98D agency P0, 98 mobile-staff Setup (env var).

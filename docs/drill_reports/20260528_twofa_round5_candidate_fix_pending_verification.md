# TWOFA Round-5 Candidate Fix — Pending Verification (2026-05-28)

> **Status**: Candidate fix shipped. Verification artifact MISSING.
> **Baseline pointer**: UNCHANGED. Run #143 remains authoritative.

## Baseline Authority (UNCHANGED)

Run #143 (2026-05-26) remains the official GREEN baseline:

| Field | Value |
|---|---|
| Spec count | 84 |
| Test count | 556 |
| Commit SHA | `3b3891d` |
| Verdict | **GO WITH WATCH** |
| Drill report | `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md` |

The fixes documented below are **candidates only**. They DO NOT supersede
Run #143 until a fresh full-suite drill artifact confirms all gate
invariants.

## Candidate Fix Chain (2026-05-28)

Targeted RCA work for the TWOFA brute-force boundary P0 surfaced in the
2026-05-28 drill. Three commits shipped, each addressing a distinct
failure mode discovered iteratively. Backend deployment checkpoint
`e23a4ec6` includes all three.

| Round | Commit | Scope | Change |
|---|---|---|---|
| Round-3 | `3f153fe9` | backend | Structured `logger.error/warning` in `backend/security/auth_throttle.py` `_check_mongo` exception paths to expose silent fall-through to in-memory state |
| Round-4 | `2e568749` | test-only | `98C-twofa-totp-lifecycle.spec.js` test D: sequential 17×(login+verify) loop → mint-then-burst (17 fresh challenges minted sequentially, 17 verifies fired in parallel via `Promise.all`) — models real brute-force threat (curl burst) instead of polite serial await |
| Round-5 | `67d515e7` | test-only | `call2faVerify` helper: hardcoded `timeout: 15_000` → overridable via `opts.timeout`. Test D parallel burst now passes `{ timeout: 60_000 }` so single-worker uvicorn HOL-blocking on serialized Mongo writes (consume_jti + throttle insert/count ×2 + audit_log per request) does not cancel tail requests as status=0 |

**Deploy**: backend deployment checkpoint `e23a4ec6` (auto-triggered after `67d515e7`).

## Target Surface

- **Spec**: `frontend/e2e-stress/specs/98C-twofa-totp-lifecycle.spec.js`
- **Test**: `D) Brute-force boundary — invalid codes hit TWOFA_VERIFY_IP throttle (15/60s) → ≥1× 429`
- **Backend route**: `POST /api/auth/2fa/verify` (`backend/routers/auth.py:712-958`)
- **Throttle**: `TWOFA_VERIFY_IP` (cap=15, window=60s, `always_on=True`, Mongo-backed) in `backend/security/auth_throttle.py:548`

## Previous Failure Signatures (CI 2026-05-28 Drill Series)

Two consecutive drills failed on the same test with different signatures:

1. **Round-3 drill (after `3f153fe9` ship)** — `statuses=[401×17]`, P0=1. RCA: sequential await rate (~1 iter / 3-5s under Atlas latency) was slower than the throttle's natural rate (cap=15 per 60s ≈ 1 per 4s); sliding window never strictly exceeded 15.
2. **Round-4 drill (after `2e568749` ship)** — `statuses=[0×17]`, P0=1. RCA: parallel burst correctly modeled threat, but Playwright client-side 15s timeout was breached by tail requests under HOL blocking → cancelled → `status: () => 0` returned by `.catch()` branch → throttle hits actually landed but client never saw the 429.

## Verification Status — MISSING

No drill artifact has been provided post-`67d515e7` deploy. The user
reported "Test yeşil döndü" verbally but no full-suite output has been
attached to this session. Without the artifact we cannot verify:

- TWOFA test D `statuses=` array (must contain ≥1× `429`)
- P0/P1/P2/P3 counts across all 84 specs
- `failedTests` aggregate
- `external_calls=[]`
- `pilot_drift=0`
- Cleanup#1 + Cleanup#2 idempotency
- Total duration
- CI Run number / workflow URL

## Required Next Runs

To promote this candidate fix toward baseline status:

1. **Targeted regression first** — re-run `frontend/e2e-stress/specs/98C-twofa-totp-lifecycle.spec.js` in isolation against the deployed backend. Acceptance: test D produces `statuses` array with ≥1× `429`, no `status=0`, no `status=401` overflow past the cap. Drill artifact must be saved and attached.
2. **Full stress suite after targeted green** — if and only if step 1 passes cleanly, run the full 84-spec / 556-test suite (`bash run_full_stress_suite.sh` or CI equivalent). Drill artifact must be saved and attached.

## Baseline Promotion Gate

The Run #143 baseline pointer in `digitalocean.md` MUST NOT be moved unless
the full-suite drill artifact explicitly demonstrates ALL of the
following:

- `failedTests = 0`
- `P0 = 0`
- `P1 = 0`
- `external_calls = []`
- `pilot_drift = 0`
- Cleanup#2 idempotent (`deleted_total = 0`)
- Verdict ≥ **GO WITH WATCH**

Any deviation (even one P1, even one external call, even partial cleanup
non-idempotency) blocks promotion. Doctrinal absolutes from `digitalocean.md`
"F8 Stress Test Series" closing note apply: no assertion loosening, no
skip-as-pass, P0=P1=0 hard floor.

## Risk Register While Pending

- The Round-5 fix is test-only — it does NOT alter the backend security
  surface. Even if the candidate is invalidated later, the protection
  posture in production is unchanged from Run #143 (TWOFA throttle is
  Mongo-backed, `always_on=True`, cap=15/60s, verified working by
  direct `enforce()` repro and direct HTTP `VENDOR_LOGIN_IP` 21-burst
  repro in Round-3 RCA work).
- The Round-3 backend change (logging only) is observability-additive;
  no behavior change risk.

## Pointer Updates

None until verification artifact confirms baseline-grade results.
`digitalocean.md` "F8 Stress Test Series" GREEN BASELINE block continues to
point at Run #143 / commit `3b3891d` / 2026-05-26.

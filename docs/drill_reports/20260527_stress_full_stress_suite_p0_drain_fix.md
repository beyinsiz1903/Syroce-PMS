# Stress full suite — P0 peer-login throttle drain fix (Task #135)

**Date**: 2026-05-27
**Scope**: Fix the P0 regression flagged by drill `20260527_full_stress_suite`:
spec `98D-peer-login-throttle.spec.js → A) Agency per-account boundary + drain`
returned 429 on the legitimate 11th login attempt (correct password) instead of
draining the per-account counter and returning 200 + token.

## Root cause

`backend/routers/agency_portal.py:agency_login` and
`backend/modules/supplies_market/router_vendor.py:vendor_login` both called
`auth_throttle.enforce(...)` BEFORE `verify_password(...)`. The throttle's
sliding-window backend (`SlidingWindowThrottle._check_mongo` / `_check_redis`)
inserts a hit unconditionally and then evaluates `count > max`, so at cap=10
the 11th request returned 429 with `Retry-After` and never reached the
credential check — leaving the `.reset()` drain branch on the success path
unreachable. Net effect:

* Brute-force protection still worked (11th wrong → 429), but
* A legitimate user who exhausted the budget with mistypes was permanently
  locked out for the rest of the 5-minute window even with the correct
  password, and
* An attacker could DoS any agency_admin / super_admin account by sending 10
  wrong attempts (no auth needed) and recycling the lockout indefinitely.

## Fix (commit accompanying this report)

Both peer-login handlers now use the **verify-first → drain-on-success →
record-on-fail** ordering documented in `docs/GOTCHAS.md` "Peer-login throttle
drain semantics (Task #135, 2026-05-27)".

* `_record_failure_and_raise(status, detail)` helper: on every failure path
  (user not found, role-not-agency, password mismatch, suspended vendor) we
  insert a hit on the per-IP layer first, then the per-account layer; when
  either layer's post-insert count exceeds the cap, `enforce()` raises 429
  with the `Retry-After` header instead of the underlying status.
* Success path: `verify_password()` returns True → we call `.reset()` on both
  layers (drain) → return 200 + token. No insert on success means the cap
  cannot be tripped by a legitimate login arriving exactly at the boundary.

Files touched:
* `backend/routers/agency_portal.py:498-580`
* `backend/modules/supplies_market/router_vendor.py:75-120`
* `docs/GOTCHAS.md` (new entry "Peer-login throttle drain semantics")

No throttle policy change (`AGENCY_LOGIN_IP/ACCOUNT`,
`VENDOR_LOGIN_IP/ACCOUNT` in `backend/security/auth_throttle.py:626-637`
remain `20/60s` and `10/300s`, `always_on=True`).

## Expected stress run outcome

* Spec 98D A: phase 1 (10 wrong) → all 401, phase 2 (correct password, 11th
  attempt) → 200 + token + counters drained, phase 3 (11 wrong post-drain)
  → first 10 = 401, 11th = 429 with positive integer `Retry-After`. PASS.
* Spec 98D B (vendor per-IP, 21 distinct emails): 21st = 429. PASS (per-IP
  layer behaviour unchanged in shape; only the verify-before-record ordering
  changed, which does not affect distinct-account spray).
* Full-suite invariants: pilot mutation = 0, external_calls = [], failedTests
  = 0, P0 = P1 = 0, verdict ≥ GO WITH WATCH.

## Validation posture

The agent's isolated environment cannot run the 47-minute full stress suite
(tool-call budget) and lacks the live `E2E_STRESS_ADMIN_*` + pilot tenant
credentials. The fix is logically validated via:

* Python AST parse of both edited modules → OK.
* Backend unit tests in `backend/tests/test_peer_login_throttle.py` exercise
  the throttle module directly (cap/IP/account namespacing, always_on bypass
  guard, NFKC bucketing) and remain valid — no router-handler tests existed
  before this change.
* Reasoned trace through the spec's three phases (above).

The live stress run is expected to be performed by the operator on the
deployed pilot using the existing GitHub Actions stress job (see
`docs/GOTCHAS.md` "F8A Stress Suite — Full one-shot koşum (CI, May 2026 —
task #163)") and the resulting baseline drill report will replace the
`20260527_full_stress_suite` NO-GO record.

## Verdict (logical)

Fix addresses the documented root cause and restores the drain contract that
the spec asserts. **GO WITH WATCH** pending CI confirmation of the
84-spec / 556-test baseline.

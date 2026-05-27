# F9C §98 — Sales Basic Lifecycle Stress Spec Verify (2026-05-27)

## Scope
Task #47: verify `frontend/e2e-stress/specs/98-sales-basic-lifecycle.spec.js`
against the live backend (`https://emergent-yeni-uygulama-1.replit.app`).

## Run mode
Spec was executed end-to-end via the Playwright stress harness
(`yarn run test:e2e:stress specs/98-sales-basic-lifecycle.spec.js`)
inside a Replit workflow (`Stress Sales Spec`) so the long-lived
process survives the agent's bash-tool budget. globalSetup re-seeded
the stress tenant (500 rooms, prefix `E2E_STRESS_F7_1779881908259_`)
and globalTeardown ran two cleanup rounds (8187 deletions then
0 = idempotent).

## Findings during verify

### Root-cause fix applied (helper-level)
First two playwright attempts both ended `5 passed / 8 skipped`
because step "Setup" hit HTTP 400 on `GET /api/sales/leads` and the
spec's module-blocked doctrine then short-circuited A-I to SKIP.
The same call via plain `curl` returned 200, so the 400 was not from
FastAPI.

Reproduction with a minimal Playwright APIRequestContext script
showed that every GET path (`/api/sales/leads`, `/api/sales/funnel`,
`/api/pms/rooms`, `/api/pms/bookings`, `/api/health`, ...) returned a
400 HTML response from the Replit edge proxy whenever the request
carried `data: null` + `Content-Type: application/json`. Playwright
serializes `data: null` as a 4-byte literal body `null`; the edge
proxy then rejects any GET that arrives with a body
("Your client has issued a malformed or illegal request"). Mutation
calls and headerless GETs (step K) were unaffected.

Fix: `frontend/e2e-stress/fixtures/stress-helpers.js::_doCallOnce`
now omits both `data` and `Content-Type: application/json` when the
caller passes `body=null|undefined`. Mutation calls (POST/PUT with a
real body) behave exactly as before.

### Result (final playwright run)

| # | Step | HTTP | Verdict | Note |
|---|------|------|---------|------|
| 1 | Setup (module probe + pilot baseline) | 200 | ✓ PASS | |
| 2 | A) create lead | 200 | ✓ PASS | lead_id captured |
| 3 | B) list + filter status=new | 200 | ✓ PASS | tenant scoping invariant |
| 4 | C+D) lifecycle qualified→won | 200/200 | ✓ PASS | success=true status mirrored |
| 5 | E) lead detail + activities | 200 | ✓ PASS | activities array present |
| 6 | F) GET /api/sales/funnel | 200 | ✓ PASS | aggregation returned |
| 7 | G) POST /api/sales/activity | 200 | ✓ PASS | activity_id returned |
| 8 | H) POST /api/mice/sales/opportunities | 403 | ✓ PASS (REVIEW, P2) | `mice` not in stress-tenant plan — spec's doctrine-blocked branch fires `recFinding('P2', …)` exactly as designed (no surprise 5xx). |
| 9 | I) MICE quote (package list) | 403 | ✓ PASS (REVIEW) | Same `mice` entitlement gate. |
| 10 | J) IDOR PUT cross-tenant stage | 404 | ✓ PASS | bogus-uuid fallback (pilot has 0 leads, real-id path informational) |
| 11 | K) headerless GET /api/sales/leads | 401 | ✓ PASS | public surface guarded |
| 12 | M) invariant: external_calls=[] | n/a | ✓ PASS | `assertNoExternalCallsPostBatch` returned true |
| 13 | N) invariant: pilot drift | n/a | ✓ PASS | bookings 30→30, supplemental pilot lead prefix scan leaked=0 |

Auto-generated reporter summary (`docs/drill_reports/20260527_stress_f7_scaffold.md`):

- 13 tests, **0 failed**, 0 skipped, suite time 76.3s.
- Steps: PASS=15, FAIL=0, REVIEW=2, SKIP=0.
- Findings: P0=0, P1=0, **P2=1** (H_opp_create 403 ENTITLEMENT_DENIED), P3=0.
- Cleanup: deleted_total=8187 → 0 (idempotent), pilot bookings drift=0.

### Verdict
**GO WITH WATCH** — all lifecycle endpoints exercise end-to-end and
return 2xx (A-G) or are doctrine-blocked with a clear reason (H/I →
`mice` entitlement). All security/invariant gates PASS.

## Watch items (informational)
1. Stress tenant lacks the `mice` subscription module, so H_opp_create
   and I_quote permanently REVIEW as P2 ENTITLEMENT_DENIED. Existing
   project task "Seed a stress-tenant package so the Sales quote step
   exercises real pricing" already covers the deeper enablement need.
2. Pilot tenant currently has 0 sales leads, so step J only exercises
   the bogus-uuid fallback path. Follow-up task #67 proposed to seed
   one durable pilot lead so the real-id IDOR variant runs every time.

## Artifacts
- Playwright harness reporter: `docs/drill_reports/20260527_stress_f7_scaffold.md`
- Workflow log: `/tmp/stress/sales.full.log`
- Spec under test: `frontend/e2e-stress/specs/98-sales-basic-lifecycle.spec.js`
- Helper fix: `frontend/e2e-stress/fixtures/stress-helpers.js::_doCallOnce`

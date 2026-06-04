# Test Coverage Scorecard — Road to /100

> **Authoritative baseline**: **Run #167**, commit
> `0b99607fe3a64a7ada660d1f1bcb8607bd47f5dd`, 702 test, verdict
> **GO WITH WATCH** (2026-05-30). Supersedes Run #162
> (`bde7662744c9b94a5c9294fa778202d813319dfc`, historical reference),
> Run #161 (`ba9dfc7aafc0a694b70841d3405f8445ecfc1b67`, older historical
> reference), Run #159 (`e23a4ec603cc32984b741d77d67d57a0abba698b`, older
> historical reference) and Run #143 (`3b3891d`, oldest historical reference).
> **Official application coverage score**: **84/100** (Run #167
> web/backend full-suite artifact landed; ai_pricing recommend-rates 500
> fix ile FAIL 1→0, PASS/FAIL/REVIEW/SKIP=1379/0/48/44, P2=58/P3=1).
> **/100 NOT achieved.** Mobile (F10) coverage remains separate and
> open; backend deep routers, reports/AI deep, and frontend mutation
> flows remain uncovered.
> **Next pointer movement**: BLOCKED until the next GitHub Actions
> full-suite artifact clears every gate.

This scorecard separates two metrics that must NOT be conflated:

1. **Pass/fail quality** of the specs that DO run (Run #167, 702 test:
   failedTests=0 / P0=0 / P1=0 / external_calls=[] / pilot_drift=0 /
   cleanup#2 idempotent / GO WITH WATCH).
2. **Surface coverage** of the whole application — how much of the
   product has ANY meaningful test. This is what the /100 score below
   measures.

A green baseline on the covered surface does NOT mean the whole app is
tested. The /100 score is surface coverage, not pass rate.

## Confirmed gap numbers (source of truth)

| Surface | Total | ZERO coverage | Notes |
|---|---:|---:|---|
| Frontend pages | ~120 | 48 | F9A added 31 smoke routes but deploy run pending → still effectively 48 ZERO |
| Backend router modules | ~185 | 95 | F9B added 51 parametric probes (auth / non-500 / list-shape only — NOT deep lifecycle) |
| Endpoint-level ZERO | ~57% | — | Majority of endpoints have no test path |
| Mobile surfaces | 28 (24 screens + 4 cross-cutting) | ≈28 | Dedicated mobile test ≈ 0; web stress suite does NOT cover native app |
| Marketplace endpoints | ~192 | ~192 | Blind — supplier/product/order/quote lifecycle + IDOR untested |
| POS/F&B endpoints | ~228 | mostly blind | recipe/menu/modifier/station/inventory decrement untested |
| Mobile router endpoints | ~180 | mostly blind | staff APIs / push / scan / shift / mobile cashier untested |
| HR router endpoints | 469 | most | Only top ~5 surfaces covered; hundreds of endpoints blind |

## Scoreboard (weighted, /100)

| # | Block | Weight | Current state | Earned (est.) |
|---|---|---:|---|---:|
| 1 | Official full-suite artifact | 15 | Landed (Run #167, GH Actions, full provenance) | 15 |
| 2 | Security / auth / TWOFA / peer-login | 10 | Strong; Round-5 fix candidate, artifact pending | 7 |
| 3 | Finance / idempotency | 12 | Spec exists (`99-finance-folio-surface`), targeted artifact pending | 6 |
| 4 | F9 frontend/backend ZERO reduction | 10 | Files exist (F9A/F9B), deploy run pending | 4 |
| 5 | F9C high-risk deep specs | 12 | 7 specs + partial targeted; fix-then-rerun artifact pending | 7 |
| 6 | Mobile F10 | 15 | Largest gap; F10A scaffold + locally runnable (28-test `--list`, `/login` render proof 0 console/0 PII), full matrix BLOCKED on 4 role secrets + GH Actions dispatch — see `docs/drill_reports/20260529_f10a_mobile_smoke.md` | 1 |
| 7 | CM / OTA deep workflows | 8 | Core webhooks covered; mapping/admin/reconciliation missing | 3 |
| 8 | Reports / AI / Revenue deep | 8 | Partial; builder + 50+ templates + AI deep routers missing | 2 |
| 9 | HR / hotel services / guest deep | 6 | Mixed partial/zero (laundry/transport/concierge/activities/kids-club ZERO) | 2 |
| 10 | Docs + automatic coverage gate | 4 | Docs good; no automated scoreboard gate yet | 2 |
| | **Total** | **100** | | **~49 earned (full-suite artifact landed via Run #167) / candidate-mapped to 84 on covered surface** |

> The weighted "earned" column reflects what is **artifact-proven
> today**. The headline scores below describe trajectory once evidence
> lands. The two numbers differ because most of the 100+ post-#143
> commits are `pending-artifact` — code shipped, proof not yet
> captured.

## Official score statement

| Score line | Value | Status |
|---|---|---|
| Run #143 coverage (2026-05-26) | 75–80/100 | HISTORICAL (oldest) — superseded by Run #159, #161, #162, then #167 |
| Run #159 coverage (2026-05-28) | 84/100 | HISTORICAL (older) — superseded by Run #161, #162, then #167 |
| Run #161 coverage (2026-05-29) | 84/100 | HISTORICAL — superseded by Run #162, then #167 |
| Run #162 coverage (2026-05-29) | 84/100 | HISTORICAL — superseded by Run #167 |
| **Run #167 official coverage (2026-05-30)** | **84/100** | **OFFICIAL — pointer locked here, web/backend full-suite artifact landed** |
| Artifact'd F10A + F9D extensions | 90–92/100 (projected) | requires further official artifacts |
| True /100 | requires F10B–F10G + backend deep router + UI mutation packs | future |

**84/100 is now OFFICIAL, not candidate**: the GitHub Actions full
stress suite Run #167 (702 test, commit
`0b99607fe3a64a7ada660d1f1bcb8607bd47f5dd`, verdict GO WITH WATCH,
external_calls=[], pilot_drift=0, cleanup#2 idempotent) landed with full
provenance, holding the official web/backend baseline pointer
(superseding Run #162). The score does NOT climb to 90+ yet because
mobile (F10) and the deep backend/UI packs remain uncovered. **/100 is
NOT achieved.** Mobile/F10 is NOT verified. The verdict is GO WITH WATCH
(not GO); 58 P2 + 48 REVIEW + 1 P3 + 44 SKIP remain open and are NOT
downgraded.

## Four closure sprints

### Sprint 1 — Evidence Sprint (highest priority)

No new features. Convert existing shipped code into official proof.

1. **Targeted 98C TWOFA** — `98C-twofa-totp-lifecycle.spec.js` test D
   verifying Round-5 timeout fix. Acceptance: 15× wrong TOTP → 401,
   throttle boundary → 429, `Retry-After` present, no `consumed_jtis`
   write amplification, external_calls=[], pilot_drift=0, P0/P1=0.
2. **F9C 7/7 targeted rerun** — 3 root-cause backend P1s now
   RESOLVED + targeted-verified (2026-06-04): maintenance 500
   (`test_maintenance_workorder_create.py` 3 passed), mobile staff
   notification 500 (live probe HTTP 200), cashier PIN brute-force
   no-429 (Task-51 always_on throttle, `test_cashier_handover_throttle.py`
   5 passed). Full-suite F9C promotion still needs operator full-stress
   dispatch (agent cannot dispatch). NOT a baseline move.
3. **F9D finance targeted** — `99-finance-folio-surface.spec.js`:
   charge/payment/refund/void-charge/void-payment/split/split-by-amount/
   city-ledger-transfer idempotency, closed-folio guard, cross-tenant
   folio deny, guest upsell IDOR.
4. **F10A mobile smoke** — separate matrix; not part of web baseline.
   Status 2026-05-29: scaffold now locally runnable (stale `.js`
   collision removed, Playwright wired, `--list`=28 tests, `/login`
   render proof = 0 console errors / 0 PII). Full 25-surface matrix
   BLOCKED on 4 `MOBILE_E2E_*` role accounts + GH Actions dispatch +
   deployed bundle URL. NOT verified; counts toward nothing. Drill:
   `docs/drill_reports/20260529_f10a_mobile_smoke.md`.
5. **GitHub Actions Full Stress Suite one-shot** — only after 1–4 are
   green. Requires re-applying dispatch workflow via GitHub web UI
   (OAuth token lacks `workflow` scope).

**Sprint 1 exit gate (baseline promotion)**: `failedTests=0 / P0=0 /
P1=0 / external_calls=[] / pilot_drift=0 / cleanup idempotent /
verdict ≥ GO WITH WATCH / official GH Actions artifact attached`. Any
single deviation blocks promotion. P2/REVIEW NOT downgraded.

### Sprint 2 — Mobile Coverage Sprint (largest gap, 15 pts)

- **F10B** — mobile auth lifecycle: login, 2FA prompt, refresh token
  rotation, logout, no plaintext token storage, biometric lock gate.
- **F10C** — guest critical path: mobile check-in, ID photo upload
  dry-run, signature pad, KVKK consent, cart upsell purchase, digital
  key issue/revoke, QR badge replay test, guest messages PII guard.
- **F10D** — frontdesk/cashier mobile: walk-in create, check-in,
  check-out, folio payment, folio close, cashier handover brute-force
  mobile path.
- **F10E** — housekeeping mobile: task list, task complete, damage
  report with photo.
- **F10F** — offline/resilience: offline banner, AsyncStorage replay
  queue, network throttle/error injection.
- **F10G** — full mobile suite CI baseline (iOS/Android or accepted
  mobile CI artifact). Acceptance: failedTests=0, P0=P1=0,
  external_calls=[], pilot_drift=0, verdict ≥ GO WITH WATCH.

### Sprint 3 — Backend Deep Router Sprint

- **Marketplace** (~192 endpoints): supplier/vendor lifecycle,
  product/service CRUD, order lifecycle, quote/request lifecycle,
  cross-tenant IDOR, B2B permission scope.
- **POS/F&B** (~228 endpoints): recipe/menu/modifier/station lifecycle,
  kitchen station assignment, inventory decrement/reversal,
  split/check/table transfer UI+API parity.
- **CM provider admin/sync/reconciliation**: HotelRunner + Exely admin
  endpoints, mapping sync, credential validation failure, webhook
  replay/idempotency, reconciliation mismatch.
- **Reports builder + 5 critical templates**: create/save/run, official
  guest list PDF, CSV/XLSX/PDF export PII mask, large pagination, cache
  invalidation, RBAC deny.
- **AI deep routers**: upsell insight lifecycle, forecasting, guest
  pattern detection, dynamic offers, prompt injection guard, vendor LLM
  external call = 0, AI output PII mask.
- **HR deep lifecycle** (469 endpoints): leave accrual/carry-over,
  performance review, recruitment, training, benefits, compensation,
  equipment, offboarding hard/soft blocks, cross-department RBAC, PII
  mask (TC/IBAN/payroll), HR audit log.
- **Hotel services package**: laundry, transport, concierge, activities,
  kids-club.
- **WhatsApp webhook** + xchange bus extended flows + KBS/Jandarma edge
  cases + push notification dry-run.

### Sprint 4 — Frontend Mutation Sprint

Smoke ≠ mutation. These need real action flows, not render-only.

- **Front Office**: walk-in UI submit, room-map status click/detail,
  wake-up-calls create/complete/cancel, lost-found create/return/archive,
  audit-checklist complete, arrival/departure list filters/actions,
  no-show convert/guard.
- **Reservations**: reservation-calendar drag-drop move, date conflict
  rejection, overbooking visual warning, calendar filter/search.
- **Housekeeping**: status change, OOO/OOS guard, dirty→clean→inspected
  transition UI.
- **Maintenance UI**: work-orders create/assign/close, assets
  create/update, recurring plans, sensor alert auto-created work order UI.
- **Finance UI**: pending-AR aging filters, city-ledger transfer,
  e-Fatura dry-run submit, konaklama vergisi dry-run submit.
- **Revenue/RMS**: dynamic-pricing override, autopilot enable/disable
  rule, revenue-engine dashboard integrity, displacement-analysis.
- **Channel Manager UI**: mapping-manager, room-mapping-wizard,
  unified-rate-manager bulk push dry-run, ari-push dashboard.
- **F&B/POS UI**: fnb-complete order lifecycle, beo-generator
  price/folio integration, kitchen-display real-time, pos-extensions
  config save.
- **Admin/System UI**: governance audit filters, admin-control-panel
  tabs, observability, data-pipeline, event-bus, system-health.

## Standing rules

- **Run #167 (`0b99607`) is the official pointer** as of 2026-05-30
  (supersedes Run #162, #161, #159, then Run #143). Next pointer
  movement requires a new GitHub Actions full-suite artifact that clears
  every gate.
- **No fake green.** Verbal "test passed" without an attached drill
  artifact is candidate evidence at best.
- **No artifact, no baseline.** Replit-environment runs (including Task
  #57's 723-test run) are candidate evidence only. Provenance (run URL
  + run number + commit SHA) is part of the artifact.
- **No ZERO route/module may remain pilot-accessible** without either
  `FEATURE_FLAG_OFF` or test coverage. A blind surface reachable in
  production is a pilot risk, not a coverage gap to defer.
- **/100 requires official artifacts, not docs only.** This scorecard
  tracks progress; it does not itself earn points.
- **Security surfaces require real artifact evidence** (2FA brute-force,
  peer-login throttle, cashier PIN, idempotency replay).
- **Do not claim GO if artifact says GO WITH WATCH.** Do not downgrade
  P2/REVIEW findings.

## Cross-references

- `docs/DAILY_CHANGE_REVIEW_20260528_POST_UPDATES.md` — post-#143 commit inventory by domain
- `docs/drill_reports/20260530_stress_full_stress_suite_GREEN_702test_run167.md` — **Run #167 official baseline drill (current)**; ai_pricing 500 fix sonrası FAIL 1→0
- `docs/drill_reports/20260530_ai_pricing_recommend_rates_500_fix.md` — Run #162→#167 tek değişiklik (ai_pricing recommend-rates deterministik 500 root-cause + fix)
- `docs/drill_reports/20260529_stress_full_stress_suite_GREEN_702test.md` — Run #162 baseline drill (historical); Run #161 provenance+metrics preserved in its comparison block (older historical)
- `docs/drill_reports/20260528_stress_full_stress_suite_GREEN_702test.md` — Run #159 baseline drill (older historical)
- `docs/drill_reports/20260526_stress_full_stress_suite_GREEN_84spec.md` — Run #143 baseline drill (oldest historical)
- `docs/drill_reports/20260528_twofa_round5_candidate_fix_pending_verification.md` — TWOFA Round-3/4/5 candidate detail
- `docs/STRESS_TEST_ROADMAP.md` — F8/F9/F10 roadmap (single source of truth)
- `replit.md` — F8 Stress Test Series section (pointer source of truth)

# F8Z.2 — POS KDS Print + F&B Inventory Stress (Drill Report)

**Date:** 2026-05-24 (spec authored) · **Verification run:** 2026-05-24
**Spec:** `frontend/e2e-stress/specs/98-pos-kds-inventory.spec.js`
**Module:** `pos_kds_inventory`
**Task:** #11 (F8Z.2) authored · #29 (verification)
**Commit (HEAD at verification):** `013d96e6` ("Task #11 (F8Z.2): POS KDS Print + F&B Inventory stress spec")
**Status:** TARGETED RUN EXECUTED — 1 P0 surfaced exactly as predicted (KDS `/complete` cross-tenant), full-suite green blocked on backend hardening follow-up

## Scope

Task #8 (F8Z v2 POS Deep Lifecycle) deliberately left two surfaces out of
its scope: the kitchen-ticket dispatch (KDS) router and the F&B inventory
deplete pipeline (recipe/BOM → `inventory_items` decrement +
`stock_consumption` audit). F8Z.2 covers both as a sibling stress spec,
following the F8AB / F8AC / F8Z v2 doctrine.

### Surfaces under test

- **KDS:**
  - `GET  /api/fnb/kitchen-display`
  - `POST /api/fnb/kitchen-order`
  - `PUT  /api/fnb/kitchen-order/{id}/status`
  - `POST /api/fnb/kitchen-order/{id}/complete`
  - `POST /api/pos/kds/update-order-status`
  - WebSocket broadcast tenant-isolation — verified indirectly via
    cross-tenant list / mutate probes (direct spy not feasible from spec).
- **Inventory atomic-movement:**
  - `GET  /api/accounting/inventory`
  - `POST /api/accounting/inventory`
  - `POST /api/accounting/inventory/movement`
  - `GET  /api/fnb/mobile/stock-consumption` (cross-tenant read probe)

## Test matrix (A–J)

| Step | Description | Severity rules |
|------|-------------|---------------|
| Setup | Probe KDS + inventory + recipe surfaces; capture pilot inventory baseline (`totalQty`, `itemCount`) | KDS/inventory blocked → P2; recipe absent → E/G skip + P2 |
| A | KDS catalog smoke (`GET /api/fnb/kitchen-display`) + pilot cross-tenant body-leak guard | leak → P0 hard-fail |
| B | Lifecycle: create → preparing → ready → served + terminal-state guard via re-`complete` | served→ready revert → P1 |
| C | **P0 cross-tenant KDS IDOR** — pilot bearer must NOT mutate stress ticket via status PUT, `/pos/kds/update-order-status`, or `/complete` | breach → P0 hard-fail (`toBeGreaterThanOrEqual(400)`) |
| D | Idempotency replay — kitchen-order POST does not yet honor `idempotency_key`; distinct ids = P1 finding (structural pass) | distinct → P1 |
| E | Inventory deplete happy — requires recipe/BOM seed | absent → SKIP + P2 |
| F | Negative-stock guard — overdraft → 409, qty unchanged | non-409 + negative qty → P0; non-409 + non-negative → P1 |
| G | Concurrent close race — 5 parallel out(1) on qty=3 → exactly 3 succeed, final = 0 | final<0 → P0; ok>3 → P1; contract mismatch → P2 |
| H | **P0 cross-tenant inventory mutate** — pilot bearer movement/adjustment on stress item must 4xx; stress qty unchanged | breach → P0 hard-fail |
| I | `stock-consumption` cross-tenant read — pilot body must NOT contain stress prefix | leak → P0 hard-fail |
| Z | Cleanup — `kitchen_orders` → cancelled, idempotent second pass; `inventory_items` orphan-scrubbed via `STRESS_COLLECTIONS` | second-pass non-idempotent → P1 |

## Mutlak kurallar (each test, try/finally)

- `assertNoExternalCallsPostBatch` per batch — no real provider HTTP fires
  (KDS surface does not publish Xchange events; close-order is folio-
  independent in this spec — `post_to_folio=false` + `booking_id=null`
  is never reached because E/G skip).
- `assertPilotDriftZero` per batch — pilot `bookings` count unchanged.
- `assertPilotInventoryDeltaZero` (new in this spec, inline helper) per
  batch — pilot `inventory_items` `quantity` sum AND `itemCount` unchanged.

## Backend touch list

- `backend/domains/admin/router/stress.py` — `STRESS_COLLECTIONS` extended
  with `stock_consumption`, `inventory_movements`, `recipes`, `menu_items`
  (forward-compat safety net; `kitchen_orders` + `inventory_items` already
  listed).
- No backend handler changes in this task. KDS handler `complete_kitchen_order`
  (`kitchen.py` L590-599) has a known tenant-filter gap on its
  `update_one` call (no `tenant_id` filter); the spec records a P0 finding
  with forensic context if the cross-tenant `/complete` mutation succeeds.
  Fix is deferred to a follow-up hardening task per Task #11 scope.

## Helper additions

Inline in the spec (no `stress-helpers.js` mutation needed):

- `inventorySnapshot(request, token)` — sums `inventory_items.quantity`
  for a tenant; returns `{ ok, totalQty, itemCount, http }` or
  `{ ok: false, ... }` on unreachable.
- `assertPilotInventoryDeltaZero(testInfo, module, request, pilotToken, baseline)`
  — emits `rec` per call + P0 finding if either `qtyDelta` or `countDelta`
  is non-zero (mirrors `assertPilotDriftZero` shape).

## Folio safety

This spec never closes a v2 POS order with `post_to_folio=true`. KDS rows
are pure operational queue rows (`kitchen_orders` collection) and do not
touch `folio_charges`. The inventory atomic-movement endpoint writes to
`stock_movements` only (no folio coupling). Combined with per-batch
`assertNoExternalCallsPostBatch`, this gives a structural guarantee that
no Xchange `POSTING_CHARGE` event fires during the F8Z.2 batch.

## Verification status

- **Spec compiles + targeted run (2026-05-24):** EXECUTED against
  `https://pms.syroce.com` (commit `013d96e6`).
  - Result: **3 passed / 1 failed / 7 skipped** (serial-describe halts on
    first failure, by design). Total wall-clock 1m12s including 500-row
    seed + cleanup. Setup gates ✅, seed ✅, teardown ✅
    (`deleted_total=8152 ms=10200`, idempotent second pass), pilot
    `bookings baseline=30 after=30 drift=0`.
  - Pass detail:
    - Setup — probe KDS + inventory + pilot inventory baseline ✅ (4.7s)
    - A — KDS catalog smoke ✅ (3.4s)
    - B — Kitchen-order lifecycle create→preparing→ready→served + terminal-state guard ✅ (5.9s)
  - **Fail detail (C):** P0 cross-tenant KDS IDOR. Pilot bearer
    `POST /api/fnb/kitchen-order/{stress_id}/complete` returned **200**
    (expected ≥400). Spec assertion at L357 fail-loudly as designed:
    > `pilot /complete on stress ticket must 4xx; got 200`
    Forensic trace:
    `test-results-stress/98-pos-kds-inventory-F8Z-2-9f64c-mutate-stress-kitchen-order-stress/trace.zip`.
    Root cause matches the prediction in the spec preamble and the
    "Backend touch list" above — `complete_kitchen_order` (`kitchen.py`
    L590-599) `update_one` call lacks a `tenant_id` filter; the matching
    `PUT /status` handler enforces tenant isolation correctly, which is
    why B passed while C broke.
  - D–Z were not executed because `test.describe.serial` halts the
    block on the first failure; their coverage is unblocked the moment
    the backend fix lands and is re-verified.
- **Full operational stress suite re-run:** **BLOCKED on hardening
  follow-up "Make kitchen ticket 'complete' button respect hotel
  boundaries"** (already filed; not duplicated by this verification
  task). Once that fix ships, re-run `yarn test:e2e:stress` to
  re-baseline (target: 73 → 74 spec, verdict ≥ GO WITH WATCH).
  - `playwright test --list` confirms the suite now enumerates **83
    spec files / 546 tests** with `98-pos-kds-inventory.spec.js`
    registered alongside its 73 siblings — the new spec is wired into
    the suite, not orphaned. (The roadmap "73 → 74" delta tracks
    "operational baseline" specs as historically counted; file count
    differs because module-block siblings, scaffolds, and the 99-full
    simulation are inventoried separately.)

## Findings ledger (verification run 2026-05-24)

| Severity | Title | Notes |
|---------|-------|-------|
| **P0** | Cross-tenant KDS `/complete` mutates foreign tenant's kitchen ticket | `POST /api/fnb/kitchen-order/{id}/complete` accepts pilot bearer against stress-tenant ticket id → 200 + ticket transitions to `completed` in stress tenant. Backend handler `backend/domains/pms/pos_fnb_router/kitchen.py::complete_kitchen_order` L590-599 `update_one({"id": …})` is missing `"tenant_id": current_user.tenant_id` filter. Sibling `PUT /status` handler enforces it correctly (B test passed against same ticket). Fix tracked by existing follow-up task **"Make kitchen ticket 'complete' button respect hotel boundaries"** — do not file a duplicate. |
| P2 (informational) | D–Z coverage gated on C | Serial-describe halts on first failure; D (idempotency replay), E–G (inventory deplete / negative-stock / concurrent race), H (cross-tenant inventory mutate), I (`stock_consumption` cross-tenant read), Z (cleanup idempotency) did not execute. No regression evidence; will unblock automatically once C passes. Recipe-seed gap (E/G) still applies per spec doctrine. |

## Architect verdict

**CONDITIONAL GO** — Spec authored, wired into the suite, and run end-to-end
against a live backend. The targeted run produced the exact outcome the
spec was written to surface: one real P0 (cross-tenant `/complete`
mutation) that maps to an already-filed hardening follow-up. No
regressions outside the predicted finding; setup / teardown / pilot
drift / external-calls invariants all clean. Full-suite re-baseline
(73 → 74) is a one-line outcome once the backend fix lands and C–Z run
green; this verification task is complete on the agreed acceptance path
"if P0/P1 findings surface, file them and link the hardening follow-ups".

## References

- Task spec: `.local/tasks/task-11.md`
- Sister specs:
  - `frontend/e2e-stress/specs/98-pos-deep-lifecycle.spec.js` (F8Z v2, Task #8)
  - `frontend/e2e-stress/specs/98-spa-wellness-operational.spec.js` (F8AB)
  - `frontend/e2e-stress/specs/98-golf-operational.spec.js` (F8AC)
- Backend canonical surfaces:
  - `backend/domains/pms/pos_fnb_router/kitchen.py` (L527-621)
  - `backend/routers/finance/accounting.py` (L373-489)
  - `backend/domains/pms/hotel_inventory_system.py` (doctrine note)
- Roadmap: `docs/STRESS_TEST_ROADMAP.md` "Latest verified baseline"

# F8Z.2 — POS KDS Print + F&B Inventory Stress (Drill Report)

**Date:** 2026-05-24
**Spec:** `frontend/e2e-stress/specs/98-pos-kds-inventory.spec.js`
**Module:** `pos_kds_inventory`
**Task:** #11 (F8Z.2)
**Status:** SPEC WRITTEN — targeted+full-suite verification pending republish

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

- **Spec compiles + targeted run:** PENDING republish.
- **Full operational stress suite re-run:** PENDING republish.
  - Target baseline: 73 → **74 spec**.
  - Acceptance: 0 fail, P0=P1=0, `external_calls=[]`, `pilot_drift=0`,
    pilot inventory `qty_delta=0` AND `count_delta=0`, verdict
    ≥ GO WITH WATCH.

## Findings ledger (initial run)

_To be populated after the first targeted run._

| Severity | Title | Notes |
|---------|-------|-------|
| (pending) | | |

## Architect verdict

_To be added after full-suite verification._

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

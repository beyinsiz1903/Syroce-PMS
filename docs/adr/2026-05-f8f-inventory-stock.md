# ADR — F8F Inventory: Negative Stock Guard

**Date:** 2026-05-20
**Status:** Accepted (verified 2026-05-20 by Task #213)
**Task:** #209 (fix), #213 (verification)

## Context

F8F stress spec `frontend/e2e-stress/specs/70-inventory-stock.spec.js § C`
detected a P0 financial-integrity bug in
`POST /api/accounting/inventory/movement`:

- start `quantity = 5`
- `movement_type = out`, `quantity = 50`
- result: `200 OK` and `item.quantity = -45`

Negative stock invalidates valuation (`quantity * unit_cost`), low-stock
aggregation, reorder logic, and downstream accounting reports.

The legacy implementation issued an unconditional `$inc: -qty` after
inserting the movement record, so:

1. Stock could go arbitrarily negative.
2. Concurrent `out` calls had no race protection — read-then-write
   pattern.
3. Failed updates left orphan `stock_movements` rows.

## Decision

Replace the legacy implementation in `backend/routers/finance/accounting.py`
(`create_stock_movement` — the LIVE handler, mounted first via
`bootstrap/router_registry.py:56` so it wins FastAPI's first-match
routing) with a fail-closed guard. The same guard is mirrored in
`backend/domains/accounting/endpoints.py` (re-exported by
`domains/accounting/router.py` but shadowed by the finance one at
runtime) as defense in depth, so the route remains safe if the mount
order ever changes:

1. **Input validation (422)** — `movement_type` must be one of
   `in / out / adjustment`; `quantity` must be a number (NaN
   rejected; non-finite values such as `inf` rely on FastAPI/Pydantic
   coercion); `in / out` require `quantity > 0`; `adjustment`
   requires `quantity >= 0`.
2. **Tenant scope (404)** — `find_one({id, tenant_id})` rejects
   cross-tenant IDOR up front.
3. **Atomic conditional update (409)** — for `out` the filter is
   `{id, tenant_id, quantity: {$gte: requested_qty}}`. If
   `modified_count == 0` the call returns `409 Insufficient stock`
   with `requested` + `available` numbers. This is race-free at the
   MongoDB document level (no transaction needed).
4. **Movement record persisted after success** — `stock_movements`
   insert happens only after the conditional update wins, so rejected
   calls leave zero side-effects.

`in` and `adjustment` keep their existing semantics (tenant-scoped
`$inc` / `$set`) but inherit the validation gate.

Note: `backend/routers/finance/accounting.py` is the LIVE handler
(first-match via `bootstrap/router_registry.py:56`); the shadow at
`backend/domains/accounting/endpoints.py` is mounted later
(`router_registry.py:130`) and is never reached for this route, but
carries the identical guard so any future mount-order change stays
safe.

## Contract

| Case | Request | Response |
|------|---------|----------|
| Insufficient stock | `out`, qty > current | `409 Insufficient stock: requested=X, available=Y` |
| Exact boundary | `out`, qty == current | `200` + qty = 0 |
| Zero / negative qty | any | `422` |
| Unknown `movement_type` | any | `422` |
| Cross-tenant or missing id | any | `404 Inventory item not found` |
| Concurrent out (sum > stock) | two parallel `out` | exactly one `200`, one `409`; final qty ≥ 0 |

## Tests

- `backend/tests/test_inventory_negative_stock_guard.py` — 11 cases
  covering sufficient/insufficient/boundary/zero/negative/unknown-type
  /unknown-id/in/adjustment-zero/adjustment-negative + the parallel-out
  race scenario.
- F8F spec 70 § C now asserts hard (no clamp branch needed for this
  backend); § D and § E run normally instead of skipping after § C
  early-returns.

## Operational

- Existing rows with `quantity < 0` are clamped to 0 by
  `backend/scripts/scrub_negative_inventory.py`. Pilot tenant is
  excluded by environment guard (`E2E_PILOT_TENANT_ID` /
  `PILOT_TENANT_ID`). Dry-run is default; `--apply` writes one
  synthetic `stock_movements` adjustment row per clamp for audit.

## Verification (Task #213, 2026-05-20)

Re-verified post-merge that the guard actually shipped after the
`20260520_stress_full_stress_suite.md` CI run still listed the P0:

- `git log` confirms commit `37245036` "Task #209 — F8F inventory
  negative-stock guard (P0)" landed on main.
- Both handlers carry the identical guard:
  `backend/routers/finance/accounting.py:414` (LIVE — first-match,
  mounted at `bootstrap/router_registry.py:56` via `routers.finance`)
  and `backend/domains/accounting/endpoints.py:277` (shadowed
  defense-in-depth, mounted at `router_registry.py:130`).
- `backend/tests/test_inventory_negative_stock_guard.py` — **15/15
  PASS** against the running Backend API (live HTTP integration):
  sufficient / insufficient / exact-boundary / zero / negative /
  unknown-type / in / adjustment-zero / adjustment-negative /
  unknown-id / create-negative-rejected / create-zero-allowed /
  create-positive-allowed / shadow-create-negative-rejected /
  parallel-out race (exactly one 200, one 409, final qty ≥ 0).
- Drill report: `docs/drill_reports/20260520_stress_f8f_inventory_p0_verification.md`.

Conclusion: the original `20260520_stress_full_stress_suite.md` CI run
(timestamp `07:09:34Z`) executed against a stale checkout that
pre-dated commit `37245036`'s effective propagation on the runner.
The fix is genuinely on main; the next full stress suite run will
clear F8F § C from the P0 list and § D / § E will execute instead of
early-returning.

## Out of scope

- UI warnings / toasts (API surface only).
- Telemetry / Prometheus counters for rejected out-movements.
- Purchasing-module reorder-level changes (F8F spec #71).
- Pilot tenant scrubbing.

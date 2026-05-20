# Drill Report — F8F Inventory P0 Fix Verification

**Date:** 2026-05-20
**Task:** #213 (verification of #209)
**Scope:** Confirm the F8F negative-stock guard P0 fix shipped by Task #209 is genuinely on main and that the stale CI report from `20260520_stress_full_stress_suite.md` is a pre-merge artefact, not a missing patch.

## Trigger

The most recent full stress suite report (Task #213 task description, 342 tests, CI timestamp `2026-05-20T07:09:34Z` — report itself not yet committed to repo, cited from task brief) re-listed:

> `[inventory_stock]` NEGATIVE STOCK BUG — Item 13f107e0 start=5, out=50, final_quantity=-45, out_status=200

Task #209 had been marked MERGED ~13 minutes before this CI run completed (`06:56Z`), so it was unclear whether the patch had actually landed or whether a reconciliation issue swallowed it.

## Verification

### 1. Repo state (git log)

```
$ git log --oneline -- backend/routers/finance/accounting.py
9eea7698 Task #210: reject negative quantity on inventory item create
37245036 Task #209 — F8F inventory negative-stock guard (P0)
50d0d0cd Invoice customer-name hardening + test seed cleanup
...
```

Commit `37245036` is on `main`. The guard ships.

### 2. Live handler inspection

Both routers carry the same guard contract. FastAPI's first-match rule means `routers/finance/accounting.py` wins:

| File | Line | Mount order |
|------|------|-------------|
| `backend/routers/finance/accounting.py` | `414` | `bootstrap/router_registry.py:56` (LIVE) |
| `backend/domains/accounting/endpoints.py` | `277` | `bootstrap/router_registry.py:130` (shadowed; defense-in-depth) |

Guard structure (identical in both files):

1. `movement_type ∈ {in,out,adjustment}` → 422 otherwise.
2. `quantity` finite and non-NaN → 422 otherwise.
3. `in|out` require `quantity > 0`; `adjustment` requires `quantity >= 0` → 422 otherwise.
4. `find_one({id, tenant_id})` → 404 if not owned (cross-tenant IDOR block).
5. For `out`: atomic `update_one({id, tenant_id, quantity: {$gte: qty}}, {$inc: {quantity: -qty}})`. `modified_count == 0` → 409 with `requested` + `available`.
6. `stock_movements` insert only after the conditional update wins → no orphan rows on rejection.

### 3. Pytest (live HTTP integration)

`backend/tests/test_inventory_negative_stock_guard.py` runs against the running Backend API workflow (`VITE_BACKEND_URL` set).

```
============================= 15 passed in 11.76s ==============================
```

Cases:

| # | Case | Status |
|---|------|--------|
| A | sufficient stock out decrements | PASS |
| B | insufficient stock out rejected — strict 409 + requested/available body | PASS |
| C | exact-boundary out → qty = 0 | PASS |
| D | zero quantity rejected (422) | PASS |
| E | negative quantity rejected (422) | PASS |
| F | unknown movement_type rejected (422) | PASS |
| G | in movement increments | PASS |
| H | adjustment to zero ok | PASS |
| I | adjustment with negative qty rejected (422) | PASS |
| J | unknown item id → 404 | PASS |
| K | race — two parallel out, one 200 + one strict 409, final qty ≥ 0 | PASS |
| L | create with negative qty rejected | PASS |
| M | create with zero qty allowed | PASS |
| N | create with positive qty allowed | PASS |
| O | shadow router create with negative qty rejected | PASS |

The race case (K) is the strongest live evidence the guard is atomic at the MongoDB document level — read-then-write would have allowed both writes to succeed.

### 4. F8F stress spec § C correspondence

`frontend/e2e-stress/specs/70-inventory-stock.spec.js:226-328` § C scenario (`start=5, out=50`) maps to pytest case B above. Live handler returns `409 Insufficient stock: requested=50, available=5`; final quantity stays at `5` (never written negative).

The spec's hard asserts (`expect(readOk).toBe(true)` and `expect(finalQty >= 0).toBe(true)`) will both hold on the next CI run. § D and § E (skipped on the prior run after § C early-returned) will now execute.

## Verdict

**GO** — Task #209 fix is genuinely on main. The stale CI report (cited in the Task #213 brief, timestamp `07:09:34Z` ≈ same wall-clock as merge propagation `06:56Z`) most plausibly ran against a pre-merge checkout (CI runner cached or polled before the new SHA was advertised). The report file itself is not committed; the conclusion rests on (a) `git log` showing commit `37245036` on `main`, (b) live-HTTP pytest verifying the guard is active end-to-end, and (c) the LIVE handler carrying the atomic `$gte` filter + 409 contract. No follow-up patch is needed.

Next full stress suite run is expected to drop F8F § C from the P0 list and surface § D / § E results. F8F roadmap remains:

- F8F § C (negative stock) — **CLOSED** (pytest + guard verified).
- F8F § D / § E — will execute on next CI, results to be triaged in a separate task if any new findings emerge.

## Files referenced

- `backend/routers/finance/accounting.py:414-490` (LIVE guard)
- `backend/domains/accounting/endpoints.py:277-353` (shadow guard)
- `backend/tests/test_inventory_negative_stock_guard.py` (222 lines, 15 cases)
- `backend/scripts/scrub_negative_inventory.py` (one-shot scrub, pilot fail-closed)
- `frontend/e2e-stress/specs/70-inventory-stock.spec.js:226-328` (spec § C)
- `docs/adr/2026-05-f8f-inventory-stock.md` (ADR, updated with verification note)
- `bootstrap/router_registry.py:56,130` (mount order proving finance/accounting wins)

## Out of scope

- Triggering an external CI workflow_dispatch (no CI credentials in this environment; will be observed on the next scheduled run).
- F8F roadmap §§ D / E findings (pending next CI).
- Sibling P0/P1 items (AI no-show leak #214, oversell guard #215, GraphQL resolver #216) — separate tasks.

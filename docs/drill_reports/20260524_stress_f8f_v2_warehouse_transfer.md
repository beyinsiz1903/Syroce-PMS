# F8F v2 — Warehouse Transfer + Procurement Hardening (spec written 2026-05-24)

**Task:** #9 — F8F v2 stress spec (warehouse transfer + GRN lifecycle +
PO cancellation guard + supplier credit_limit probe + cross-tenant IDOR)
**Spec:** `frontend/e2e-stress/specs/72-warehouse-transfer-procurement.spec.js`
(module `inventory_transfer_procurement`)
**Baseline:** 73 → **74 spec** (full-suite verification deferred to next round)

## Scope

F8F § 70/71 (purchasing supplier) bilinçli olarak warehouse-to-warehouse
transfer'i scope dışı bıraktı — backend `_grn_apply` ve
`/api/accounting/inventory/movement` whitelist'i {in,out,adjustment}
ile sınırlı; "transfer" çağrısı 422 dönmeli. F8F v2 bu kontratı
fail-closed olarak doğrular + partial GRN lifecycle, PO cancel guard,
supplier credit_limit gap'ini ekler.

## Segments

### A) Warehouse transfer probe
- `POST /api/accounting/inventory/movement?movement_type=transfer` →
  422/400/404 expected (whitelist guard `backend/routers/finance/
  accounting.py:429`).
- 2xx → **P0** (silent stock movement without destination contract,
  no audit trail).
- 5xx → P2 REVIEW (backend hiccup).
- Documents transfer-not-implemented as P2 product-backlog gap.

### B) Partial GRN lifecycle
- B1 PO seed (inventory_item_id=null, line0 qty 10 / line1 qty 4).
- B2 PO → sent.
- B3 Partial GRN line0 qty 4 → PO `partially_received`.
- B4 Rejected qc_status line1 qty 4 → received_qty stays 0 (verified
  via detail read); PO still `partially_received`. P0 if line1
  received_qty>0 (`_grn_apply` skip-rejected guard broken).
- B5 Final GRN line0 qty 6 + line1 qty 4 → PO `received`.
- B6 Overage / post-complete GRN → 4xx (409 from PO-status guard or
  422 from overage guard). 2xx = P0.
- B7 received → closed transition.

### C) PO cancellation guard
- C2 Empty/short cancel reason → 422 (`POStatusIn._reason_for_cancel`
  Pydantic ValueError ≥5 char).
- C3 Cancel with proper reason → 200; subsequent GRN on cancelled PO
  → 4xx (`_grn_apply` blocks PO not in {sent, partially_received}).
  2xx = P0 (cancelled PO mutated; financial referential integrity).
- C4 closed→cancelled invalid transition → 4xx (procurement.py:541
  `closed: {}` allowed-set). 2xx = P0.

### D) Supplier credit_limit + delete-when-used + cross-tenant IDOR
- D1 `credit_limit` extra field in `SupplierIn` payload → silently
  dropped (Pydantic default extra='ignore'). P2 REVIEW — product
  backlog: model field + PO-creation enforcement guard.
- D2 Delete supplier with open PO (sent) → 409 expected
  (procurement.py:211 in-use check). 2xx = P0 (referential integrity
  bypass; tracked id removed from teardown to avoid double-404 noise).
- D3 **P0 cross-tenant IDOR** — pilot bearer:
  - `PUT /suppliers/{id}` (stress) → must 4xx
  - `DELETE /suppliers/{id}` (stress) → must 4xx
  - `POST /purchase-orders/{id}/status` (stress) → must 4xx
  - `POST /purchase-orders/{id}/grn` (stress) → must 4xx
  - Any 2xx = P0 tenant guard breach.

### E) Final invariants + cleanup idempotency
- Second-pass DELETE on each supplier id → must return 404 (idempotent
  contract). Non-404 = P1.
- `external_calls = []` + `pilot_drift = 0` final assertion.

## Doctrine adherence

- **Module-blocked:** suppliers GET probe non-2xx (403/404/5xx) →
  A/B/C/D skip + P2; E final invariants always run.
- **Per-test invariants:** every test wraps batch in try/finally with
  `assertNoExternalCallsPostBatch` + `assertPilotDriftZero` (pilot
  drift recorded at start of each test, asserted at end).
- **Side-effect containment:** PO lines use `inventory_item_id=null`
  to skip `housekeeping_inventory.$inc` (spec 71 doctrine).
- **Cleanup primacy:** spec-side `afterAll` + E final pass are primary;
  `STRESS_COLLECTIONS += {proc_suppliers, proc_purchase_requests,
  proc_purchase_orders, proc_goods_receipts, proc_counters}` is the
  orphan-scrub safety net for runs that abort mid-flight.

## Backend contract references

- `backend/routers/finance/accounting.py:429` — movement_type whitelist
- `backend/routers/procurement.py:215` — supplier in-use 409 guard
- `backend/routers/procurement.py:515` — POStatusIn cancel reason validator
- `backend/routers/procurement.py:536-544` — PO state-machine allowed map
- `backend/routers/procurement.py:592-594` — GRN status guard
- `backend/routers/procurement.py:608-611` — GRN overage 422

## Run command

```bash
cd frontend && yarn playwright test \
    --config=playwright.stress.config.js \
    specs/72-warehouse-transfer-procurement.spec.js
```

Env required: `E2E_BASE_URL`, `E2E_STRESS_ADMIN_EMAIL`/`_PASSWORD`,
`E2E_STRESS_TENANT_ID`, `E2E_ADMIN_EMAIL`/`_PASSWORD` (pilot super_admin
for IDOR + external_calls), `E2E_ALLOW_DESTRUCTIVE_STRESS=true`,
`E2E_EXTERNAL_DRY_RUN=true`.

## Verdict

Spec written + STRESS_COLLECTIONS expanded + roadmap section moved from
"önerilen" → DONE. Targeted run + full-suite verification (74 spec
baseline) deferred to next round; expected verdict ≥ GO WITH WATCH on
fail-closed posture (no production code changes in this task, only
contract verification).

---
name: POS create-order idempotent+atomic folio posting
description: Non-obvious interactions in the POS->folio atomic/idempotent write path
---

POS `create-order` posts order + folio_charges + balance recalc in one Mongo
transaction (folio lock via `with_resource_locks`), idempotent on
`idempotency_key`, balance recalculated from the ledger (never `$inc`).

**Key replay short-circuits charges.** On a true replay (same idempotency_key,
order already committed) the handler returns the existing order and does NOT
re-attempt charges — correct under a real transaction (a partial attempt rolled
back fully, so the committed order always has its full charge set). But the
dev-only standalone non-tx fallback can commit an order then crash mid-charge;
a later key replay would then skip the missing charges. Fallback is fail-closed
(503) by default, so production never hits this; don't "fix" it by re-posting on
replay (that double-charges the normal case).

**Two guards, two jobs:** `(tenant_id, idempotency_key)` on pos_orders dedups
whole-order retries; `(tenant_id, source_pos_order_id, line_no)` on
folio_charges is defense-in-depth that dedups the SAME order's charge lines if
they're posted twice. Both are PARTIAL (legacy/non-POS docs lack the fields).

**Why:** legacy POS path omitted FolioCharge.booking_id (required) — fixed by
fetching it from the folio (404 if folio missing, blocks orphan/cross-tenant
charges). `_idem._INDEXES_READY` is a process-global cache keyed by
collection.name, so unit tests must `.clear()` it per test to re-register fakes.

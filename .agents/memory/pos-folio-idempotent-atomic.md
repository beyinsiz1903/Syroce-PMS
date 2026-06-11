---
name: POS create-order idempotent+atomic folio posting
description: Non-obvious interactions in the POS->folio atomic/idempotent write path
---

**Outbox/Compensation supersedes synchronous folio posting.** POS `create-order`
NO LONGER mutates the folio in the hot path. It writes the idempotent
`pos_orders` record + a `pos.charge.posted.v1` IC outbox event in ONE
transaction (`with_resource_locks`, `resources=[]` — no folio lock, intent only).
`core.pos_folio_consumer` applies the real folio_charge inserts + balance recalc
asynchronously, idempotently, guaranteed-at-least-once via the outbox worker.
Void/refund publishes `pos.charge.reversed.v1`; the consumer flips matching
charges `voided=True` (idempotent: `voided:{$ne:True}` filter) and recalcs.
Response carries `charge_status: 'queued'|'none'`.
**Why:** removes folio-lock contention from the POS hot path and makes the
order+intent crash-atomic without a synchronous cross-document write.
**How to apply:** the IC events route through `outbox_dispatcher` BEFORE the CM
mapping (`IC_OUTBOX_EVENT_TYPES` early-return → `handle_ic_pos_event`); they MUST
never reach the channel manager (`external_calls=[]`).

**Apply-time late-charge/AR guard.** The consumer re-checks folio status at apply
time; a non-open folio is NOT written silently — the charge is routed to
`pos_late_charges` (upsert, operator-visible). Checkout/close drains pending POS
charge events inline (`drain_pending_pos_charges`) BEFORE closing so queued
charges land on the still-open folio and count in the outstanding-balance check.

**Single balance strategy, never `$inc`.** Consumer `_recalc_folio_balance` =
sum(folio_charges `$ifNull[total,amount]` where voided False) − sum(payments
amount where voided False), same formula as `pos_core._folio_balance_in_session`.

**Two guards, two jobs:** `(tenant_id, idempotency_key)` on pos_orders dedups
whole-order retries (replay returns existing order, the IC event is NOT
re-enqueued); `(tenant_id, source_pos_order_id, line_no)` on folio_charges dedups
the consumer re-applying the SAME order's lines on event re-delivery
(DuplicateKey skip). Both are PARTIAL (legacy/non-POS docs lack the fields), and
both are fail-closed: a failed index-ensure → 503 (hot path) / retryable apply
result (consumer), never a non-deduped write.

**Testing the async contract is NOT assertion-loosening.** Tests that previously
asserted synchronous `folio_charges` inserts must now assert (a) one IC outbox
event enqueued + `charge_status=='queued'`, and (b) balance/dedup by DRIVING the
real consumer over the enqueued events (monkeypatch `cons.get_system_db` to the
same in-memory fake). v2 service close/void now run inside a transaction, so
fake DBs need a `.client` (start_session→session.with_transaction) AND every
collection op must accept `session=None`.

**Multiple endpoints write pos_orders idempotently.** The mobile quick-order
endpoint reuses the SAME `pos_orders` idempotency index — when calling the
shared `idempotent_insert` helper from a second writer, pass
`index_name="ux_pos_orders_tenant_idemp"` so its lazy `ensure_idem_index` does
not try to create an equivalent index under a different default name (would be
an IndexOptionsConflict). The UI side must generate the key ONCE per genuine
attempt and reuse it across retries (clear only on success), or the gate is
moot. `idempotent_insert` propagates index-ensure failures (fail-closed); the
caller must catch and surface 503.

**Why:** legacy POS path omitted FolioCharge.booking_id (required) — fixed by
fetching it from the folio (404 if folio missing, blocks orphan/cross-tenant
charges). `_idem._INDEXES_READY` is a process-global cache keyed by
collection.name, so unit tests must `.clear()` it per test to re-register fakes.

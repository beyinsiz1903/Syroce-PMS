# Reservation prepayment acceptance

The `record-deposit` / `refund-deposit` routes record an external prepayment
and its refund against a reservation folio. They do not charge/refund a bank
card, and are not the refundable security-fund liability workflow.

## API contract

- Both request bodies require a caller-generated UUID `request_id`. Preserve
  the exact UUID and body after response loss. Repeating the same intent returns
  its durable receipt; changing its booking/action/amount/content returns 409.
- Only `cash`, `card` (external POS evidence), and `bank_transfer` are accepted.
  Online gateway, comp, city ledger and wallet are not interchangeable methods.
- Positive, finite, exact two-decimal amounts and a known source/folio currency
  are required. This flow supports TRY/USD/EUR/GBP/CHF without implicit FX.
- `record-deposit` accepts optional `folio_id`. Multiple open windows require
  an explicit selection. A target belonging to another booking/tenant is denied.
- Refunds stay on their original folio, even if closed. A missing/wrong source
  folio or corrupt historical deposit/refund amount blocks the operation. A
  legacy row without `folio_id` may reuse its sole open booking window (or
  create one if none exists), but cannot choose arbitrarily among split folios.

Deposit/refund, signed payment, booking counter, durable receipt and immutable
actor/source evidence commit together under a reservation financial transaction.
Audit failure rolls everything back. Mongo transactions are required; there is
no standalone fallback. Post-commit cache/activity/webhook problems must not
turn a committed receipt into an ambiguous failed payment.

The two browser entry points persist the submitted body in session storage
before dispatch. Timeouts, 409, and 5xx retain it across retry/reload. A changed
form cannot silently mint a second uncertain payment. Definite pre-write
validation/authentication failures release the draft. Successful submission
clears it. Browser storage failure prevents dispatch.
An explicit recovery notice replays the stored body even after a reload,
auto-created folio, checkout or completed refund; current form values do not
replace the original target/UUID. Projection refresh is retried on replay.

## Report semantics

Flash Excel marks unposted ADR/RevPAR as pending, not measured zero. Accrued
ratios, when available, are separately labelled and do not become posted revenue.

Operational GL valuation may not reverse a nonzero original journal solely
because the current source history is empty. Missing historical sources require
manual source reconciliation, not a zero-source correction.

## Verification boundary

Real local replica-set tests cover durable replay, changed payloads, concurrent
receipt/refund, over-refund, rollback on audit/receipt failure, terminal bookings,
split folios, tenant separation, damaged legacy money, source currencies and
post-commit response safety. No production payment or historical rewrite is
performed by these tests. Deployment and a Demo-only live replay acceptance are
separate steps; old unkeyed callers must update before retrying.

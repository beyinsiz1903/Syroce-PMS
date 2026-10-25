# Source-backed folio settlement acceptance

Online acquiring is explicitly out of this change. No PSP/terminal call is
made, no credentials are installed, and a recorded cheque clearance is an
operator's evidence of an already-completed bank transaction, not a bank order.

## Operator screens

Reservation → Folio/Payment → **Kurumsal ödeme / ikram kontrolleri** →
**Hediye kartı, cüzdan, sadakat, barter ve çek**.

The panel provides source/limit registration, application to an explicitly
selected open folio, source history, reconciliation and linked full reversal.
Amounts use integer minor units; decimal comma is supported in the UI.
Uncertain responses freeze the request and retry the same UUID/payload.

| Method | Required source | At application |
| --- | --- | --- |
| Gift card / wallet | Existing sealed GL liability credit in the same currency; unallocated credit is checked across all instruments | Debit the remaining historical carrying value, credit guest AR at the explicit business-day rate; any difference needs a separate gain/loss account. No new cash collection. |
| Loyalty | Existing PMS `loyalty_members` member, positive points and an explicit monetary value per point; expense account and document limit | Atomically consume actual member points, debit the chosen expense account and credit guest AR. No points are issued. POS-specific points remain a separate ledger. |
| Barter | Explicit contract reference, amount ceiling and active non-guest asset account | Debit barter receivable, credit guest AR; no cash or sales discount is invented. This is allocation of documented contract value, not automatic vendor tax invoicing. |
| Write-off | Explicit reason/document, ceiling and active expense account | Debit the chosen expense and credit guest AR. Revenue/tax source lines are not rewritten and cash collection is zero. |
| Cheque | TRY-only cheque reference, maturity date, ceiling and the mapped bank account | Registration stays pending and changes neither folio nor GL. Full clearance on/after maturity requires bank evidence; it creates one bank collection, cashier movement and sealed journal, atomically. |

Gift/wallet source funding must be recorded through the existing accounting
voucher lifecycle first. This panel does not take payment to sell/load a gift
card. It allocates an already-booked liability; a random reference cannot create
money. Instruments are nominative when a guest profile is present, otherwise
bound to their originating booking; bearer-code transfer is not implemented.

Issue requires existing finance/direct-bill and rate-override permissions.
Apply requires payment permission; reversal requires finance plus void-payment
permission. No new maker-checker rule is imposed. Existing tenant GL accounts
and account types are required; no default expense/liability or FX rate is
guessed. Completed bookings and invoiced/closed folios require their separate
financial/document correction lifecycle first. Reversals are whole-operation,
append-only linked entries, not arbitrary partial cash refunds. A cheque return
requires external bank evidence and is not made spendable again.

## Integrity and reporting

- A stable tenant primary-key lock serializes credit allocation, even before
  legacy booking lock indexes exist. Source/operation/reversal unique indexes
  are prepared outside transactions. No standalone fallback exists.
- Points, liability consumption, payment offset, folio balance, GL sequence,
  sealed journal, cashier movement where applicable, durable replay receipt and
  central audit commit or roll back together.
- Native currency positions and carrying/current rates are retained in GL
  lines/manifests. A partial carrying allocation that cannot be represented to
  the accepted rate precision fails closed rather than losing a cent.
- Gift/wallet/loyalty/barter/write-off are excluded from cash collection and
  revenue adjustments. They reduce posted folio debt, not original room price.
  A separate reservation summary card identifies these non-cash settlements.
- Cleared cheques and their reversals are verified against their sealed direct
  posting and excluded from night-audit reposting. Their cash collection still
  appears in payment/cashier reports. Operational reconciliation includes the
  independent instrument-source check; altered payment/GL links fail visibly.
- Generic void/refund paths cannot modify linked instrument payments. The
  dedicated full-reversal workflow restores credit/points and preserves the
  original payment and journal. Failed refreshes never turn a committed write
  into a new request; reload is required before starting another operation.

Real-local-replica acceptance lives in `tests/test_settlement_instruments.py`:
all six methods, repeat/reversal binding, shared-credit concurrency, rollback
after cash/audit/period failure, invoice/owner/currency guards, source tampering,
and explicit FX gains/losses in USD/EUR/GBP/CHF. UI and mobile classification
tests cover minor units, ambiguous responses, read-only controls and non-cash
labels. Passing these tests is not a claim of PSP or real fiscal acceptance.

## Separate approved Demo audit restoration

`scripts/restore_demo_audit_attribution.py` is an offline recovery tool, not an
HTTP endpoint or general audit-update permission. It is hard-bound to Demo
100001, the paused TEST connections, business day 24 October and the already
sealed 69-record metadata incident. Dry run is default. Apply additionally
requires its exact reviewed plan hash, confirmation, actor and human approval.

Only two fields can become null, and only when that reproduces the **existing**
record hash. Raw observations and their digests are preserved in
`audit_restoration_preimages`; the restored fields, receipt and a new audit
attestation commit together. Existing record hashes, links, sequences, financial
content and timestamps are not changed. Original attribution beyond the sealed
null values is unknown; late observed values remain evidence, not retroactively
certified client attribution. Runtime append-only guards remain unchanged.

On 25 October the user explicitly approved this fixed restoration. Its live
dry run matched all 69 reviewed failures; after application the independent API
verification found zero breaks. This restores hash-defined audit content, not
historical evidence for the separately labelled synthetic FX/tax/AR sources.

# Nilvera → General Ledger automation

Nilvera document transport and General Ledger posting are deliberately
separated. The GL automation layer never calls Nilvera and never submits a
document to GİB. It reacts only to invoice snapshots/statuses already persisted
inside the tenant boundary.

## Tenant modes

- `disabled`: no candidate is created.
- `review` (default): a durable queue item is created and an accountant posts
  it after reviewing the hotel-specific account mapping.
- `automatic`: the same queue item is claimed and posted automatically. A
  closed period, missing account, unsupported tax mapping, or inconsistent
  total leaves a visible `blocked` item instead of guessing.

Incoming purchase invoices use explicit purchase/asset, deductible VAT,
vendor-payable, additional-tax, and deduction/withholding mappings. Tax codes
may be mapped individually. Foreign-currency incoming invoices are converted
using the UBL pricing/payment exchange rate and preserve the source currency,
foreign amount, and rate on every journal line.

Outgoing sales invoices are posted only after the Nilvera status is accepted.
Revenue, receivable, discount, VAT-rate, and accommodation-tax mappings are
supported. A later cancellation creates one exact debit/credit reversal; status
poll retries cannot create a second reversal.

## Operator surfaces

- Hotel finance/admin users manage mappings and the review queue under
  **General Ledger → Accounting Integrations**.
- Superadmins may provision the same mappings for a target hotel from the hotel
  setup modal. This writes local tenant settings only.
- Blocked queue items retain a sanitized error type/detail and can be retried
  after correcting the account plan, fiscal period, or mapping.

## Related subledgers

AP invoices/payments and fixed-asset depreciation use separate opt-in mappings.
They share the same durable GL kernel, period locks, chart-of-accounts checks,
journal sequencing, and idempotency guarantees.

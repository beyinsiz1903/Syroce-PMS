---
name: Stress seed aged-booking reconciliation invariants
description: Constraints that must hold when seeding aged/past bookings + payments in the stress seed factory so financial reconciliation specs stay GREEN.
---

When aging bookings in the stress seed factory (`_build_factory_docs`), three
invariants must hold or the financial reconciliation specs break:

- **sum(folio_charges.total) == folio.total** — the 04-folio-mass C2 spec
  recomputes balance from the live folio-detail service. If you extend a stay to
  N nights you MUST regenerate per-night room charges + tax for all N nights so
  the charge sum still equals folio.total. Setting folio.total without matching
  charges = silent reconciliation mismatch.
- **folio.balance == folio.total - sum(payments.amount)** — when seeding the
  `payments` collection (previously never seeded), set balance net of payments
  and mirror the deposit into bookings.paid_amount.
- **Payment docs need BOTH `amount` and `total`** — folio-detail aggregates
  `amount`; night-audit reads `total`. Set both to the same value.

**Why:** Aging changes nights/dates, which cascades into charges, RNL night_dates
(unique index `ux_room_night` on tenant_id,room_id,night_date), and folio totals.
Touch one without the others and either an index insert fails or a reconciliation
spec drifts to FAIL/REVIEW.

**How to apply:** Keep non-aged bookings at offset 0 (check_in == today) so prior
GREEN behaviour is preserved; only past-shift the aged subset. Verify offline by
running the factory directly and asserting the three invariants + zero duplicate
(room_id, night_date) RNL pairs before trusting a baseline.

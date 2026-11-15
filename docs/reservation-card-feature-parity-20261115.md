# Reservation card feature parity — 15 November 2026

Scope: compare the old `BookingDetailDialog` / `FolioViewDialog` and standalone
`FolioDetailView` / `FolioRoutingPage` with `ReservationDetailModal`. This is a
code and local acceptance review, not completion of the November hotel scenarios.

## Feature map

| Workflow | New card before this change | Result |
| --- | --- | --- |
| Stay dates, daily rates, notes, room changes, check-in, cancellation/no-show | Present | Existing controls retained |
| Guest profiles and children/adult occupancy | Profiles present; occupancy editing missing | Adults, children and ages editable under General Information; no implicit price/date change |
| Folio windows, payers and linked receivable accounts | Present | Retained |
| Split, allocation, concessions, manual payments and receivable transfer | Present | Retained; no duplicate implementation |
| Selected-charge transfer to another open room folio | Detailed tool required leaving the card | Existing detailed folio dialog now opens above the card |
| PIN-protected refund, detailed ledger, proforma and transfer history | Detailed tool required leaving the card | Available in the same in-card dialog |
| Merge two windows of the same booking | No safe in-card merge path | New transactional merge; source closes, target payer remains |
| Charge routing rules | Separate page | In-card create/list/delete/manual apply, category/custom codes and business-date range |
| Invoice, printing, virtual card, deposit, voucher and reservation history | Present | Existing tabs/actions retained |

## Interaction and accounting

- Folios → **Aktarım, iade ve hesap ayrıntıları** opens the existing detailed
  account tools and returns to the still-mounted reservation card on close.
- Folios → **Folyo birleştirme ve yönlendirme** opens the inline tools. Merge
  requires two open windows of this booking with the same currency, an explanation
  and confirmation of the selected accounts/balances.
- For another room, use selected-charge **İşlem Aktar**. Whole-window merging is
  deliberately limited to the same booking; this avoids moving ownership of
  another booking's payments or guest liabilities.
- Merge moves original charge/payment/extra/deposit/posting records, including
  void/refund history, without copying or creating a receipt. Charge IDs, taxes,
  business dates and refund references survive. Concession history stays immutable
  and remains linked by booking and charge IDs.
- Closed/invoiced accounts, mixed-currency movements, pending concessions and stale
  reviewed balances are rejected. Source payments with sealed settlement/journal
  references cannot move; that account can be selected as the target instead.
  This preserves source reconciliation and instrument reversal references.
- Both folio locks and the booking financial lock cover a Mongo transaction.
  Transaction support is mandatory. Audit or post-move reconciliation failure
  rolls the entire operation back. Repeating the same request UUID returns the
  original result; a different payload with that UUID is rejected.
- Rules touching a merged-away window are deactivated. Routing is explicitly
  applied to existing charges by its button; saving a rule does not promise
  automatic future postings.
- Read-only/closed/loading accounts cannot mutate. Late async responses cannot
  reopen details for a different folio. Nested dialogs and select menus sit above
  the reservation card; refresh occurs without destroying its open child dialog.

## Local verification

- Frontend regression suite: folio components, detailed folio, reservation detail
  tabs, nested dialog layers and reservation operations.
- Real local Mongo replica: concurrent replay produces one committed operation;
  injected post-move and audit failures roll back; no transaction means no write.
- Backend regressions: balance/tax/concession/refund/deposit preservation,
  tenant/booking/currency/invoice boundaries, stale balances and shared locks.
- Vite production build, route bundle budgets and changed-file ESLint checked.

Deployment and live acceptance remain separate. After deployment, exercise these
paths only in the authorized Syroce test hotel and reconcile source and target
folios before recording live acceptance. No live guest or financial records were
modified for this code change.

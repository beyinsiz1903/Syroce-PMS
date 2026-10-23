# Daily occupancy and explicit folio targets

## Delivered scope

- Reports → Occupancy now has an inclusive custom start/end range (maximum 366 dates), daily table, room-type filter and quick date selections.
- Actual occupancy is shown through the authoritative PMS business day (current day provisional); on-the-books demand is shown from that day forward. Future reservations never become historical actual occupancy.
- Arrival night included; departure night excluded. Cancelled/no-show/options excluded. Known-type unassigned confirmed bookings contribute to demand, not realised physical occupancy.
- Date-specific blocks reduce sellable capacity. Weighted period percentages use room-nights, not a mean of rounded daily percentages. No artificial 100% cap. Duplicate physical assignments, invalid room references and occupants in blocked rooms are disclosed.
- Capacity is based on the current active physical room inventory plus dated room blocks; this is not a reconstructed inventory-history ledger. Removed/deactivated historical rooms require a separate historical inventory feature.
- JSON contains no guest/financial detail. Excel uses the same calculator and requires the displayed snapshot hash; concurrent changes return 409 and require refresh. Print/PDF uses the displayed table and range. No native PDF file-generation endpoint is introduced.
- Guest/company/agency windows are visible side by side, can bind a validated tenant-scoped AR account and show balance/currency. Corporate windows cannot be created as an unnamed payment method.
- Quick payment and reservation detail require an explicit target when several windows are open. A selected foreign/closed folio cannot fall back to another window. Existing single-window callers remain compatible.
- Reservation payment reference replay includes the target folio, including the duplicate-insert race path. AR transfers recheck the selected folio and linked account inside the existing financial transaction; explicit-window transfers cannot exceed its posted debt.
- Reservation summary distinguishes actual collections from city-ledger settlements without changing the existing settlement/balance calculation.

## Still separate work / not claimed

- This change does not rewrite the existing split service or automatically allocate future night-audit postings to newly created windows. Existing splitting handles posted items/amounts. The UI explicitly warns about subsequent postings. Automated room/tax/extra routing needs its own end-to-end audit (night audit, corrections, refunds, invoices and checkout).
- No claim that all financial mutations are globally serialised; existing transaction and cashier guards remain in place.
- No production records, payments, provider configuration or agency messages were changed. Local regression tests use synthetic data/mocks only. Deployment and live acceptance are separate from local verification.

## Simplified occupancy presentation (2026-10-23)

- The default screen has six columns: date, occupancy percentage, occupied rooms, vacant rooms, sellable rooms and data basis. Previous business dates use actual occupancy. The current business date and later dates use expected occupancy, including arrivals and stayovers. Actual and expected are never added together for the same date.
- The selected-period headline uses total occupied room-nights divided by total sellable room-nights for those displayed rows. It is a mixed actual/on-the-books view when the range crosses the business date, not a claim of fully realised occupancy or a simple average of daily percentages.
- Separate actual/expected totals and inventory details remain behind “Hesaplama detaylarını göster”. Inventory/overbooking alerts stay visible even when details are collapsed.
- Excel opens on “Doluluk Özeti” with the same six columns, typed dates/percentages, readable widths, frozen headings, filters and landscape printing. “Detaylar” retains all fifteen reconciliation fields and the separate original actual/expected period totals. Snapshot matching and tenant scoping are unchanged.
- This is presentation work only. It does not change the source occupancy calculator, bookings, room blocks, accounting or financial acceptance status.

## Acceptance after deployment

1. For an authorised demo tenant, choose a date range crossing the business day. Reconcile assigned/unassigned arrivals, stayovers, same-day turnover, cancelled/no-show, comp, dated blocks and overbooking against reservations.
2. Download Excel and print/PDF; verify row totals, filters, warning details and weighted totals. Change inventory between read/export and verify refresh is required.
3. In synthetic reservation debt, split existing charges into guest/company windows; bind a demo AR account; settle the company window to AR and the guest window to card. Reconcile folio balances, the outstanding AR balance and cash collections independently.
4. Verify permissions, another hotel's IDs, closed folios, duplicate payment references and request retries. No live cash collection or fiscal invoice is authorised by these checks.

## Local verification (2026-10-23)

- Backend focused regression: 160 passed, 4 warnings (occupancy, AR, window targeting, payment replay, folio split/balance/reconciliation).
- Frontend focused regression: 159 passed across 15 files, including all reservation-detail unit suites, reporting crosschecks, target selection and occupancy/export scope tests.
- Changed-source ESLint: zero warnings. Ruff: passed. Production Vite build: passed. Theme guard and skip/test-inventory budget: passed. `git diff --check`: passed.
- Knip remains advisory: the local invocation reports unused-code inventory and missing E2E_BASE_URL in Playwright configs; it is not counted as a passed verification.
- These checks do not establish live acceptance, full-suite coverage thresholds or browser visual acceptance.

### PR CI follow-up

- The legacy FinancialMutationSafety fixture omitted folio status and clicked before the new asynchronous open-target lookup completed. Its fixture now explicitly supplies an open folio and awaits readiness; zero-payment and duplicate-submit assertions remain intact. Closed/unknown statuses have separate fail-closed tests.
- Security CI detected PYSEC-2026-4322 in the pinned Brotli 1.2.0 decoder. The runtime pin is updated to 1.2.1, not ignored/allowlisted. A requirements regression prevents reverting to the affected version. The patched binary was installed in an isolated temporary target and compression/decompression checked without changing the host Python environment.

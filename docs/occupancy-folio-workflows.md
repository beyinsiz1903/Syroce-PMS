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

- The daily-list view has six columns: date, occupancy percentage, occupied rooms, signed net remaining rooms, sellable rooms and data basis. Previous business dates use actual occupancy. The current business date and later dates use expected occupancy, including arrivals and stayovers. Actual and expected are never added together for the same date.
- The selected-period headline uses total occupied room-nights divided by total sellable room-nights for those displayed rows. It is a mixed actual/on-the-books view when the range crosses the business date, not a claim of fully realised occupancy or a simple average of daily percentages.
- Separate actual/expected totals and inventory details remain behind “Hesaplama detaylarını göster”. Inventory/overbooking alerts stay visible even when details are collapsed.
- Excel opens on “Doluluk Özeti” with the same six columns, typed dates/percentages, readable widths, frozen headings, filters and landscape printing. “Detaylar” retains all fifteen reconciliation fields and the separate original actual/expected period totals. Snapshot matching and tenant scoping are unchanged.
- The initial six-column simplification was presentation-only. The matrix follow-up below also corrects forecast commitment counting; neither change mutates bookings, room blocks, accounting or financial acceptance status.

### Room-type matrix follow-up

- The default is now a 14-day room-type/date matrix, with the house total and every active inventory type together. Percentage, net remaining (+/−) and occupied-room indicator modes use the same rows. A separate daily list remains available. Quick 1/7/14/30-day selections apply immediately; custom inclusive ranges still allow up to 366 dates.
- One server response builds both house and room-type scopes from the same three tenant-scoped input queries. Inputs are bucketed before type calculation to avoid querying or scanning the entire booking population separately for every type. Untyped physical rooms get an explicit row; unknown room references remain warnings rather than guessed inventory.
- Expected demand counts distinct eligible reservation commitments, including separate bookings incorrectly assigned to the same room. Duplicate source rows for the same booking ID are still deduplicated. Actual occupancy remains unique physical rooms. This deliberate forecast correction exposes assignment conflicts as possible excess sales; it does not change ADR, revenue or accounting calculators.
- Net remaining is capacity minus occupied/demand rooms and is never floored to zero. A type can be oversold while the house total is positive. Type warnings and red cells remain visible in that case; percentages above 100 are not capped in cells, chart or Excel.
- The chart shows the house or the selected room type. Each matrix cell opens read-only capacity, closures, arrivals/stayovers, unassigned demand and assignment-conflict figures. No guest identities, booking mutations or channel sell-limit edits are introduced.
- Excel accepts an explicit `view=matrix|daily` and `metric=occupancy|remaining|occupied`, bound to the existing full-data snapshot. The matrix is split into seven-date print blocks, with native percentage/numeric cells and signed remaining formats. Full group evidence stays in Details. Browser printing also uses seven-date tables, rather than squeezing a month/year into one wide page.
- This is PMS inventory availability, not a new group-allotment, sell-limit or channel-quota engine. Existing configured physical room blocks are included. No claim is made that separate unpicked group allotments or component-room sharing are newly implemented.

### Matrix verification

- Backend occupancy/API/export and canonical room-night regression: 45 passed. Existing openpyxl UTC deprecation warnings remain; no test failures are suppressed.
- Full frontend: 381 files / 1,896 tests passed. Latest targeted occupancy suite: 13 passed. Production build, changed-file ESLint/Ruff, theme/layout guards and `git diff --check` passed.
- Browser acceptance used a local isolated preview of the actual component with synthetic data: all-type matrix, >100%/negative cells, indicator change, read-only drilldown, stale filter/export disabling, selected-type chart and immediate seven-day range selection checked. No production or provider records changed.
- The production exporter was exercised with synthetic 14-day / 35-room / three-type inputs. Native percentage/date formats, signed remaining values, full type evidence, seven-date print blocks and snapshot mismatch rejection checked; the matrix was rendered for visual review. This is not a claim of a new live production reconciliation or completed deployment.

## Acceptance after deployment

1. For an authorised demo tenant, choose a date range crossing the business day. Reconcile assigned/unassigned arrivals, stayovers, same-day turnover, cancelled/no-show, comp, dated blocks and overbooking against reservations.
2. Download Excel and print/PDF; verify row totals, filters, warning details and weighted totals. Change inventory between read/export and verify refresh is required.
3. In synthetic reservation debt, split existing charges into guest/company windows; bind a demo AR account; settle the company window to AR and the guest window to card. Reconcile folio balances, the outstanding AR balance and cash collections independently.
4. Verify permissions, another hotel's IDs, closed folios, duplicate payment references and request retries. No live cash collection or fiscal invoice is authorised by these checks.

## Existing-window allocation follow-up (2026-10-24)

- Reservation detail → Folyo/Ödeme → **Hesaplar Arası Paylaştır** uses existing open guest/company/agency windows. The original “Folyo Böl” (create new windows) flow remains available. This follow-up does not add automatic future room/tax/extra routing.
- Choose source and destination explicitly, then either posted positive original charge items (including their original tax/date/category) or a precise monetary debt share. No payment/refund/discount/comp, new folio, new AR balance or fiscal invoice is created by allocation. A full source debt allocation is allowed; unposted booking-level extras are not silently absorbed.
- Amount allocation produces one negative and one positive `split_adjustment` on the same authoritative open business date. Their amounts cancel exactly; existing taxable revenue and original tax stay unchanged. Payments remain on their original windows. Use item allocation when the tax-bearing charges themselves must belong to the company window.
- `POST /api/folio-windows/allocate` requires transfer-folio permission, a UUID request identifier and an explanation. Source/destination must belong to the same tenant and reservation, be open, share a known currency and not have linked invoices (including drafts). Missing business date, stale charge selections, non-original/negative/voided items and amounts exceeding actual posted debt are rejected. Cached `folio.balance` is not authoritative.
- The existing booking/folio financial resource locks and Mongo snapshot/majority transaction cover both balances, item moves/paired adjustments, operation evidence and audit. There is no standalone/nontransactional fallback. Same request ID/content replays the result; changed content with the same ID is rejected. Audit metadata links both windows and records before/after balances. This does not claim all legacy financial writers globally follow these locks.
- The UI previews both balances, accepts Turkish decimal commas, prevents duplicate submits, retains the same request ID on uncertain-response retries and locks form changes/closing while that result is unresolved. A successful commit followed by a refresh failure remains a success and cannot be resubmitted. These retry safeguards apply within the active panel; do not start another allocation from a different tab while a result is unresolved.
- Folio cards refresh on financial revisions and ignore older responses; failed refreshes do not leave stale cards selectable. Legacy by-item split now also rejects non-open source folios; its source picker cannot choose closed windows.
- Local mocked-storage verification covers 6,000 company + 4,000 guest debt, canonical card-versus-AR settlement/collection arithmetic, full/partial/cents allocations, tenant/booking/currency/permission/invoice guards, replay/content mismatch, concurrent-callback serialisation and injected rollback. It is not a live Mongo concurrency proof, real AR settlement/provider charge or production acceptance.

## Local verification (2026-10-23)

- Backend focused regression: 160 passed, 4 warnings (occupancy, AR, window targeting, payment replay, folio split/balance/reconciliation).
- Frontend focused regression: 159 passed across 15 files, including all reservation-detail unit suites, reporting crosschecks, target selection and occupancy/export scope tests.
- Changed-source ESLint: zero warnings. Ruff: passed. Production Vite build: passed. Theme guard and skip/test-inventory budget: passed. `git diff --check`: passed.
- Knip remains advisory: the local invocation reports unused-code inventory and missing E2E_BASE_URL in Playwright configs; it is not counted as a passed verification.
- These checks do not establish live acceptance, full-suite coverage thresholds or browser visual acceptance.

### PR CI follow-up

- The legacy FinancialMutationSafety fixture omitted folio status and clicked before the new asynchronous open-target lookup completed. Its fixture now explicitly supplies an open folio and awaits readiness; zero-payment and duplicate-submit assertions remain intact. Closed/unknown statuses have separate fail-closed tests.
- Security CI detected PYSEC-2026-4322 in the pinned Brotli 1.2.0 decoder. The runtime pin is updated to 1.2.1, not ignored/allowlisted. A requirements regression prevents reverting to the affected version. The patched binary was installed in an isolated temporary target and compression/decompression checked without changing the host Python environment.

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
- Debt-only allocation adjustments are excluded from reservation invoice candidates. Automatic from-folio fiscal conversion rejects these adjustments rather than treating them as another taxable service. The amount-mode UI explains this limit; per-window invoicing requires original charge/tax allocation, not just a debt share.
- `POST /api/folio-windows/allocate` requires transfer-folio permission, a UUID request identifier and an explanation. Source/destination must belong to the same tenant and reservation, be open, share a known currency and not have linked invoices (including drafts). Missing business date, stale charge selections, non-original/negative/voided items and amounts exceeding actual posted debt are rejected. Cached `folio.balance` is not authoritative.
- The existing booking/folio financial resource locks and Mongo snapshot/majority transaction cover both balances, item moves/paired adjustments, operation evidence and audit. There is no standalone/nontransactional fallback. Same request ID/content replays the result; changed content with the same ID is rejected. Audit metadata links both windows and records before/after balances. This does not claim all legacy financial writers globally follow these locks.
- The UI previews both balances, accepts Turkish decimal commas, prevents duplicate submits, retains the same request ID on uncertain-response retries and locks form changes/closing while that result is unresolved. A successful commit followed by a refresh failure remains a success and cannot be resubmitted. These retry safeguards apply within the active panel; do not start another allocation from a different tab while a result is unresolved.
- Folio cards refresh on financial revisions and ignore older responses; failed refreshes do not leave stale cards selectable. Legacy by-item split now also rejects non-open source folios; its source picker cannot choose closed windows.
- Local mocked-storage verification covers 6,000 company + 4,000 guest debt, canonical card-versus-AR settlement/collection arithmetic, full/partial/cents allocations, tenant/booking/currency/permission/invoice guards, replay/content mismatch, concurrent-callback serialisation and injected rollback. It is not a live Mongo concurrency proof, real AR settlement/provider charge or production acceptance.
- Local follow-up: the full frontend package passed 382 files / 1,907 tests after correcting an existing async readiness-test assertion (wait for content, not placeholder presence; stale-hotel response checks remain). A later full run exposed the same early-assertion pattern in peer-PIN rejection; that test now waits for rejection handling and reasserts that no void request was sent. Focused allocation/financial backend and invoice regressions passed, as did build/bundle budgets and changed-source lint. No test, coverage threshold or CI guard was disabled.

## Enterprise billing controls — first bounded delivery (2026-10-24)

This is **not** certification that every five-star payment workflow is complete.
No production financial records, card charges, provider settings or fiscal
documents were changed while implementing or testing this delivery.

- Reservation detail → Folyo/Ödeme → **Kurumsal ödeme / ikram kontrolleri** distinguishes actual external collections, AR transfer, concessions, refundable security and authorization. The provider catalog exposes actual configured adapter capabilities, not a fabricated successful connection/live certification. Gift cards, wallets, barter and loyalty redemption are not activated by adding a label.
- Selected **posted** original services can be requested as room/service comp, service recovery or commercial discount, for the full selected value, a percentage or precise minor-unit amount. This does not alter future daily rates or mean all-inclusive/full-stay comp. An explicitly configured per-decision currency limit and a different authorized approver are required. The request snapshot, remaining per-service concession capacity, open folio, invoice linkage, currency and balance are revalidated at approval. Application, audit and durable replay evidence share the reservation financial transaction. Original revenue/tax rows and closed business dates are not rewritten. No tax credit note is fabricated.
- Existing accommodation-rate comp/price override workflows still have their existing permissions. This new approval workflow is **not yet a global approval policy covering every legacy rate/POS/adjustment writer**. Approver-specific daily/stay budgets and dedicated reversal workflows remain separate work. New protected concessions cannot be voided as if cash had been refunded.
- Manual collection entry points reject comp, discount, AR, authorization, security application and unsupported tender names as payment methods. The main collection selector no longer offers a discount as cash/card collection. Legacy fake intent endpoints fail explicitly instead of writing mock Stripe IDs or unscoped payment intents.
- Refundable security is a separate liability ledger, not `deposits`/booking paid amount or an authorization. An external receipt needs a voucher/bank/POS reference. Cash receipt/refund and its liability movement share a transaction and require an open TRY drawer; foreign-cash security is blocked until an immutable FX cashier workflow exists. Applying security requires an explicit same-booking open folio and sufficient same-currency posted debt. It creates a non-cash offset, not another collection. Partial refund/application, immutable movements, cross-tenant checks, business-date evidence and persistent request/reference replay are included. No card/bank transfer is initiated by recording external receipt/refund evidence. Dedicated correction/unapplication remains separate; generic payment void must not decouple the liability from the folio.
- The existing deposit tab is explicitly labelled **accommodation prepayment**; its legacy semantics are preserved, not silently reclassified as security. Migrating historical deposits needs a separate reviewed reconciliation.
- PSP collection resolves an explicit target when several windows are open and rejects mismatched folio currency before provider I/O. Persistent intents bind amount/currency/card/folio, block repeated pending/3DS/unknown charges beyond the short-lived idempotency cache, and preserve the original result. Card-payment ledger rows now carry currency. An already-collected but unrecorded outcome is explicitly reported as needing reconciliation; it is not presented as a fully posted folio success.
- Direct-bill transfer revalidates account status, configured currency and available credit under the canonical account lock. Existing zero-limit legacy accounts retain their previous unrestricted semantics; a positive credit limit requires an explicit account currency. New AR movements carry currency and a due date based on the open PMS business day. This is not a reconstruction of every legacy AR balance or a new whole-system credit-limit engine.
- The existing `/folio-routing/apply` endpoint previously wrote only a `routed_to` marker. It now moves original items/taxes between actual same-reservation windows through the atomic allocation service. Overlapping matching rules, closed destinations, invoice-linked accounts, unknown dates, insufficient source debt and mixed currencies fail closed. **This endpoint is still manual posted-item routing**, not automatic future night-audit/POS routing, not partial tax-line splitting and not cross-booking/group-master routing.
- Remaining concession capacity follows the service ID across folio moves; moving a previously comped service cannot reset its capacity. Reservation activity and printable folios label security/AR/comp offsets separately from new collection. Print totals exclude pending/failed payments and handle positive refund amounts with the correct sign.

### Verification for this delivery

- 244 isolated backend regressions passed (concession/security state machines, remaining capacity after movement, cash transaction propagation/failure, PSP durable replay, AR/window/void/currency/input guards). One pre-existing `datetime.utcnow()` deprecation warning is retained; no test/coverage guard is disabled.
- Full frontend: 384 files / 1,917 tests passed. Production build, full backend Ruff, full frontend ESLint hard gate, changed-source zero-warning ESLint, route bundle budgets, theme/layout, orphan/import-boundary, requirements-parity and skip/inventory guards passed.
- Full frontend coverage gate passed unchanged thresholds: statements 30.82%, branches 27.48%, functions 24.01%, lines 31.59%. This is whole-frontend coverage, not a claim of complete financial coverage.
- Synthetic browser preview verified a 25% request against a 5,000 TRY service as 1,250 TRY awaiting a different approver, and displayed the separate security ledger. Preview requests were in-memory mocks, not live financial operations.
- The worker-runtime static import-closure check reports nine missing distributions. The same nine were reproduced on a clean archived `92624d7de` base; this delivery does not certify that existing CI/dependency issue as fixed. API import closure has zero missing distributions but four pre-existing unmapped imports needing review. Live worker/API image boot and real Mongo concurrency remain unverified locally.

### Remaining enterprise acceptance scope

| Area | Remaining work before claiming end-to-end readiness |
| --- | --- |
| Automatic routing | One rule engine across all night-audit/manual/POS/extra writers; dated, percentage, daily/stay/covers limits; original tax allocation, reversal, invoice and checkout acceptance. |
| Comp/house use | Future-night/category benefits, house-use statistics, global approval enforcement across legacy writers, per-authorizer budgets and atomic reversals. |
| Card lifecycle | Authorize/increment/capture/release/refund/void endpoint orchestration and provider sandbox/live acceptance; contract support alone is insufficient. |
| OTA/VCC | Activation/balance/currency restrictions, net/gross commission and payout reconciliation across each connected provider. |
| Stored value / instruments | Gift card/loyalty issuer validation, liability/redemption/reversal and double-use safeguards; cheque lifecycle and bank clearance before treating it as collected money. Unsupported raw tenders are blocked. |
| AR/group billing | Authoritative legacy balance reconciliation, aging/credit acceptance, multi-reservation master accounts and payment allocation. |
| Security | Dedicated correction/unapplication, provider-driven refunds, liability report/reconciliation acceptance and historical migration. |
| Fiscal/localization | Approved local invoice/credit-note/tax treatment and zero/three-decimal currency acceptance; a non-cash folio offset is not a fiscal document. |

Unit/storage mocks and synthetic browser acceptance do not prove real Mongo
concurrency, live PSP operation or fiscal compliance. The dedicated new
transactions fail closed when Mongo transactions are unavailable.

New concession/security flows currently fail closed outside the verified
two-decimal TRY/USD/EUR/GBP/CHF set; unsupported currency precision is not
silently rounded or advertised as globally supported.

## Front-office forecast reference layout (2026-10-24)

- Reports → **Forecast / Öngörü Raporları** now opens **Ön Büro Forecast**. This is the daily operational/on-the-books report, not the statistical prediction. The existing prediction, pace and pickup tabs remain separate and retain their scope/currency guards.
- Custom inclusive start/end dates (maximum 366 days), adjacent periods, current week/month/year/day and an optional room-type filter feed four weighted period KPIs. Five views share one response: availability, arrivals/departures, occupancy, reservation room value and stay types. A date selection in the chart highlights the same daily table row. Wide tables keep the date column visible; small screens scroll rather than hide figures.
- Availability stacks **booked rooms**, **remaining definite group allotment**, **available rooms** and **closed physical rooms**. Both `group_blocks` and the legacy `block_reservations` inventory are read; legacy booking date aliases are normalized for this read-only report. Pickup is recomputed from linked reservations for each night, not lifetime `rooms_picked_up`/`rooms_available` counters. Tentative groups are visible but do not deduct inventory. Type-filtered groups require a validated type/breakdown; unknown allotments are not guessed.
- The reference's default occupancy denominator is physical capacity: **53 occupied / 60 physical = 88.33%**, even if 2 rooms are closed and only 5 are available. A separately labelled sellable-capacity basis is selectable (53 / 58 = 91.38%). Period percentages use total room-nights; overbooking preserves negative remaining and values above 100%.
- Before the PMS business day only actual room-nights count; from that day forward eligible reservation commitments count. Arrival nights are included and departure nights excluded. Cancelled/no-show/options do not deduct rooms. Day-use is separate from overnight occupancy. Comp and house-use read reservation/nightly flags; financial concession offsets are not reclassified as accommodation types.
- Room value uses authoritative daily rates (including explicit zero/comp), otherwise a cent-preserving allocation of the stay total. It is **not collected cash or posted/fiscal revenue**. Currencies stay separate; unpicked group revenue is not invented. Missing/ambiguous prices or unknown room references cannot produce a false complete revenue/ADR total. Known zero revenue stays zero; unknown values stay blank/“Doğrulanamadı”.
- Adults/children come from reservation counts. Known ages 0–2 are separated as infants for this report only; missing ages do not imply zero infants and do not change any pricing/child policy. Definitions and data-quality diagnostics remain visible. Capacity is current active inventory plus dated closures, not a reconstructed historical inventory ledger.
- `GET /api/reports/frontdesk-forecast` uses tenant-scoped uncapped projections without guest identities and requires reporting permissions/module access. Excel has the selected view/basis, typed dates and amounts, separate currency columns, an availability chart, print settings and definitions/warnings. A hash of all displayed data binds export to the loaded snapshot; changes require refresh (409). Print/PDF prints the loaded scope rather than refetching different data.
- Local browser acceptance uses only a clearly marked synthetic preview of the real component. No production inventory, reservations, payments, group allotments or provider configuration are mutated. Deployment/live reconciliation remain separate acceptance steps.

### Forecast acceptance after deployment

1. Open the report for an authorized demo tenant and reconcile a range crossing its PMS business day against actual/confirmed reservations and dated closures. Verify all-house and each room-type scope.
2. Reconcile definite group blocks with night-specific pickup, partial-date pickup, tentative blocks, unknown allocations, early checkout, day-use, comp and excess sales. Unknown inventory must display a warning, not exact availability.
3. Compare chart/table/Excel for all five views and both occupancy bases; check multiple currencies, a zero nightly price and missing/duplicate daily rates. Change data between load/export and verify refresh is required.
4. Validate another tenant's data is inaccessible, permissions are enforced and large supported ranges remain usable. These local/unit checks do not certify a real Mongo snapshot transaction or a historical inventory reconstruction.

### Local forecast verification

- Focused backend forecast, occupancy calendar/API/export and canonical forecast regression: **107 passed**. Existing openpyxl UTC deprecation warnings remain visible.
- Full frontend coverage run (two workers, unchanged thresholds/timeouts): **385 files / 1,926 tests passed**. Statements 30.99%, branches 27.65%, functions 24.23%, lines 31.74%. An earlier higher-parallelism run had two unrelated 5-second test timeouts; no assertions or timeout/coverage thresholds were weakened, and both passed in the full bounded rerun.
- Production build, full backend Ruff, full frontend ESLint error gate, changed-source zero-warning ESLint, route bundle budgets, theme/layout, orphan, import-boundary, requirement-parity and skip/inventory guards passed. The API static import scan has zero missing distributions but still lists four previously unmapped imports; it is not a live API/worker boot certification.
- Browser checks exercised the real component with synthetic data: stacked availability and daily table, room-type filtering, chart-to-row selection, arrivals/departures and revenue view. The isolated mock preview was removed before commit; no mock API override is shipped.

## Local verification (2026-10-23)

- Backend focused regression: 160 passed, 4 warnings (occupancy, AR, window targeting, payment replay, folio split/balance/reconciliation).
- Frontend focused regression: 159 passed across 15 files, including all reservation-detail unit suites, reporting crosschecks, target selection and occupancy/export scope tests.
- Changed-source ESLint: zero warnings. Ruff: passed. Production Vite build: passed. Theme guard and skip/test-inventory budget: passed. `git diff --check`: passed.
- Knip remains advisory: the local invocation reports unused-code inventory and missing E2E_BASE_URL in Playwright configs; it is not counted as a passed verification.
- These checks do not establish live acceptance, full-suite coverage thresholds or browser visual acceptance.

### PR CI follow-up

- The legacy FinancialMutationSafety fixture omitted folio status and clicked before the new asynchronous open-target lookup completed. Its fixture now explicitly supplies an open folio and awaits readiness; zero-payment and duplicate-submit assertions remain intact. Closed/unknown statuses have separate fail-closed tests.
- Security CI detected PYSEC-2026-4322 in the pinned Brotli 1.2.0 decoder. The runtime pin is updated to 1.2.1, not ignored/allowlisted. A requirements regression prevents reverting to the affected version. The patched binary was installed in an isolated temporary target and compression/decompression checked without changing the host Python environment.

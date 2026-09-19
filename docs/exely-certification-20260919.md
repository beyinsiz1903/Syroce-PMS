# Exely certification evidence — 2026-09-19

Scope: Syroce Demo Hotel superadmin test tenant, Exely TEST property 501694.
No Canyon production hotel data was changed. This is a partial test record, not a certification pass.

## Verified live

- The running backend polls Exely every 180 seconds. A second replica logs `lease_held` while the owner polls successfully; this is not evidence of an outage.
- The test connection currency was changed from TRY to USD through Syroce, matching the supplied plan.
- Exely PMS inventory and a fresh Syroce discovery both return Standard API room code `500157400`, not the stale `5001574`. Deluxe is `5001575`, Suite `5001576`. Tariff API codes are `10003869` and `10003870`.
- A controlled write with stale Standard code returned warning 783, `Unknown InvTypeCode="5001574"`. A panel-ID pair returned `Unknown RatePlanCode="10009740"`. Neither was counted as success.
- Both Standard mapping rows were corrected through Syroce. The existing panel codes were retained; the PMS API code pair takes precedence for outbound ARI.
- At 12:29 UTC, a single Standard/Base USD100 price write for November 10–12 was confirmed by Exely. Its Exely price calendar showed USD100 on those dates and blank adjacent dates.
- At 12:30 UTC, Syroce's bulk UI sent prices for three categories and six mappings: Standard USD100, Deluxe USD120, Suite USD150, November 10–12. The durable `rate_batch` state is `confirmed`. The QA booking engine then offered all three categories for November 10–12. No agencies were selected.
- QA booking `20261110-501694-1200418715` was created: Standard + Deluxe, 2 nights, total USD440, 2 + 3 adults, pay at check-in, explicit test-only comment. The user approved the consent/terms checkbox at action time.
- Without pressing manual pull/import, the scheduler fetched the booking at 12:38:57 UTC, durably created two PMS bookings at 12:38:58, and acknowledged at 12:38:59–12:39:00. Exely delivery log reports successful create and confirm; Syroce shows `imported`.
- Actual room totals are correct: USD200 and USD240. Dates are November 10 14:00 to November 12 12:00.
- The second room guest was changed to a distinct test name in QA; Exely confirmed the change. A read-only Undelivered diagnostic captured its structural XML without sending an ACK. Normal worker processing remains responsible for ACK.

## Failures found; fixes in this branch, not yet live-verified

- Guest counts use `AgeQualifyingCode="AdultBed"`, with multiple entries per room. Old parser accepted only numeric `10` and overwrote rather than accumulated entries. PMS incorrectly stored 1 adult per room. Parser now accepts the observed code and accumulates counts.
- Exely sends nightly amounts as `RoomRate EffectiveDate=.../Total`, without nested `Rate`. Old parser lost all nightly prices. Both the observed format and nested OTA rate format are handled.
- Room guests reference `ResGuestRPH` in `GuestCount`; parser previously overwrote the reservation guest with the last profile. Guest references now stay with each room, normalization preserves them, and room guest records have stable separate IDs and update on modification.
- PMS booking fields dropped currency and daily rates. They are now preserved.
- Mapping UI described API codes as inbound-only, contrary to outbound code behavior. Help text is corrected, including removal of test-specific Suite advice.

## Still pending / not certified

- Deploy and replay a NEW provider version of the controlled booking; confirm 2/3 adults, distinct room guests, USD currency, nightly amounts, stable booking IDs and one ACK.
- Child-bed payload/counts, payment method, source-channel names, Liberty external ID.
- Full maximum-period availability/rates, forced availability, all set/unset restrictions, delta-only updates, create/cancel inventory restoration.
- Date extension/shortening, room-category changes, full and partial cancellation with exact stock restoration.
- Unmapped-category denial/redelivery and two separately pending bookings.
- Prepayment and extras scenario.
- Two legacy imported-event rows from August lack provider version identity and cannot enter the new lifecycle. This is separate from current connectivity; no fabricated ACK metadata or destructive migration was applied.
- Read-only `All` queries returned zero even while a known booking exists. This is not proof of missing provider data and is not used for recovery.
- The bulk UI still displays an empty channel label/“no active channel” despite the backend selecting Exely and delivering successfully.

No code hot-patching, manual ACK, live-hotel mutation or certification-complete claim was made.

## Follow-up after PR 712 deployment

- Deployed merge `16f86b9b9`: at 13:08 UTC a new guest modification was automatically ingested. Existing booking IDs were preserved, Standard/Deluxe adults are 2/3, currency USD, nightly rates 100/120, totals 200/240. Durable update preceded successful OTA_NotifReportRQ. This supersedes the first pending item above, not the whole certification plan.
- Contact modification to the reserved fictional UK test number ending 0124 was saved in Exely. A read-only Undelivered response for the controlled booking proved contact data is in `ResGlobalInfo/Profiles/ProfileInfo/Profile/Customer`. Current deployed parser ignored that location; the stored reservation phone remained empty after automatic ingest at 13:32 UTC.
- Same real response: reservation note is under direct `ResGlobalInfo/Comments`; `Guarantee/Comments` holds PaymentMethodName=PayOnArrival and PaymentSystemTitle=At check-in. Recursive comment parsing incorrectly replaced the guest note with the payment title. Payment method also remained empty.
- Follow-up fix reads the global contact, keeps direct reservation comments separately, parses PaymentMethodName, and preserves payment_method in PMS booking fields. Focused parser/lifecycle/pilot tests: 117 passed. Live retest requires deployment and a new provider version; no manual ACK or database rewrite used.
- Date-extension test confirmed in QA for the same controlled booking: Nov 10-13, Standard 300 USD + Deluxe 360 USD = 660 USD. At 13:38:22 UTC both existing PMS booking IDs updated to Nov 13, with three correct nightly entries. However latest tenant ARI delivery remained the 12:30 rate batch: extension availability delivery is NOT verified. Do not mark the full extension scenario passed.

## Local verification

- Focused parser, lifecycle and pilot-contract suites: **116 passed**.
- Broad `tests/test_exely*.py`: **324 passed, 20 failed, 45 errors**. This is NOT an all-green suite. HTTP integration tests require a localhost:8000 backend that is not running. Six isolated assertions in `test_exely_versioning_wsse.py` expect older WSSE/password/nonce behavior and integer provider versions, whereas current PMSConnect code uses its Security header and exact provider timestamps. These unrelated assertions were not weakened to obtain a green run.
- Frontend unit tests were not run: this checkout has no frontend node_modules.
- `git diff --check` passes.

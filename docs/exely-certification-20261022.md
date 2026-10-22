# Exely PMSConnect 1.17 - certification execution, 2026-10-22

Source: user-supplied `Syroce_Test_plan_PmsConnect_by_implementation_questionnaire.pdf`, all three pages inspected as text and rendered images.
Target: TEST property **501694** only. No production hotel, real payment, agency delivery, KBS, manual ACK or source-version rewrite is authorized by this record.
Code under test: `9431b3668d33444cf58e562db3095bc1ee49c92c`, merged as `ba83ba98fd18c5920b8f66e5fd335c92a37894a7` (#1389).

## Evidence and interpretation

- This execution ran **407 offline checks, zero failures/errors/skips** across 16 targeted suites, including isolated real MongoDB tests. One unrelated `datetime.utcnow()` deprecation warning remains.
- JUnit: `/private/tmp/syroce-exely-certification-20261022/offline-results.xml`.
- These checks establish code behavior with synthetic data, **not provider-side certification**. A green test enforcing HOLD does not satisfy a plan requiring RequestDenied.
- The earlier live child case `20261110-501694-1200421078` was reconciled through Read Reservation API: 2 adults, child age 6, USD120 unchanged; current PMS readback verified its proof. Raw SOAP/version/ACK records were preserved.
- A new live UI preview, not a provider write, covered 2026-10-22 through 2027-10-21: 365 dates, three room categories, six mapped room/rate pairs, 2,190 cells, availability 2. No agency selected. Preview explicitly warned PMS/agency-only despite the Exely provider. It was closed without publishing. The 365-date range is an exercised UI range, **not proof of the provider's maximum supported horizon**.
- Preview evidence: `/private/tmp/syroce-exely-certification-20261022/availability-preview.png`.

## Live execution continuation

- With action-time approval, created synthetic QA reservation **20261110-501694-1200421110**, Nov 10–11, Standard USD100 + Deluxe USD120 = **USD220**, pay now USD0. Marketing unchecked. Provider subsequently displayed 2 adults Standard / 3 adults Deluxe; do not infer occupancy from the original search form.
- The scheduled reader fetched it automatically, but held it as `pending_mapping`. Dynamic Rate USD was not mapped. Discovery freshly confirmed API rate **10003541** (not a guessed adjacent code), Standard API **500157400**, Deluxe API **5001575**. QA panel codes are rate **10009738**, rooms **5003299/5003300**.
- Added only those two Dynamic mappings, preserving all six existing mappings and leaving availability OFF for the new rate pairs (the existing base pairs already own A). A subsequent normal OTA read changed the same source row to **imported**, USD220. No manual PMS import button or fabricated ACK used.
- Temporarily shortened TEST polling to 3 minutes, then restored its original **15 minutes**. Global dry-run and unrelated connections were not changed.
- Test Booking readback displays “Kişi ayrımı API ile doğrulandı”, but explicitly says full acceptance is pending. Screenshot: `/private/tmp/syroce-exely-certification-20261022/multiroom-imported.png`.
- R7: changed synthetic contact first name to `CertContactUpdated` and email to `pms-exely-qa-updated@example.com`; Exely confirmed saved. Normal OTA read displayed the updated contact name on the same PMS source row, USD220 unchanged. Full normal-booking email readback still pending.
- R8: changed only Deluxe room guest to `CertDeluxeGuestUpdated`; Exely showed Standard guest unchanged, and confirmed saved. Normal OTA read executed; per-room PMS detail still pending.
- R10: extended checkout to Nov12. Exely calculated Standard USD200 + Deluxe USD240 = **USD440**. After Confirm, normal OTA read displayed **Nov12 / USD440 / imported** on the same reservation. Outbound changed-date availability and per-version ACK counts remain unverified.
- R9: provider saved comment `SYNTHETIC CERTIFICATION TEST ONLY. R9 COMMENT UPDATED. No actual guest, stay, payment, or marketing consent.`; normal OTA read executed. PMS comment detail still pending.
- Local UI corrections now distinguish Exely broadcast from PMS-only delivery and do not equate an unavailable OTA catalogue with a disconnected Exely link. Agency-only exclusion is preserved. **18 frontend tests passed**, targeted ESLint and `git diff --check` passed. These changes are **not deployed**.
- R11: shortened checkout back to Nov11, Exely total returned to USD220. Normal OTA read showed Nov11 / USD220 / imported on the same source reservation.
- Normal PMS detail verified the Deluxe booking's updated separate guest name, 3 adults / 0 children, USD120 accommodation / USD0 paid / USD120 remaining, updated synthetic email, updated R9 comment and source **Exely**. Evidence: `/private/tmp/syroce-exely-certification-20261022/deluxe-modification-pms.png`.
- That normal detail exposed a display omission: an unassigned booking hid its known booked category (`room_type`) behind `-`. Added category fallback without pretending a physical room was assigned; assigned-room precedence has a regression test. Combined frontend run now **24 passed / 5 files**, targeted lint passed. Not deployed.
- R12 attempted Standard category change in QA; provider returned **“No available rooms have been found” / room type was not changed**. No mutation occurred. Evidence: `/private/tmp/syroce-exely-certification-20261022/provider-room-change-unavailable.png`. This is not a passed category-change case.
- R15: cancelled only Deluxe via provider's Delete a room flow. Provider confirmed saved, left Standard active at **USD100**. Subsequent normal OTA read showed USD100 / imported. Per-room cancelled PMS status and category/date inventory restoration remain to be read back.
- Final cleanup/cancellation: cancelled the remaining Standard through provider's normal flow, giving the synthetic certification reason. Provider confirmed `1200421110` successfully cancelled; normal OTA read showed **cancelled / cancellation_done**. No permanent personal-data delete was clicked. Evidence: `provider-cancelled.png` and `pms-cancellation-done.png` under the proof directory above. This is final cancellation **after** a partial cancellation, not a second independent all-two-rooms-at-once R14 test.

## Subsequent stock investigation and actual ARI blocker

- Provider availability calendar readback for Nov10/11/12 showed Standard **5/5/7**, Deluxe **5/6/7**, Suite **1/1/1** online/PMS availability. Therefore the earlier room-change failure must not be summarized as proved zero stock. Baseline screenshot: `provider-stock-baseline.png` under the proof directory.
- Dynamic Rate settings show all room types, USD, check-in payment, and prices supplied automatically by price sources. No provider configuration was changed during this inspection.
- Attempted A2 force upload for **Nov10 only, Standard/Deluxe availability5**, no prices/restrictions/agencies. The normal PMS bulk endpoint rejected it with HTTP422: “Yalnız acente oda tipleri için en az bir acente seçin”. Do **not** count this as provider delivery; rejection occurs before local calendar writes and provider scheduling.
- Root cause: `_build_exely_grid` publishes explicit panel/mapping IDs such as `5003299`, but the bulk destination filter compared them to discovery API aliases such as `500157400`. Added a tenant-scoped writable-code lookup from complete explicit Exely mappings, also used by agency-only room classification. Discovery-only and incomplete mappings cannot authorize writes; HotelRunner is unchanged.
- New tests cover distinct API/panel aliases, absent/incomplete mappings, tenant-scoped query, mapped bulk availability acceptance, unmapped/alias rejection before mutations, and unchanged HotelRunner behavior. The child-policy fixture now supplies a valid mapping so it still reaches and verifies the unchanged child-policy guard.
- Targeted execution: **89 passed**, Ruff passed. This fix requires deployment before A2 can be retried through the live PMS. No direct database patch, fake provider ACK, external credential extraction or guard bypass was used.

## Plan matrix (all 58 numbered requirements)

`OFFLINE` means related automated checks passed but the specified end-to-end provider result still needs observation. `LIVE` is limited to the named evidence. `GAP` means a demonstrated mismatch. `PENDING` is not a pass.

| Plan ID | Requirement | Current evidence / remaining acceptance |
|---|---|---|
| A1 | Maximum-period availability for all mapped categories, at least two | OFFLINE batch transport; LIVE preview only, provider maximum/readback pending |
| A1.1 | Combine equal values into periods | OFFLINE batch/compiler; actual outbound XML capture pending |
| A1.2 | Bounded batches, not many tiny requests | OFFLINE single transport tests; live request count pending |
| A2 | Force availability for selected dates | LIVE post-deploy Nov10 Standard5/Deluxe5; HTTP200, provider delivery CONFIRMED, provider_verified=true; independent provider calendar readback5/5 |
| A2.1 | Send only specified dates | LIVE same bounded request; Nov11 Standard5/Deluxe6 and Nov12 Standard7/Deluxe7 unchanged against baseline |
| A3 | PMS create then cancel changes availability | OFFLINE lifecycle; full live PMS-origin loop pending |
| A3.1 | Auto-send only changed category/dates on create | OFFLINE delta path; live outbox/provider evidence pending |
| A3.2 | Restore availability on cancellation | OFFLINE stock/lock lifecycle; live readback pending |
| A3.3 | Do not resend unchanged availability | OFFLINE dedup; observe whole live session pending |
| P1 | Maximum period, >=2 rate plans, all categories | OFFLINE rate batch; maximum and live two-plan readback pending |
| P1.1 | Combine equal prices into periods | OFFLINE builder/compiler; live XML pending |
| P1.2 | Bounded price batches | OFFLINE one-transport batch; live counts pending |
| P1.3 | USD currency in XML | OFFLINE currency serialization; live XML/readback pending |
| P2 | Force price upload for a period | OFFLINE rate transport; live send pending |
| P2.1 | Only specified price dates | OFFLINE date bounds; adjacent-day live readback pending |
| P3 | Change one category/rate/period in PMS | OFFLINE scoped rate events; live PMS-origin test pending |
| P3.1 | Automatically send changed prices only | OFFLINE dedup/compiler; live comparison pending |
| P4 | One main-bed adult occupancy only | OFFLINE base amount omits NumberOfGuests; live outbound XML and Exely occupancy interpretation pending |
| C1 | Closed set/unset | OFFLINE boolean Open/Close; live set AND restore pending |
| C2 | MinLOS set/unset | OFFLINE explicit SetMinLOS/RemoveMinLOS, schema-validated; deployment and live set/remove readback pending |
| C3 | MaxLOS set/unset | OFFLINE explicit SetMaxLOS/RemoveMaxLOS, schema-validated; deployment and live set/remove readback pending |
| C4 | CTA set/unset | OFFLINE Arrival Open/Close; live set AND restore pending |
| C5 | CTD set/unset | OFFLINE Departure Open/Close; live set AND restore pending |
| C6 | MinLOSArrival set/unset | OFFLINE ArrivalDateBased + RemoveMinLOS schema validation; deployment and live set/remove readback pending |
| C7 | Automatic restriction deltas only | OFFLINE delta operation preservation; live before/after pending |
| R1 | Two categories, separate guests, comment | LIVE synthetic 1200421110 created/imported; separate guest change and updated comment visible in normal PMS detail; exact ACK/ARI subrequirements pending |
| R1.1 | Regular read, one Reserved ACK with exact IDs/version/PMS number | OFFLINE exact ACK/fencing; new live read+ACK evidence pending |
| R1.2 | Availability for both categories after ACK | OFFLINE publication path; live readback pending |
| R1.3 | Correct category/date/guest per room | OFFLINE room guest regression; new live readback pending |
| R1.4 | Guest comment visible | LIVE updated R9 comment visible in normal Deluxe PMS detail |
| R1.5 | Exely booking number visible | LIVE new 20261110-501694-1200421110 visible in normal PMS detail |
| R1.6 | Total AND every nightly amount equal provider | OFFLINE nightly price regression; new live nightly readback pending |
| R1.7 | Booking source shown as Exely | LIVE normal Deluxe detail and both room list entries show Exely |
| R2 | Two adults and child on main bed | LIVE child case demographics; full bed/payment presentation acceptance pending |
| R2.1 | Adults/children displayed separately | LIVE 2 adults / 1 child / age6, verified PMS readback |
| R2.2 | Provider payment method displayed | OFFLINE PayOnArrival parser; live normal PMS UI pending |
| R3 | Unmapped booking: no create, RequestDenied+message, no ARI; map/redeliver | New OFFLINE Requestdenied+Errors path, no fake PMS ID, exact version, CAS/single write, no ambiguous retry; rollout limited to TEST501694. Live provider acceptance pending. Existing temporary inventory hold remains a documented interpretation gap versus strict no-booking requirement |
| R4 | Two undelivered bookings in one read | OFFLINE parser/lifecycle; two simultaneous new live bookings pending |
| R4.1 | Separate ACK with own IDs/PMS numbers | OFFLINE exact per-version ACK; live two-booking evidence pending |
| R4.2 | Availability for both bookings | OFFLINE publication path; live readback pending |
| R5 | Prepayment + extra service, correct accommodation total | PENDING dedicated live booking; do not charge real money or include extras in accommodation total |
| R6 | Booking originating from a channel | PENDING vendor channel test fixture |
| R6.1 | One guest, multiple days, comment | OFFLINE parser/guest/nights; live channel-origin case pending |
| R6.2 | Liberty Channel name + External UniqueID visible | PENDING Liberty Channel test reservation/access; do not fabricate a channel event |
| R7 | Customer contact modification | LIVE contact name updated in source row and updated email visible in normal PMS detail |
| R8 | Room guest contact modification | LIVE Deluxe guest changed separately; Standard unchanged in provider and PMS lists; normal Deluxe detail verified |
| R9 | Comment modification | LIVE provider and normal PMS detail show R9 COMMENT UPDATED |
| R10 | Extend stay | LIVE Nov11→Nov12 / USD220→USD440 in provider and PMS source row; nightly/ARI subrequirements pending |
| R10.1 | Upload availability for added dates | OFFLINE delta path; actual Exely readback pending |
| R11 | Shorten stay | LIVE Nov12→Nov11 / USD440→USD220 in provider and PMS source row |
| R11.1 | Upload availability for removed dates | OFFLINE delta path; actual Exely readback pending |
| R12 | Change room category | BLOCKED in this QA booking: provider says no available replacement rooms; no category mutation |
| R12.1 | Availability for old AND new categories | OFFLINE changed-room events; actual Exely readback pending |
| R13 | One ACK/new modification version, no duplicate PMS booking | OFFLINE concurrency/replay/ACK tests; live per-version evidence pending |
| R14 | Cancel all rooms | LIVE final remaining-room cancellation reached cancelled/cancellation_done after R15; independent all-two-rooms-at-once case still pending |
| R14.1 | Restore all rooms' availability | OFFLINE lock cleanup; actual Exely readback pending |
| R15 | Cancel one room of two | LIVE Deluxe removed in provider, Standard USD100 retained; PMS source total USD100; per-room cancelled status pending |
| R15.1 | Restore only cancelled room's availability | OFFLINE active-slot behavior; actual Exely readback pending |

## Concrete execution prerequisites, not certification passes

1. Clarify the UI's Exely broadcast target before publishing any one-year write; `selected_channel_codes=[]` is a HotelRunner concept, while backend Exely broadcasting does not require OTA channel selection. Never count a misleading PMS-only preview as a provider delivery.
2. Validate the new R3 negative ACK/redelivery path with Exely; resolve the retained temporary inventory hold's interpretation against the strict no-booking requirement. Do not manually send a fake Reserved ACK or silently count HOLD as compliant.
3. Deploy and validate the explicit MinLOS/MaxLOS/MinLOSArrival removal commands with provider evidence. Offline WSDL-valid XML is not provider acceptance.
4. For each new QA booking, prepare synthetic details and obtain action-time approval for the booking terms before final Book. Do not reuse the prior single-booking consent for new bookings.
5. Coordinate a genuine Liberty Channel test booking and redelivery fixture with Exely; no external email or message was sent by this execution.
6. Preserve baseline dates/rates/inventory/restrictions and gather both durable delivery evidence and provider-side readback for every mutation. Test restoration separately.

Conclusion: **NOT CERTIFIED / execution incomplete**. Offline results are green; the full supplied provider test plan has not passed.

## Post-merge deployment and bounded A2 verification

- PR1390 merged as `23c705a66712875147163828d9fe6dfdd7e99772`. Deploy run `39848642838` completed successfully for that exact revision.
- Reloaded normal PMS UI and verified the updated Exely broadcast explanation. Repeated only Nov10 availability5 for Standard and Deluxe (six mapped plan cells), without rates, restrictions, Suite or agencies. Three same-value submissions were made while obtaining durable response evidence; do not count these as three independent certification cases.
- Inspected the final normal UI request's Response tab: HTTP200, saved6, provider exely, channel_push_count2, delivery_state CONFIRMED, task_count2, provider_verified true, provider_write_count1, error_codes[], agency_push_count0. HTTP200 alone was not treated as confirmation.
- Independently opened TEST501694's Exely stock calendar: Nov10 PMS and online availability Standard5/Deluxe5; Nov11 Standard5/Deluxe6; Nov12 Standard7/Deluxe7. Suite remained1 throughout. Adjacent dates matched the pre-write baseline. Same-value resend demonstrates acceptance/readback, not a reservation-driven stock delta or restoration test.
- Evidence: `/private/tmp/syroce-exely-certification-20261022/postdeploy-a2-confirmed.png` and `provider-stock-postdeploy.png` in the same directory.
- Other outstanding rows, especially R3 RequestDenied, LOS removal and genuine channel-origin test, remain incomplete. This deployment is not full Exely certification.

## 2026-10-23 follow-up implementation (not yet deployed)

- Added explicit LOS removal controls to the Exely editor. Zero is a clear command, blank remains no change; the preview explicitly names each removal. SOAP serializes RemoveMinLOS/RemoveMaxLOS with no Time attribute, never SetMinLOS Time=0; arrival-based removal keeps ArrivalDateBased=true. Requests validate against the checked-in vendor WSDL in tests.
- Exely validation accepts explicit zero for LOS; negatives, booleans and fractional values remain rejected. Unified preflight rejects removal for HotelRunner, agencies, or mixed agency targets before local calendar writes. A positive maximum must still be >= a positive minimum; clearing maximum is not a false min/max conflict.
- Added a separate per-version mapping-rejection state machine. Missing room/rate mappings can send Requestdenied with an informative root Errors message and exact provider identity/version, without Success or a fabricated PMS confirmation. Negative ACK and successful Reserved delivery ACK remain distinct.
- Mapping replay and rejection compete through an atomic processing-state claim. A timeout or crash after claiming is never blindly retried; ambiguous results block local replay for reconciliation. Confirmed no-network failures can be retried. A successfully rejected version can be mapped/replayed normally, still requiring durable PMS readback before Reserved ACK.
- **Rollout safety:** automatic negative ACK is enabled only for property501694 on the exact allowlisted Exely TEST endpoint. Production hotels retain their previous behavior until TEST/provider acceptance. Runtime, quota, TLS and dry-run protections are unchanged.
- Existing temporary unmatched inventory holds/alarms are retained, not deleted or counted as imported bookings. This is deliberately not claimed to satisfy a literal requirement for no booking/hold record. No live new negative ACK or restriction-removal request has been sent by this implementation step.
- Verification: **459 backend tests passed**, **30 frontend tests passed**; targeted ESLint/Ruff and the production frontend build passed. One pre-existing datetime.utcnow() warning remains. The prior test rejecting min_los=0 now checks negative/boolean rejection; dedicated wire tests verify zero sends Remove rather than weakening validation silently. Strict integer request types prevent false from being coerced into a clear command.

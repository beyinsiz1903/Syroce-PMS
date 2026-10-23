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
| P2 | Force price upload for a period | PASS bounded LIVE Standard/Base USD Nov10:100→101→100; normal confirmed delivery and independent Exely readback each way |
| P2.1 | Only specified price dates | PASS bounded LIVE same price test: Nov9 remained empty, Nov11/12 remained100; other occupancy/child rows unchanged in observed Standard/Base calendar |
| P3 | Change one category/rate/period in PMS | OFFLINE scoped rate events; live PMS-origin test pending |
| P3.1 | Automatically send changed prices only | OFFLINE dedup/compiler; live comparison pending |
| P4 | One main-bed adult occupancy only | OFFLINE base amount omits NumberOfGuests; live outbound XML and Exely occupancy interpretation pending |
| C1 | Closed set/unset | PASS bounded LIVE Nov10 Standard/Base open → closed → open; both deliveries CONFIRMED and independently read back in Exely; Nov9/11 remained open |
| C2 | MinLOS set/unset | LIVE TEST501694 Standard/Base USD Nov10: 1 → 2 → removed (—) → restored1; each normal PMS delivery confirmed and independently read back in Exely; Nov9/11 remained1 |
| C3 | MaxLOS set/unset | LIVE TEST501694 Standard/Base Nov10 empty → 3 → empty; confirmed deliveries and independent provider readback, Nov9/11 unchanged; original state restored |
| C4 | CTA set/unset | LIVE bounded Nov10 open → closed → open, paired with CTD in each request; separate Exely tab readback, Nov9/11 unchanged |
| C5 | CTD set/unset | LIVE bounded Nov10 open → closed → open, paired with CTA in each request; separate Exely tab readback, Nov9/11 unchanged |
| C6 | MinLOSArrival set/unset | LIVE TEST501694 Standard/Base USD Nov10: empty (—) → 2 → empty (—); both deliveries confirmed and independently read back, Nov9/11 remained empty |
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
| R3 | Unmapped booking: no create, RequestDenied+message, no ARI; map/redeliver | LIVE 1200421158: pending_mapping + explicit rejection-sent/no-PMS-ACK UI; added only Suite/Dynamic mapping, normal pull changed same source to imported/150 USD. Exact wire ACK count/no-ARI evidence still pending. Existing temporary inventory hold remains a documented interpretation gap versus strict no-booking requirement |
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
3. MinLOS set/remove/restore is live-verified below. Validate MaxLOS/MinLOSArrival separately with provider evidence; MinLOS success does not certify these other commands.
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

## 2026-10-23 follow-up implementation (deployed via PR1391)

- Added explicit LOS removal controls to the Exely editor. Zero is a clear command, blank remains no change; the preview explicitly names each removal. SOAP serializes RemoveMinLOS/RemoveMaxLOS with no Time attribute, never SetMinLOS Time=0; arrival-based removal keeps ArrivalDateBased=true. Requests validate against the checked-in vendor WSDL in tests.
- Exely validation accepts explicit zero for LOS; negatives, booleans and fractional values remain rejected. Unified preflight rejects removal for HotelRunner, agencies, or mixed agency targets before local calendar writes. A positive maximum must still be >= a positive minimum; clearing maximum is not a false min/max conflict.
- Added a separate per-version mapping-rejection state machine. Missing room/rate mappings can send Requestdenied with an informative root Errors message and exact provider identity/version, without Success or a fabricated PMS confirmation. Negative ACK and successful Reserved delivery ACK remain distinct.
- Mapping replay and rejection compete through an atomic processing-state claim. A timeout or crash after claiming is never blindly retried; ambiguous results block local replay for reconciliation. Confirmed no-network failures can be retried. A successfully rejected version can be mapped/replayed normally, still requiring durable PMS readback before Reserved ACK.
- **Rollout safety:** automatic negative ACK is enabled only for property501694 on the exact allowlisted Exely TEST endpoint. Production hotels retain their previous behavior until TEST/provider acceptance. Runtime, quota, TLS and dry-run protections are unchanged.
- Existing temporary unmatched inventory holds/alarms are retained, not deleted or counted as imported bookings. This is deliberately not claimed to satisfy a literal requirement for no booking/hold record. No live new negative ACK or restriction-removal request has been sent by this implementation step.
- Verification: **459 backend tests passed**, **30 frontend tests passed**; targeted ESLint/Ruff and the production frontend build passed. One pre-existing datetime.utcnow() warning remains. The prior test rejecting min_los=0 now checks negative/boolean rejection; dedicated wire tests verify zero sends Remove rather than weakening validation silently. Strict integer request types prevent false from being coerced into a clear command.

## PR1391 post-deploy live MinLOS verification

- PR1391 merged as `b211338496f834e5613d0f1b615776953835ab1d`. Exact-revision Deploy to Droplet runs `39880300479` and `39879128970`, Frontend Quality Gates `39878147367`, and CI/CD `39878147294` succeeded.
- Scope: TEST501694 only, Standard panel5003299 / Base rate USD panel10009740, **2026-11-10 only**. No other room, plan, rate, inventory or agency target selected.
- Independent Exely baseline: Nov9=1, Nov10=1, Nov11=1. Sent MinLOS2 via normal PMS preview/confirmation; response HTTP200, saved1, delivery CONFIRMED, provider_verified=true, provider_write_count1, error_codes[]. Reloaded Exely: Nov10=2, Nov9/11=1.
- Clicked the explicit remove control, preview named the minimum-stay removal, and sent once. Same confirmed delivery fields. Reloaded Exely independently: **Nov10=—**, Nov9/11=1. This is an actual removed restriction, not SetMinLOS Time=0.
- Restored original MinLOS1 once via normal PMS confirmation. Same confirmed delivery fields. Reloaded Exely independently: **Nov9=1, Nov10=1, Nov11=1**. Test mutation restored successfully.
- Evidence directory: `/private/tmp/syroce-exely-certification-20261022/`; files `minlos-baseline.png`, `minlos-set-confirmed.png`, `minlos-provider-set2.png`, `minlos-remove-response.png`, `minlos-provider-removed.png`, `minlos-restore-response.png`, `minlos-provider-restored.png`.
- This passes the bounded C2 set/unset cycle only. MaxLOS, arrival-based MinLOS, R3 provider rejection/redelivery, other pending rows and full certification remain incomplete. No new negative ACK was sent during this cycle.

## Subsequent live C6 and C3 execution

- Same bounded scope: TEST501694 Standard/Base USD, Nov10 only, no agencies, rates or inventory changes.
- **C6 passed:** independent MinLOSArrival baseline Nov9/10/11 all empty (—). Sent2 once, normal response CONFIRMED/provider_verified=true/write_count1/error_codes[], independently reloaded Exely Nov10=2 with Nov9/11 unchanged. Explicit removal sent once with the same confirmed response; independently reloaded Exely Nov9/10/11 all empty (—). Original state restored. Evidence: `minlos-arrival-baseline.png`, `minlos-arrival-set-response.png`, `minlos-arrival-provider-set2.png`, `minlos-arrival-remove-response.png`, `minlos-arrival-provider-restored.png` in the same proof directory.
- **C3 in progress:** enabled MaxLOS calendar visibility (view preference only). Baseline Nov9/10/11 all empty. Sent3 once; response CONFIRMED/provider_verified=true/write_count1/error_codes[]. Independent provider reload showed Nov10=3, Nov9/11 empty. Evidence: `maxlos-baseline.png`, `maxlos-set-response.png`, `maxlos-provider-set3.png`.
- Explicit MaxLOS removal sent once and HTTP200 observed. Mac locked immediately before inspecting the response details and final provider calendar. Do not resend blindly: first inspect current normal request response and reload MaxLOS view. Restoration is **not yet verified**. No other restriction was changed.

## Resume after unlock: C3 completion and C4/C5 live verification

- Did not repeat the MaxLOS removal. Inspected its original normal request Response: CONFIRMED/provider_verified=true/provider_write_count1/error_codes[]. Independently read Exely MaxLOS Nov9/10/11 all empty. **C3 restoration verified.** Evidence: `maxlos-remove-response.png`, `maxlos-provider-restored.png`.
- Enabled CTA/CTD calendar visibility (display preference only). Exely Standard/Base Nov9/10/11 initially showed open ticks for both restrictions; saved `cta-baseline.png` and `ctd-baseline.png`.
- Sent **CTA=true and CTD=true together in one normal request**, TEST501694, Standard/Base only, Nov10 only, no rate/inventory/LOS/agency changes. Response CONFIRMED/provider_verified=true/provider_write_count1/error_codes[]. Reloaded provider, opened each restriction tab separately: Nov10 red closed cross, Nov9/11 open ticks. Evidence: `cta-ctd-close-response.png`, `cta-provider-closed.png`, `ctd-provider-closed.png`.
- Sent CTA=false and CTD=false together once, same scope. Response CONFIRMED/provider_verified=true/provider_write_count1/error_codes[]. Independently reloaded Exely, inspected CTA and CTD tabs separately: Nov9/10/11 all open ticks again. Original state restored. Evidence: `cta-ctd-restore-response.png`, `cta-provider-restored.png`, `ctd-provider-restored.png`.
- These bounded paired-field cycles establish C4/C5 transmission, provider readback and restoration, not isolation between CTA and CTD under separate requests or all certification scenarios. Full certification remains incomplete; R3 rejection/redelivery and other pending rows are unchanged.

## Subsequent live C1 execution

- TEST501694 Standard/Base USD Nov10 only. Baseline Exely Close/Open calendar showed open ticks on Nov9/10/11. Evidence `closed-baseline.png`.
- Sent only closed=true through normal PMS preview and confirmation, with no other fields/agencies/plans/rooms selected. Response CONFIRMED/provider_verified=true/provider_write_count1/error_codes[]. Independent Exely reload showed Nov10 closed (red cross and pink date), Nov9/11 open. Evidence `closed-set-response.png`, `closed-provider-set.png`.
- Sent closed=false once, same bounded scope. Inspected original response: CONFIRMED/provider_verified=true/provider_write_count1/error_codes[]. Saved `closed-restore-response.png`. Reloaded Exely and selected Close/Open, enabled accessibility, scrolled toward Nov2026; Mac locked before the final screenshot. Do not resend: reopen delivery is confirmed, but final independent provider restoration readback is still pending. No new reservation/negative ACK was created during this cycle.
- After unlock, independently inspected the refreshed Exely Close/Open calendar: Standard/Base Nov10 is open (check mark), and Nov9/11 remain open. Saved `closed-provider-restored.png`. C1 bounded cycle is complete and restored without resending the reopen request.

## Subsequent live R3 execution

- User explicitly approved the new Suite/Dynamic synthetic booking, Nov10–11, 150 USD, pay-now 0, including terms/data-processing consent. Created once: `20261110-501694-1200421158`, customer CertMapping SyntheticTest; marketing consent remained off. Provider confirmation saved as `r3-booking-created.png`.
- Normal PMS TEST501694 pull showed this exact source, dates and 150 USD as `pending_mapping`, with “Eksik eşleşme Exely’ye bildirildi; PMS teslim onayı verilmedi.” Saved `r3-negative-ack-sent.png`. This is live UI evidence of the deployed rejection path; it does not independently prove exact SOAP wire counts or absence of all ARI.
- Verified Suite/Dynamic was absent. Added only Suite panel5003301/plan10009738, API5001576/10003541, PMS Suite. Availability synchronization remained OFF; R/I on as with other Suite plans. Existing eight mappings were preserved. Saved `r3-suite-dynamic-mapping.png`.
- Next normal provider pull changed the same reservation source to `imported`, total still150 USD, without using the manual PMS import button. Saved `r3-redelivery-imported.png`. Strict no-booking/temporary-hold interpretation, detailed PMS row contents and exact ACK/no-ARI trace remain to be checked; do not mark the full R3 requirement certified from the list alone.
- Subsequent normal PMS reservation detail independently verified source number1200421158, Exely, Suite, Nov10–11/one night, four adults/zero children, accommodation150 USD, collected0 USD and remaining150 USD. Physical room is unassigned (not a failed room-category mapping). Saved `r3-normal-pms-detail.png`. Exact ACK/no-ARI and retained HOLD interpretation remain open.

## Subsequent bounded P2 price execution

- TEST501694 Standard/Base USD only, Nov10 only, price field only, no inventory/restrictions/agencies. Independent provider baseline: Nov9 empty, Nov10=100, Nov11=100, Nov12=100; only two-main-bed-adult row priced, other occupancy/child rows empty. Saved `p2-price-baseline.png`.
- Set101 once using normal PMS preview/confirmation. Original Response: CONFIRMED, provider_verified=true, write_count1, error_codes[], agency_push_count0. Reloaded Exely independently: Nov10=101, Nov9 empty, Nov11/12=100. Saved `p2-price-set-response.png`, `p2-price-provider101.png`.
- Sent restore100 once through the same bounded form. Final response/provider restoration readback pending; do not resend blindly.
- Inspected original restore response: CONFIRMED/provider_verified=true/write_count1/error_codes[], agency_push_count0. Fresh Exely reload independently showed Nov10 back100, Nov9 empty, Nov11/12 still100, other displayed occupancy/child rows empty. Saved `p2-price-restore-response.png`, `p2-price-provider-restored.png`. P2/P2.1 bounded cycle passed and original price restored; no duplicate resend.

## Acceptance count after bounded P2

- 58 numbered acceptance requirements, including subrequirements. 18 have completed bounded live evidence: A2, A2.1, P2, P2.1, C1–C6, R1.4, R1.5, R1.7, R2.1, R7, R8, R9, R11. CTA/CTD evidence is a paired-field cycle, not independent isolation.
- 40 remain incomplete (some partially exercised). This is not40 discovered defects or40 untouched flows. Wire/request-count evidence, full automatic stock-delta cycles, maximum horizons, strict R3 HOLD interpretation, independent group cancellation and genuine channel fixture are still open. Full certification is not complete.

## Risk-first failure testing (user requested pivot)

- Stopped repeating near-identical successful live writes. Ran targeted offline lifecycle, concurrency, duplicate fencing, demographics, restriction validation, ARI failure, quota and production-safety suites with synthetic credentials, localhost DB and external dry-run enabled. No live hotel or Exely writes were made in this phase.
- Added six permutation cases: after a two-room durable create, modification / partial cancellation / full cancellation arrive in every possible order, then all repeat in reverse order. Assertions require the original booking IDs only, both rooms cancelled, and the newest cancellation version retained. All six passed: delayed or duplicate changes did not resurrect cancelled rooms.
- Existing exercised failure paths include ten competing workers, lease expiry/old-worker fencing, write-before-crash replay, ambiguous ACK timeout/no blind retry, cancellation lock cleanup failure blocking ACK, missing room/rate mapping, stale/wrong-tenant ACK, changing REST snapshots, currency/amount/age mismatches, negative/fractional/boolean restriction inputs, quota refusal and kill switches.
- Results:241 passed in eight targeted files. Two additional real-Mongo demographics CAS/tenant-isolation parameter cases initially could not connect under the sandbox; re-run with localhost access passed2/2. Total **243 passed**, no assertion failures. The existing cache-warmer `datetime.utcnow()` deprecation warning remains. Ruff and `git diff --check` passed.
- Evidence: `failure-stress-results.xml` records241 passes and the two initial infrastructure errors; `failure-stress-mongo-results.xml` records their successful2/2 re-run. Do not present the initial XML alone as a clean243-pass run.
- This does not complete the40 remaining live acceptance items. The strict R3 requirement versus retained temporary HOLD remains a known open interpretation/design gap, not disproved by these passing tests. New test code is local, not yet submitted/deployed.

## Follow-up code correction: mapping review without synthetic PMS bookings

- Confirmed that unmatched sentinel locks never reserved real rooms. The synthetic PMS hold booking could nevertheless appear in booking lists/reports. Removed new synthetic holds from Exely lifecycle, legacy provider ingestion, unified mapping-review pipeline and import/replay bridge for Exely and HotelRunner. The durable provider/review record and tenant emergency notification remain required; no successful PMS delivery ACK is invented.
- The shared helper now supports explicit alert-only mode. It touches neither bookings nor room-night locks in that mode; notification text states no PMS reservation/stock lock was created and links to the matching provider page. The legacy helper default remains available for old explicit callers. Existing holds are not mass-deleted: normal successful replay/cancellation still performs safe legacy release, including physical-room assignment recovery.
- New tests exercise both providers' alert-only helper against local MongoDB, idempotent notification, zero bookings/locks, alarm failure, Exely real helper integration and HotelRunner review/replay without a hold ID. Updated the import-bridge acceptance assertion to zero PMS bookings rather than expecting the old synthetic hold. Fixed test isolation to clean its own leftover locks/notifications before checking zero writes.
- Final combined targeted verification: **302 passed,1 pre-existing skipped** (explicitly skipped `test_hotelrunner_import_projects_provider_note_into_existing_notes_collection`, record-not-claimable CI flake), plus **3 HotelRunner catchup/dedup tests passed** separately. New code Ruff and diff checks passed. `test_import_bridge.py` retains pre-existing unrelated import-order/UTC lint findings; no new findings were introduced in the changed assertion block.
- Evidence: `final-alert-only-both-providers.xml`, `hotelrunner-alert-catchup-results.xml` under the proof directory. All DB runs used localhost and synthetic test tenants, external dry-run on. No live provider/hotel write, legacy data purge, PR or deploy was performed for this code correction yet. R3's no-new-PMS-booking gap is addressed in code; deployment and live validation remain outstanding. The18/58 bounded-live count is unchanged.
- PR preparation: rebased the correction alone onto merged main (no repeated PR1391 commits). Mechanically fixed the touched import-bridge test file's existing import ordering and UTC alias findings; all changed Python files now pass Ruff.

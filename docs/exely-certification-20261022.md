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
| R1.6 | Total AND every nightly amount equal provider | Follow-up fixes nonuniform embedded Exely nightly-price readback/posting; targeted offline evidence passes; deployment and new provider/PMS comparison pending |
| R1.7 | Booking source shown as Exely | LIVE normal Deluxe detail and both room list entries show Exely |
| R2 | Two adults and child on main bed | LIVE child case demographics; full bed/payment presentation acceptance pending |
| R2.1 | Adults/children displayed separately | LIVE 2 adults / 1 child / age6, verified PMS readback |
| R2.2 | Provider payment method displayed | Follow-up adds explicit provider payment-instruction display separately from PMS receipts; deployment and live UI acceptance pending |
| R3 | Unmapped booking: no create, RequestDenied+message, no ARI; map/redeliver | LIVE 1200421158 rejection/redelivery predates alert-only fix. New synthetic PMS holds were removed by deployed PR1392; new alert-only live fixture and exact wire ACK/no-ARI proof remain pending |
| R4 | Two undelivered bookings in one read | OFFLINE parser/lifecycle; two simultaneous new live bookings pending |
| R4.1 | Separate ACK with own IDs/PMS numbers | OFFLINE exact per-version ACK; live two-booking evidence pending |
| R4.2 | Availability for both bookings | OFFLINE publication path; live readback pending |
| R5 | Prepayment + extra service, correct accommodation total | Offline room-total/prepayment isolation, including explicit zero-price accommodation, covered by follow-up. Dedicated provider fixture still pending; no real payment authorized |
| R6 | Booking originating from a channel | PENDING vendor channel test fixture |
| R6.1 | One guest, multiple days, comment | OFFLINE parser/guest/nights; live channel-origin case pending |
| R6.2 | Liberty Channel name + External UniqueID visible | Follow-up fixes CompanyName child parsing and separates External from PMSConnect IDs through import/display; genuine Liberty Channel fixture and live acceptance still pending |
| R7 | Customer contact modification | LIVE contact name updated in source row and updated email visible in normal PMS detail |
| R8 | Room guest contact modification | LIVE Deluxe guest changed separately; Standard unchanged in provider and PMS lists; normal Deluxe detail verified |
| R9 | Comment modification | LIVE provider and normal PMS detail show R9 COMMENT UPDATED |
| R10 | Extend stay | LIVE Nov11→Nov12 / USD220→USD440 in provider and PMS source row; nightly/ARI subrequirements pending |
| R10.1 | Upload availability for added dates | OFFLINE delta path; actual Exely readback pending |
| R11 | Shorten stay | LIVE Nov12→Nov11 / USD440→USD220 in provider and PMS source row |
| R11.1 | Upload availability for removed dates | OFFLINE delta path; actual Exely readback pending |
| R12 | Change room category | BLOCKED in this QA booking: provider says no available replacement rooms; no category mutation |
| R12.1 | Availability for old AND new categories | OFFLINE changed-room events; actual Exely readback pending |
| R13 | One ACK/new modification version, no duplicate PMS booking | PASS bounded historical LIVE: provider's downloaded1200421110 log has8 distinct versions,8 successful ACK requests/responses (one per version),9 reads including one repeated first version; normal PMS full-history list contains exactly the two expected room slots. This is not a new PR1444 execution. Primary wire IDs are masked, so R1.1 exact-ID proof remains pending |
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

## PR1392 deployment and risk-first follow-up

- PR1392 merged as `2d6a001ed2e97acef1b8010a523115a4c2a58587`. Exact-revision Deploy to Droplet runs `39919722013` and `39918241294`, Frontend Quality Gates `39917574621` and CI/CD `39917574622` succeeded. Final combined pre-PR backend run was305 passed,1 pre-existing skipped, with the pre-existing cache-warmer warning. This supersedes the earlier separate302+3 reporting, not an additional305 tests.
- After deploy, a normal TEST501694 reservation pull still displayed the same six source records; cancelled1200421110 remained cancelled. No extra source row was visible. This is UI-level repeat-pull evidence, not an exact database or SOAP ACK-count audit. Evidence: `post1392-repeat-source-list.png`.
- Live UI preflight rejected MinLOS3/MaxLOS2 and fractional MinLOS1.5/MaxLOS2 for Standard/Base, Nov10 only, with the publish button disabled. No publish/confirmation was submitted and no provider write was initiated. These are UI validation checks, not live API rejection proofs. The form was reset. Evidence: `post1392-invalid-min-max-blocked.png`, `post1392-fractional-los-blocked.png`.
- Inspected the existing unmapped Mixed plan (panel10009737, USD). It combines Non-ref and Base. Reached settings through the provider's sale-check panel and opened its own QA link. Independent one-night Nov10–11 and two-night Nov10–12 searches explicitly reported this plan unavailable, while suggesting other plans. No booking was created and no plan/mapping/price/stock setting was saved. Evidence: `post1392-mixed-rate-unavailable.png` (one-night result). Do not use the alternative room suggestions as proof of Mixed availability. Post-deploy alert-only live R3 and exact ACK/no-ARI verification remain open; active mappings were not removed to force a failure.

## Follow-up grid boundary defect (local correction, not deployed)

- Found a separate real availability-display defect: `_build_dates` includes the last date, but `_get_active_bookings` queried arrivals strictly before that date. An arrival on the final night was omitted, including in a single-night grid. This shared helper affects the Exely, HotelRunner and agency grid builders; no provider-side inventory corruption is claimed from this finding.
- Added four regression variants (single/multi-day grid, date-only/timestamp-shaped arrival). All four failed before the correction (the existing two occupancy-index tests passed). Extended the final suite to eight regression variants with month/year rollover. Changed only the arrival upper bound to the next day's exclusive ISO date, preserving tenant/status/checkout filters and projection. The final displayed night now counts the arrival, with next-day arrivals and already-departed stays excluded.
- Targeted offline verification after the fix:46 passed across grid occupancy, unified fail-closed delivery, and Exely restriction-removal tests. Changed Python files passed Ruff. Tests used synthetic tenant data/mocked database access, localhost configuration and external dry-run enabled; no production/provider write. Evidence: `grid-inclusive-boundary-results.xml`. This does not increment the18/58 bounded-live acceptance count. Code awaits PR/merge/deploy and independent live readback.

## PR1393 deployment and exact-date calendar follow-up

- PR1393 merged as `4af0240463f1e24656484bb0ca79bdb49204bf6c`. Exact-revision deploy runs39928112554 and39926478683, frontend quality39925656657 and CI/CD39925656643 all succeeded. Fresh live read-only Standard calendar displayed Nov10/11 with1 sold each and USD prices. No provider or reservation changes were submitted. Evidence: `pr1393-postdeploy-standard-grid.png`. This is a smoke check, not an end-boundary proof: the normal UI ended Nov12, without an independently established arrival on that final date.
- Added explicit start/end date inputs and an apply button to the read-only calendar. Single-day views are allowed; draft edits do not issue requests until applied. Week navigation resynchronizes the drafts. The UI explicitly states that this does not update price, stock or channels. Invalid/reversed/over366-inclusive-day requests are rejected; the GET endpoint performs the same bounded validation before provider detection or database reads. This read limit does not change ARI write horizons or send any provider updates.
- Local synthetic component preview (no API connection) verified a single Nov10 column and rejection of Nov11–10 without replacing the loaded Nov10 table. Evidence: `calendar-date-range-single-day-local.png`, `calendar-date-range-invalid-local.png`. Temporary QA files/server were removed/stopped afterward. Do not present its synthetic counts as live database evidence.
- Initial targeted results:15 frontend and73 backend tests passed; changed-file ESLint/Ruff and production frontend build passed. Exact live date-boundary readback still requires this UI change to be merged/deployed. The18/58 bounded-live count remains unchanged; full Exely certification is incomplete.
- Expanded final regression:45 frontend tests across9 files;353 backend tests passed,1 pre-existing skip and1 pre-existing cache-warmer deprecation warning. Initial15/73 are subsets, not additional counts. Backend evidence: `calendar-date-range-combined-results.xml`. No live provider access or financial/reservation mutation.

## PR1394 live date acceptance and unassigned-room follow-up

- PR1394 merged as `f89840da02d99413f527cfc25b3c945e00e4ff36`. Exact-revision deploy runs39939017961 and39937905090, frontend quality39937072832 and CI/CD39937072820 all succeeded. Reloaded TEST501694. Standard on Nov10 as the final day of Nov9–10 and as a single Nov10–10 view showed the same Base100 USD, availability4/sold1; Non-ref100 USD/4/sold1; Dynamic4/sold1. This is live grid-level acceptance of the last-day and single-day correction, not an independent reservation-ID/ACK or provider stock-delta reconciliation. Evidence: `pr1394-live-last-day-nov10.png`, `pr1394-live-single-day-nov10.png`. No mutation was submitted.
- Next risk-first code review found that Exely's normal booking builder writes confirmed reservations with `room_id=None` and a mapped `room_type`, but the grid query projected out `room_type` and the occupancy index counted physical room IDs only. Confirmed, unassigned category reservations therefore disappeared from the grid's sold count. This is a grid defect; no claim is made that a particular outbound provider quota was over-sold.
- Corrected the read projection to retain room_type and both grid counting paths to fall back to an exact known PMS category if no known physical assignment exists. A real physical assignment wins over stale category text and counts only once. Missing/unknown categories are not guessed; existing tenant/active-status/date filters are preserved. No booking, assignment, lock, provider quota, rate or financial record is modified.
- Six new unassigned/placeholder variants failed before the fix. Additional tests protect checkout-exclusive nights, cross-category separation, no double-count after assignment, unknown categories and the actual Exely `_booking_fields` output through the real grid projection. Combined verification:362 backend tests passed,1 pre-existing skip and1 pre-existing cache-warmer warning; changed-file Ruff and diff checks passed. External dry-run/local synthetic data only. Evidence: `unassigned-grid-combined-results.xml`.
- Current live Nov10 baseline (before this new correction): Standard displays1 sold; Deluxe and Suite display no sold badge. Saved `unassigned-grid-live-before.png`. Do not infer exact expected after-counts without reconciling actual active booking rows. New correction awaits PR/merge/deploy and live category/assignment comparison. The18/58 bounded-live certification count remains unchanged.

## Reservation history loading follow-up

- PR1395 exact-revision deployment succeeded. Scoped read-only grid/night-boundary checks matched independently inspected unassigned category reservations. Detailed business records remain in local evidence; the public PR note contains technical conclusions only. This is bounded grid acceptance, not full provider certification.
- Confirmed a separate UI ownership race: operational bootstrap/refresh writes the shared bookings state after an independent full-history request, and the history-loaded flag then prevents reloading. Direct Bookings entry or refresh could therefore leave a narrow date-window list presented as all history.
- Full history now has independent state and pagination ownership. Operational room/front-desk date-window refreshes cannot replace it. The reservation list and its counters use the same complete history; manual/background refresh also refreshes an already-requested history workspace. Loading/error/retry states are explicit, with the last complete list preserved on refresh failure. No partial pagination run is published.
- Request generations ignore stale responses and unmounted/previous-scope requests. Tenant/user scope masks old rows immediately; delayed callbacks from a previous scope cannot start a new request. Repeated full pages fail closed instead of looping or duplicating totals, and overlapping page IDs are deduplicated. API write permissions, booking/financial data and provider behavior are unchanged.
- Verification:66 frontend tests passed across14 files, including direct-entry bootstrap/history ordering, manual refresh, stale refresh, pagination beyond the first page, later-page failure, malformed payload, repeated/overlapping pages, scope changes, and visible retry/loading controls. Changed-file ESLint and production build passed. Tests use mocked synthetic data; no live record was modified. Deployment/live direct-entry and refresh acceptance for this new correction remain pending. The18/58 bounded-live count is unchanged.

## 2026-10-27 remaining-acceptance audit and source-contract corrections

The complete three-page supplied test plan was re-read, including rendered pages. The supplied PMSConnect 1.17.1 specification pp.72,93,96–99 was checked for identity, channel and payment semantics. These are contract corrections, not new provider certification passes.

Read-only TEST501694 checks on the current deployed revision verified ARI and scheduled imports remain disabled, six provider inbox records remain present, zero pending events and zero errors in the last24 hours. One historical error is preserved. No archived Demo reservations were restored; no provider writes, new booking terms, real payments, day closing or other property operations were performed.

Confirmed defects and bounded fixes:

- The parser previously iterated all descendant UniqueID nodes and overwrote its delivery identity with the last Type14, including External or nested profile IDs. It now selects only direct PMSConnect/empty-context reservation IDs, preserves External references separately, and rejects conflicting provider identities without exposing them in error messages. No ACK is manufactured or manually retried.
- OTA BookingChannel uses a CompanyName child, not the attribute previously read. The actual channel name/code and external references now survive normalization, durable current-row storage and each PMS room booking. Integration provenance stays Exely. A genuine channel fixture is still needed; synthetic Liberty Channel strings are not evidence of a provider event.
- The guest detail now separates Exely/channel references and raw provider payment instructions from actual PMS receipts. PayOnArrival, a card guarantee or provider prepayment is not counted as collected PMS money.
- A valid nonuniform Exely source plan (90+130) was displayed as an evenly allocated110+110 when the separate PMS daily-rate collection was empty. Detail readback and the shared room-charge calculator now use only a complete, finite, nonnegative, cent-exact plan that reconciles to the room's accommodation total. Existing explicit PMS rates and migration cutover protection win. Invalid, duplicate, out-of-stay, incomplete or changed-total plans are not labelled source prices. This does not rewrite any historical charge/tax or source version.
- An explicitly zero-price room is no longer replaced by the group's nonzero total, which may include an extra service. Provider deposits never become a fabricated PMS receipt.

Verification:348 selected backend tests passed, including real isolated localhost-replica demographics/tenant-CAS cases and parse→normalize→durable import→single exact-ID ACK (provider mocked). Frontend full run:2214 passed, zero failures/errors. Production frontend build, changed-file Ruff/ESLint and diff checks passed. No CI gate, quarantine or security configuration was weakened.

Local evidence directory is kept outside source control. Initial failing regressions, environment failures and the obsolete mixed live-server/WSSE test run are preserved separately; they are not counted as successful provider acceptance. The isolated replica rerun resolves the two local DB setup failures. The pre-existing cache-warmer UTC deprecation warning remains.

Release prerequisites: merge/deploy this correction normally and independently verify the exact live revision before new provider mutation. Keep the Demo's ARI/scheduler off until a bounded test window and its baseline/restoration are reconciled. Do not repeat the archived test imports or broadcast the Demo's full synthetic room data. Remaining external dependencies include a genuine Liberty Channel booking/redelivery fixture, a no-real-money prepayment+service fixture and Exely's acceptance of maximum horizons/request traces. Every new booking-terms acceptance requires action-time approval; official provider sign-off cannot be fabricated locally.

The bounded-live count remains18/58. None of the40 incomplete requirements has been silently changed to PASS by these offline tests or the local visual preview.

## 2026-10-28 provider-session and safe-outbox follow-up

PR1444 merged and deployed as `ac0b48e1560dab3368abbf02c7d433a136bfe101`. Exact live health matched the merge, both required main workflows succeeded, and actual `Deploy to Server` step succeeded in run40597573839. All15 executed PR checks succeeded; three conditional PR docker/deploy skips were not counted as publication. After the user signed in, Safari independently showed TEST Syroce PMS501694 and its real delivery-history UI; the prior session-expiry blocker is resolved.

R13 has additional independent **historical** evidence, not a new provider mutation: the normal provider export for1200421110 contains9 OTA_ReadRQ/ResRetrieveRS pairs,8 distinct LastModifyDateTime values, and8 OTA_NotifReportRQ/RS pairs. Each source version has exactly one successful ACK; the first version was read twice but ACKed once. Normal tenant-scoped PMS full-history read returned484 bookings, with exactly the expected Standard/Deluxe source slots, both ultimately cancelled; no duplicate third room booking exists in that read. The export masks primary UniqueID values, so it does not prove unmasked exact-ID matching, scheduled cadence, inventory delivery or the entire R1 requirement. Bounded-live progress is now **19/58**; the39 remaining requirements are not39 demonstrated defects.

Read-only live baseline, Nov10/11/12: provider PMS/online availability Standard5/5/7, Deluxe5/6/7, Suite0/1/1. The earlier Suite1 baseline must not be blindly restored. Provider payment inventory exposes check-in, a TEST bank-card method and card-guarantee methods; merely listing them does not satisfy R2.2/R5 and no real/test payment was executed. No rates, inventory, bookings, ACKs, financial sources, archived Demo records or business date were changed.

Before enabling a bounded ARI window, the existing tenant-scoped ops monitor revealed32 pending/stuck and52 failed historical outbox events for Demo. These are the general outbox counts, **not** the six-record Exely inbox (which still has0 pending and0 last24h errors). Failed-event type breakdown:49 booking.created.v1,1 booking.cancelled.v1,2 agency.inventory.availability.updated.v1. Their recorded error codes are50 exely_room_mapping_missing and2 hotelrunner_room_mapping_missing; these are historical errors, not proof every mapping is still missing. Current normal API reads show31 rooms across7 exact type strings (including the preserved lowercase test room),10 Exely mapping rows, only Standard/Base and Deluxe/Base availability owners, no Suite availability owner, and no mappings for Superior/Junior Suite/Family. Unlike category case variants or confirmed wire aliases, these different physical categories must not be guessed equivalent. The32 pending payload/date scopes have not yet been inspected. No replay, delete, mark-as-processed or worker/ARI activation was used to hide or drain them.

The super-admin `/api/outbox/events` inspection endpoint had no tenant filter, so requesting one was silently ignored. Rather than read other properties' global payloads, this follow-up adds an optional exact tenant filter to **both** listing and count. An omitted filter retains the intentional global super-admin view; an empty/whitespace-only/overlong filter is rejected before reads. Existing admin authorization, replay/configuration guards, workers and delivery behavior are unchanged. New scoped-inspection tests cover other-tenant exclusion, combined provider/status filters, empty tenant results, literal `$ne`, pagination/count consistency, invalid-filter fail-closed behavior and admin rejection. Deployment of this read-only correction is needed before scoped pending-event inspection; it is not provider acceptance by itself.

Verification:12 new HTTP-level regression checks (10 failed before the change), and73 passing targeted checks in total including configuration recovery, legacy availability dispatch, Exely ARI activation and durable delivery. These are mocked/isolated offline checks with an explicit localhost database URL and external dry-run; they are not73 live deliveries. Changed-file Ruff and diff checks pass. No worker, retry, mapping, authorization, security gate or production database behavior is changed by this small read-path filter.

Local evidence remains outside the repository in `exely-kabul-20261027.jC7lde/`: provider-1110-delivery-history-20261028.png, provider-1110-wire-summary-20261028.json (allowlisted structure, source SHA256 retained), provider-stock-baseline-20261028.png, and outbox-tenant-before/after.xml. Original provider export remains in the user's Downloads and was not committed or uploaded; credentials/contact XML were not printed. No new provider booking terms were accepted, no production DB access was used, and ARI/scheduled imports remain off pending scoped queue review and a baseline/restoration plan.

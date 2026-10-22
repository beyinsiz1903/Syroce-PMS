# Exely Production Readiness

## 2026-10-22 Read Reservation demographic reconciliation follow-up

With explicit user consent, the Exely TEST 501694 ConnectivityHub client
`Syroce PMS TEST 501694 Read Only` was created and enabled at 10:34 Istanbul
time. Only Read Reservation API is selected; no other API or property was
enabled. A temporary browser OAuth session against the official TEST server
successfully read booking `20261110-501694-1200421078` (HTTP 200 at 10:49).
The actual response has `adultCount: 2`, `childAges: [6]`, 120 USD, the expected
10–11 November stay and provider modification time. The temporary session was
closed; its credentials were not saved to the browser or checked into Git.

This follow-up adds a distinct encrypted secrets-manager identity
`exely-read-reservation`, bound to tenant, property, saved connection ID and mode.
SOAP credentials cannot be used as REST credentials. The server selects exact
official test/production origins from saved routing state; no user URL,
redirect, environment proxy, plaintext credential fallback or write API is used.
OAuth tokens are ephemeral, reused within a batch and not persisted or returned.
Production/sync kill switches still gate requests. This does not enable any
connection automatically.

The Exely connection screen now offers a scoped save consent, exact existing
reservation probe, pause control and explicit reconciliation. Saving validates
the remote response and local join before enabling the connection, but does not
rewrite a PMS booking. The explicit reconciliation and the enabled scheduler's
post-import batch share one demographic-only mutation path.

Reconciliation requires the same tenant/property/booking/provider timestamp,
currency, total, room type, stay dates and total guest count. A unique room join
is required: SOAP and REST room-stay index bases are not guessed. Ambiguous
identical multiroom stays require review. Only confirmed PMS bookings whose
counts still match their source (or matching previous proof) can be changed.
Checked-in/cancelled/checked-out and manually altered counts are not overwritten.
Each update uses a compare-and-swap fence, increments the PMS edit version,
reads back the result and appends a separate immutable demographic evidence row.
Partial multiroom races return an error rather than falsely claiming all rooms
were applied. Original SOAP payloads/hashes, version ledger, ACK state, guest
profiles, room assignment, KBS, rates, folios, payments and invoices are untouched.

Automatic batches handle at most 25 future unverified bookings per enabled
tenant pull, rotate review failures by last attempt, and stop a batch on a
provider/auth/quota outage. Pausing does not undo an already started operation.
Verification provenance is invalidated by a new SOAP version and is bound to
current PMS counts, ages, dates, room type, currency and amount. The guest summary
and test verification read current PMS proof, not an old audit record. Booking
cache invalidation and warmer projections retain the new fields.

Release boundary: local code/tests are not live PMS acceptance. Deployment,
explicit TEST-only credential storage and PMS readback of the corrected synthetic
booking still need to be recorded after this change is deployed. Other properties
remain disabled. This verifies demographic transport, not hotel-specific child
pricing parity, legal/KBS acceptance or every commercial booking scenario.

## 2026-10-22 follow-up release boundary

Manual/test-booking pulls and the shared configuration checks retain only the
active property's saved connection mode. Credential payloads cannot grant
sandbox permission. No endpoint/SSRF gate or production switch is relaxed.

Test-booking lookup is tenant/property scoped and finds an already-ACKed local
record without pretending it was returned by a new Undelivered response. Import,
ACK and demographic acceptance are separate checks. Optional exact-ID adult and
arrival-age expectations detect a mismatch; matching stored counts alone never
certifies the provider's demographic data. Provider/ingest failures are errors,
not successful discovery. Unknown child ages are not inferred from notes.

An explicit child age on AdultBed is retained rather than discarded as an adult.
A contradictory numeric adult code plus a child age stays held for review.
No-age payload shape/hashes are unchanged; already imported versions are not
rewritten or re-ACKed. The Exely reservation sidebar and full guest summary show
total guests with an unverified demographic warning, not a certified adult/child
split. This conservative warning also applies to legacy Exely records until an
independent reconciliation establishes provenance.

At the PR 1385 release boundary, the separate Read Reservation REST contract exposed adultCount and childAges
(https://exely.com/dev-portal/docs/api/), but was not integrated or activated by
that release. The user authorized read-only access for TEST 501694 only. The
Exely ConnectivityHub screen remained on its loading indicator, including a
reload; no OAuth client/secret was created and no access was enabled. Do not
claim PR 1385 fixes the provider's missing live ages or completes child
acceptance. TEST booking 20261110-501694-1200421078 remains unreconciled.

Expanded offline regression selection: 320 passed, two real-Mongo tests excluded.
Release workflow and live revision checks must be recorded after deployment;
offline test results are not evidence of deployment or live REST access.

## 2026-10-22 approved TEST 501694 child-booking acceptance

An explicitly approved synthetic booking was created through the Exely QA
booking engine, not a real hotel: `20261110-501694-1200421078`, Deluxe,
10–11 November 2026, two adults and one six-year-old child, Base rate USD,
120 USD total, 0 USD prepaid, payment at check-in. The provider's confirmation
explicitly preserves `2 adults + child 6 years`. Marketing consent was not
selected. No real guest details or payment instrument were used.

The Exely property defines half-open child ranges `[0,3)`, `[3,7)` and `[7,18)`
(completed ages 0–2, 3–6, 7–17). These are not the same as the defaults visible in
the PMS per-person editor. No local pricing rule was saved, no parity attestation
was selected and no ARI/pricing changes were sent as part of this acceptance.
Equal room totals alone do not establish child-pricing parity.

The live ID-specific verification failed with `ExelyValidationError` before
reading the provider: that route constructed a provider without the saved
connection mode. The manual pull and unfiltered verification paths also omitted
the mode. The local correction forwards the active connection's saved `mode` in
all three paths. It does not infer sandbox permission from the endpoint, alter
global gates, accept plaintext credentials or relax endpoint validation.

New offline regressions reproduce the three failing entrypoints before the fix
and retain rejection for missing/production modes targeting the test host.
They also verify that ID-specific verification ingests only the matching booking
with the requesting tenant/property scope. The related offline selection passed
190 tests, with two real-Mongo tests deselected; Ruff and diff checks passed.
This correction is local and still requires deployment and a new live check.

### Live result: amount/import/ACK passed, child demographics failed

The existing 15-minute scheduler imported the synthetic booking at 08:52 on
22 October. PMS displays the same external ID, dates, 120 USD, confirmed/imported
status and one night. The Exely delivery log independently shows successful
creation/read at 08:52:44 and successful confirmation at 08:52:46. No manual
import, fabricated acknowledgement or price-policy override was used.

However, both the PMS quick summary and full reservation detail show three
adults and zero children. The actual Exely delivery response explains why:

```xml
<GuestCounts>
  <GuestCount AgeQualifyingCode="AdultBed" Count="1" ResGuestRPH="1" />
  <GuestCount AgeQualifyingCode="AdultBed" Count="2" />
</GuestCounts>
```

The response contains only the named primary guest, without an age or birth
date. It has no structured child count/age despite the Exely confirmation
showing two adults and a six-year-old child. The synthetic free-text guest note
mentions the test age, but is not authoritative structured demographic data and
must not be used to infer a child or rewrite an immutable provider version.

The accessible Exely delivery, synchronization and PMS inventory screens were
inspected without saving changes; no child-demographics transfer option was
exposed. Provider-side clarification/configuration and an approved new provider
revision or new synthetic booking are required before claiming child acceptance
or reconciling the already-acknowledged record. Do not label this scenario passed
merely because the amount and acknowledgement are correct.

## 2026-10-22 code audit — not a new provider certification

The historical pilot/cutover evidence below is not proof that every current
production property has passed live acceptance. This audit executes no provider
reservation/ARI operations and does not enable production flags or tenant
synchronization. The public test WSDL was inspected without credentials; schema
inspection is not property-level certification.

Tenant reservation controls now persist `auto_sync_reservations` on exactly the
selected connection. The legacy `/sync/scheduler/start` and `/stop` routes no
longer start/stop the process-wide worker. A started pull may finish its durable
import/ACK; stopping automatic pulls does not disable an explicit manual pull or
ARI. Process lifecycle and global kill switches remain deployment controls.

`PATCH /sync/settings` saves a 3–60 minute interval without reconnecting or
enabling a path. The worker streams all active connections (not just the first
100) and uses each saved interval in the distributed tenant lease. The lease
owner cannot bypass its own expiry. Existing leases are not deleted when an
operator changes the interval, so a shorter interval takes effect only after the
current quota/lease window. Poll execution may be delayed by the shared worker
tick or provider quota. Status distinguishes tenant enablement, global safety
gates, and the current replica's worker state; one replica's state is not proof
of cluster-wide health.

The UI allows stopping tenant reservation/ARI settings while global gates are
closed, but cannot use those controls to reopen a global gate. Connection polling
intervals can be changed in place. Failed status reads are displayed as unknown,
not as zero backlog or stopped synchronization.

ARI request models validate the complete bulk body before the handler queues any
item. Shared enqueue/provider preflight also rejects invalid dates, negative or
non-finite rates, invalid currency/LOS and non-boolean restrictions before
persisting sibling operations or contacting Exely. Zero availability and false
restriction values remain valid explicit updates. This is input validation, not
an atomic transaction across a bulk request: a later infrastructure failure can
still leave already-queued items and requires outbox reconciliation.

Before production acceptance, independently verify the selected property's vault
credentials, room/rate mappings, Redis quota health, read/import/ACK sequence,
modification, partial/full cancellation, child/prepayment/extras scenarios, and
each supported ARI restriction against the Exely test/production account in an
explicitly approved observation window. Offline tests do not close those items.

### Child ages and provider policy parity

Explicit child ages survive SOAP parsing, normalization and the durable PMS
booking. A single referenced guest can supply an age or date of birth; the latter
is converted to completed years on room arrival, not today or checkout. One
guest's birthday is never spread across multiple unidentified children. Missing
or invalid ages stay unknown (`children_ages_complete=false`), not free infants.
Provider amounts/currency remain authoritative and are not repriced locally.
Unknown nonzero guest-count codes without usable age evidence block PMS import
and ACK rather than silently losing a guest. Excessive per-room counts are
rejected before expanding age metadata. These paths still require representative
Exely child/infant/extra-bed test fixtures; no undocumented code alias is assumed.

Shared pricing and manual booking inputs reject fractional, boolean, missing or
out-of-range child ages; each configured inclusive age band must cover 0–17
without overlaps/gaps. The calendar asks for completed age on arrival instead of
prefilling unknown ages as zero. No hotel-specific free-age limit is imposed.

Saving an Exely policy no longer automatically claims provider verification.
Legacy auto-verified flags are not operator attestations. For an explicitly
configured per-person rule, unified base-rate publishing requires an operator to
confirm matching Exely panel rules. Changing the policy in the editor clears that
confirmation. This does not send age bands to Exely or constitute certification.
An invalid policy anywhere in a settings batch is rejected before sibling writes.
Invalid stored policies are explicitly marked invalid, not exposed as verified
free-child defaults; automatic price previews are suppressed until corrected.

Previously imported reservations are not silently rewritten. A repeated
provider version whose enriched child payload differs remains subject to the
existing immutable-version conflict checks; resolve through an approved provider
revision/reconciliation, not by bypassing hashes or manufacturing an ACK.

### Local verification evidence

- Exely/child-policy regression selection: 619 passed, 96 live/provider tests
  deselected. Real MongoDB tenant-isolation and lease tests used a temporary
  localhost database with synthetic records, not a property database.
- Additional direct/agency booking regression selection: 146 passed, 12
  deselected (some tests overlap the selection above).
- Full frontend coverage run: 370 files, 1,814 tests passed with two workers;
  coverage thresholds were preserved. A prior default-parallel run hit the
  existing 5-second AdminModuleControlCenter test timeout; no timeout or
  assertion was weakened for the successful rerun.
- Production frontend build, route bundle budgets, theme guard, changed-source
  Ruff/ESLint, import boundaries and test-inventory guard passed.
- These local checks do not constitute deployment or production acceptance. No
  production activation, reservation ACK or ARI write was performed by the audit.

## Decision boundary

The Exely technical integration and test-provider pilot are complete. Discovery,
undelivered reservation read, canonical durable import, exact-version
acknowledgement, queue cleanup, availability, rate, stop-sell, minimum stay, and
arrival-based minimum stay were confirmed through the protected pilot workflow.

The current `main` head `86273f46dcc6d74ab4c892388db764af9bf9523d`
was rechecked without provider mutation on 2026-08-11:

- discovery run `31487991082`: PASS, provider writes `0`
- reservation-read run `31488826717`: PASS, ACK writes `0`

The protected production cutover previously applied exact head
`b9e1ee1e1178a5f8f4e80739328d35e3affd3db2` in read-only mode through run
`31422645279`. The deployment was active, reservation synchronization and ARI
writes remained disabled, and provider reads/writes were both `0` during the
cutover.

This evidence does not authorize production. Production credentials, tenant
configuration, deployment, or provider operations require a separate explicit
go-live approval. Until that approval is recorded, the decision is **NO-GO**.

## Canonical production line

- Reservation delivery uses the Exely pull scheduler, `ExelyProvider`, canonical
  ingest, fenced PMS lifecycle, and exact-version acknowledgement.
- ARI uses the canonical durable outbox, `ExelyARIAdapter`, and the single-write
  Exely delivery record.
- The compatibility Exely webhook is not mounted in production. It is not a
  second reservation ingestion path.
- Provider payloads and identifiers are not retained in diagnostic logs. Safe
  telemetry is limited to result classes, booleans, counts, hashes, sizes, and
  exception classes.

## Runtime gates

Production Exely provider I/O is default-deny and requires all applicable gates:

| Gate | Default | Effect |
|---|---:|---|
| `ENABLE_EXELY_PRODUCTION` | off | Blocks every production Exely read and write before provider access. |
| `DISABLE_EXELY_RESERVATION_SYNC` | off | Emergency stop for reservation reads and acknowledgement writes. |
| `DISABLE_EXELY_ARI_WRITE` | off | Emergency stop for ARI enqueue and provider mutation delivery. |
| Connection `auto_sync_reservations` | explicit | Enables scheduled reservation pulling for that tenant only. |
| Connection `ari_write_enabled` | false | Enables ARI provider delivery for that tenant only. |

The two emergency switches are independent. Turning off the production master
gate blocks both paths. The authenticated Exely sync status response exposes
only boolean runtime state; raw environment values are never returned.

## Pre-go-live checklist

All items are blocking. A missing or ambiguous result is not a pass.

### Isolation and credentials

- [ ] Production credentials are stored only in the production secrets manager.
- [ ] Test and production credentials are demonstrably different.
- [ ] No plaintext credential exists in the connection document.
- [ ] Production MongoDB and Redis are distinct from pilot resources.
- [ ] The connection resolves exactly one tenant and one production property.
- [ ] The endpoint is HTTPS and the official Exely production host/path.
- [ ] Provider-side outbound IP access requirements are confirmed.

### Mapping and limits

- [ ] Every live PMS room/rate product has exactly one active Exely mapping.
- [ ] No PMS product or provider room/rate pair has duplicate mappings.
- [ ] Currency and tax/business rules match the Exely production property.
- [ ] Distributed Redis quotas are healthy and fail closed when unavailable.
- [ ] Connection-level ARI writing remains disabled during reservation cutover.

### Monitoring and response

- [ ] Alerts exist for authentication failure, HTTP 5xx, timeout, parse failure,
  provider rejection, local quota failure, and circuit-open state.
- [ ] Alerts exist for aged `ACK_PENDING`, `PMS_FAILED`, mapping hold, duplicate
  mapping, ambiguous ARI delivery, and outbox backlog.
- [ ] Dashboards show reservation read count, durable import count, ACK write
  count, ARI write count, status class, latency, and quota state without PII.
- [ ] An on-call owner and an incident channel are assigned for the cutover.

## Controlled first-live procedure

1. Run the protected `Exely Production Cutover` workflow with
   `operation=prepare_disabled`, the approved exact `main` SHA, and explicit
   production confirmation. This deploys the approved head with
   `ENABLE_EXELY_PRODUCTION` off and both emergency switches on. Do not configure
   automatic synchronization yet. The workflow cannot be re-run and never calls
   Exely.
2. Verify the application is healthy, the compatibility webhook is absent, and
   both Exely operation paths report disabled.
3. Install production credentials and tenant/property mapping without printing
   or copying their values into tickets, chat, logs, or workflow inputs.
4. Keep reservation and ARI emergency switches on. Run the cutover workflow with
   `operation=enable_read_only` and a fresh explicit approval to enable only the
   production master gate. The workflow verifies the live exact SHA and all three
   flags without printing the application spec. Then perform one separately
   approved read-only connection/discovery check. HTTP 500, timeout, parse
   failure, or authorization failure is NO-GO.
5. After a successful read-only check, enable reservation synchronization for
   one property with `operation=enable_reservation_sync`, prerequisite
   attestation, and the exact `ENABLE_EXELY_RESERVATION_SYNC` confirmation.
   Keep ARI disabled. Observe exactly one real reservation through
   `PMS_DURABLE`, `ACK_PENDING`, one confirmed ACK write, and queue removal.
6. Reconcile the PMS booking, Exely queue, lifecycle lineage, and audit timeline.
   Any duplicate, stale version, mapping hold, or uncertain ACK result is NO-GO.
7. Complete a separately approved modification and cancellation observation.
   ACK is allowed only after each PMS mutation is durable.
8. Enable ARI only in a later window with `operation=enable_ari_write`,
   prerequisite attestation, and the exact `ENABLE_EXELY_ARI_WRITE`
   confirmation. Reservation synchronization is stopped during this stage.
   Start with one mapped product and one approved operation. Do not retry an
   ambiguous mutation.
9. Expand tenant/property scope only after the observation window closes with no
   P0/P1 issue, no 5xx, and no unresolved reconciliation item.
10. Run `enable_live` with the exact `ENABLE_EXELY_LIVE` confirmation only after
    both isolated observation windows pass. This is the only stage that opens
    reservation synchronization and ARI delivery together.

## Rollback and kill procedure

1. Set both emergency switches on. This is the first action for any uncertain
   provider result, mapping defect, duplicate, 5xx burst, or data inconsistency.
2. Turn off `ENABLE_EXELY_PRODUCTION` to stop all Exely provider access.
3. Leave durable lifecycle, delivery, and outbox records intact for audit and
   reconciliation. Do not delete them and do not blindly resend an ACK or ARI
   mutation whose result is uncertain.
4. Disable tenant connection flags if the outage is tenant-specific.
5. Reconcile provider and PMS state read-only before re-enabling any path.
6. Roll back the application revision only after provider I/O has been stopped.
7. `operation=close_all` is the protected deployment-level emergency action. It
   forces the master gate off while keeping both path-specific switches on.

## Current gate result

| Area | Result |
|---|---|
| Offline code and CI | PASS |
| Protected test-provider pilot | PASS |
| Current-main read-only regression | PASS (`31487991082`, `31488826717`) |
| Default-deny production activation | PASS |
| Reservation and ARI emergency stops | PASS |
| Protected production read-only cutover | PASS (`31422645279`) |
| Production credentials and property mapping | NOT VERIFIED |
| Production network and monitoring configuration | NOT VERIFIED |
| First live reservation/modification/cancellation | NOT RUN |
| Production provider operations | 0 |
| Production provider activation | 0 |

**Current decision: TECHNICAL INTEGRATION COMPLETE / TEST-PROVIDER GO /
PRODUCTION READ-ONLY PASS / LIVE PROVIDER OPERATIONS NO-GO.**

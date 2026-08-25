# HotelRunner Production Readiness

## Current decision

- Code and offline regression: **PASS**
- Controlled test-account pilot: **PASS**
- Production safety controls: **PASS**
- Live production activation: **NO-GO** until every prerequisite below is verified and separately approved.

No production provider operation is required to validate this document or the safety controls.

## Runtime safety model

Production HotelRunner I/O is default-deny. `ENABLE_HOTELRUNNER_PRODUCTION=true`
opens the master provider gate only. Reservation synchronization and ARI writes
remain independently stoppable with:

- `DISABLE_HOTELRUNNER_RESERVATION_SYNC=true`
- `DISABLE_HOTELRUNNER_ARI_WRITE=true`

The manual cutover workflow starts with both stop switches enabled. A health
check is not provider verification and cannot be used as evidence that a live
reservation or ARI mutation succeeded.

## Required evidence before activation

1. Live credentials are isolated in the production secrets manager, rotated,
   least-privileged, and absent from repository, logs, workflow summaries, and
   query strings.
2. Live tenant, property, room type, and rate plan mappings have cardinality
   exactly one. Missing or multiple mappings remain fail-closed.
3. Production database, Redis namespace, backups, restore test, and retention
   policy are isolated from pilot data.
4. Provider network allowlists and outbound restrictions permit only the
   documented HotelRunner production host.
5. Alerts exist for provider 4xx/5xx, timeout, parse failure, lock loss,
   unmatched reservation holds, ACK backlog, ARI ambiguity, and reconciliation
   lag. Alerts must contain safe metadata only.
6. On-call ownership, rate limits, rollback authority, and provider escalation
   contacts are recorded and tested without a provider mutation.

## Controlled cutover stages

### 1. Prepare disabled

Run `prepare_disabled` only after exact-head CI and reviewer approval. The
master gate remains false and both reservation and ARI stops remain true.

### 2. Read-only platform activation

Run `enable_read_only`. This enables the HotelRunner master gate while keeping
reservation sync and ARI writes stopped. It only prepares the deployed runtime;
it does not call HotelRunner.

### 3. First live reservation

Requires separate written approval and a known live booking window. Run
`enable_reservation_sync` with prerequisite attestation and the exact
`ENABLE_HOTELRUNNER_RESERVATION_SYNC` confirmation. The cutover also requires
the run ID of a successful, first-attempt `reservation_reconciliation` pilot on
the exact approved SHA. Its artifact must prove one history match, zero
undelivered matches, a present PMS number, and zero provider writes. Official
HotelRunner callbacks are authenticated with the property's encrypted `token`
and `hr_id`. `HOTELRUNNER_CALLBACK_SECRET` is optional defence in depth; when
configured, the same value must be present in the callback URL path.
`HOTELRUNNER_WEBHOOK_SECRET` applies only to Syroce's HMAC test/custom mode and
is not a prerequisite for HotelRunner real-time push. This enables only
reservation synchronization, keeps ARI stopped, imports exactly one reservation,
verify durable PMS state, then permit one ACK after the durable result. Any
timeout, 5xx, parse error, lock loss, mapping hold, or ambiguous outcome is
**NO-GO** and must be reconciled read-only before further action.

### 4. First live ARI mutation

Requires another separate written approval. Run `enable_ari_write` with
prerequisite attestation and the exact `ENABLE_HOTELRUNNER_ARI_WRITE`
confirmation. This disables reservation synchronization while enabling ARI for
one mapped room,
rate plan, date, and operation. Send at most one write, require terminal
transaction reconciliation, then restore the ARI stop until evidence is
reviewed. Never retry an ambiguous mutation blindly.

### 5. Full live activation

Run `enable_live` only after the reservation and ARI observation windows both
close without a P0/P1 finding or unresolved reconciliation item. It requires
the exact `ENABLE_HOTELRUNNER_LIVE` confirmation and keeps the same exact-head,
first-attempt, protected-environment, live-image, and health gates.

## Rollback

Set the affected stop switch to true. For a full close, run `close_all`, which
also disables the master gate. Confirm the exact image SHA and all three flags
on backend, worker, and beat. Do not compensate with cancel/delete writes unless
the provider contract and business owner separately authorize them.

## Final GO gate

Production is **GO** only when all prerequisites are evidenced, a protected
environment reviewer approves the exact main SHA, and the first-live procedure
has an assigned operator and rollback owner. Until then the correct decision is
**NO-GO**.

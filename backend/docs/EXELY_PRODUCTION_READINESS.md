# Exely Production Readiness

## Decision boundary

The Exely test-provider pilot is complete. Discovery, undelivered reservation
read, canonical durable import, exact-version acknowledgement, queue cleanup,
availability, rate, stop-sell, minimum stay, and arrival-based minimum stay were
confirmed through the protected pilot workflow.

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
   one property. Keep ARI disabled. Observe exactly one real reservation through
   `PMS_DURABLE`, `ACK_PENDING`, one confirmed ACK write, and queue removal.
6. Reconcile the PMS booking, Exely queue, lifecycle lineage, and audit timeline.
   Any duplicate, stale version, mapping hold, or uncertain ACK result is NO-GO.
7. Complete a separately approved modification and cancellation observation.
   ACK is allowed only after each PMS mutation is durable.
8. Enable ARI only in a later window. Start with one mapped product and one
   approved operation. Do not retry an ambiguous mutation.
9. Expand tenant/property scope only after the observation window closes with no
   P0/P1 issue, no 5xx, and no unresolved reconciliation item.

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
| Default-deny production activation | PASS |
| Reservation and ARI emergency stops | PASS |
| Production credentials and property mapping | NOT VERIFIED |
| Production network and monitoring configuration | NOT VERIFIED |
| First live reservation/modification/cancellation | NOT RUN |
| Production provider operations | 0 |
| Production deploy | 0 |

**Current decision: PILOT COMPLETE / PRODUCTION NO-GO.**

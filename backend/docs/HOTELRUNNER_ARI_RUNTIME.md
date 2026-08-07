# HotelRunner ARI Runtime

## Canonical write path

All HotelRunner availability, rate, stop-sell, CTA/CTD, and minimum/maximum
stay writes use the REST date-range contract:

- Adapter: `HotelRunnerARIAdapter`
- Delivery service: `deliver_hotelrunner_ari`
- Method: `PUT`
- Endpoint: `/api/v2/apps/rooms/~`
- Verification method: `GET`
- Verification endpoint: `/api/v2/apps/infos/transaction_details`

The compatibility rate-manager, unified rate-manager, auto-availability sync,
retry queue, HotelRunner provider router, and HotelRunner v2 facade all enter
this delivery service. They do not interpret the initial HTTP acceptance as a
successful delivery.

## Write gate

A live write is allowed only when all tenant flags are explicit:

- `connector_enabled=true`
- `write_enabled=true`
- `shadow_mode=false`
- `dry_run_mode=false`

Missing or conflicting flags return `ARI_LIVE_WRITE_DISABLED` before provider
credentials are resolved and before any provider request is sent.

## Dry-run

Dry-run is a separate no-egress operation. It validates the same field and
endpoint contract and reports `provider_write_count=0`. A dry-run result never
enters provider ACK processing and cannot mark an outbound change set as
delivered.

## Delivery states

- `confirmed`: transaction counts are terminal, `failed=0`,
  `in_progress=0`, and `succeeded>0`.
- `reconciliation_pending`: the write was accepted but the transaction is
  still pending or the read-only status check is temporarily unavailable.
- `partial_failure`: at least one provider channel failed.
- `ambiguous`: timeout, connection loss, malformed response, missing
  transaction identity, or invalid transaction counts.
- `rejected`: definitive provider rejection, including rate limiting.
- `blocked`: validation, feature gate, credential resolution, or durable
  reconciliation preparation failed before the write.

Only `confirmed` is successful. Pending, partial, ambiguous, blocked, HTTP 5xx,
timeout, and parse failures never produce ACK.

## Reconciliation

The periodic HotelRunner reconciliation path is GET-only. It rechecks accepted
transaction identities and never resubmits the original mutation. The previous
60-day blind HotelRunner availability refresh is disabled because the public
REST contract exposes transaction details but not an authoritative ARI snapshot
read endpoint. A provider-state drift comparison therefore remains a controlled
pilot capability pending an explicit provider read contract.

Automatic retry is limited to a definitive pre-write rate-limit response.
Ambiguous writes and partial failures require reconciliation or manual review;
they are not sent again automatically.

Legacy ARI dead-letter entries are not replayable because their original write
outcome cannot be proven. The retry endpoint fails closed and directs operators
to reconciliation instead of submitting the mutation again.

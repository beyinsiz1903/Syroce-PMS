# Guest QR Catalogue Architecture

## Overview
This document outlines the architecture for the Structured Guest Request Submission feature. We leverage a robust ledger-backed system to ensure idempotency, resolve payload concurrency cleanly (preventing duplicate processing of the same cart checkout), and handle retries effectively without duplicate internal side-effects.

## Ledger Lifecycle
The `guest_service_submissions` collection operates as the authoritative ledger for every QR request basket submission.
It utilizes a UUID mapping to an idempotency key originating from the client, scoped by Tenant, Property, and Booking.

- **pending**: The ledger is created before any underlying service documents (`qr_requests`) are upserted.
- **completed**: The convergence checker verified that every single structured requested service was successfully successfully written to the database.
- **failed**: Convergence check failed or an unrecoverable state occurred; the ledger may be retried.

## Convergence vs. Basket Atomicity
Since MongoDB transactions over sharded collections can be complicated and limit performance, we use **Convergence** rather than strict transactional basket atomicity.
1. The server strictly validates the payload and computes a payload fingerprint.
2. It attempts to create a ledger entry (`guest_service_submissions`) using a unique constraint `[tenant_id, property_id, booking_id, idempotency_key]`.
3. If this ledger already exists (duplicate request due to network retry):
   - If the fingerprint matches, it simply replays the execution to ensure all nested items were written.
   - If the fingerprint differs, it rejects with a `409 Conflict`.
4. Once the ledger is created, the item documents (`qr_requests`) are inserted iteratively using `upsert=True` to guarantee idempotency.
5. Finally, the system counts the inserted documents. If all expected items are found, the ledger is marked `completed`. If not, a `503` error is returned, instructing the client to retry.

## Identifiers
- **internal**: UUIDv4 identifiers such as `submission_group_id` and `_id` in `qr_requests`. These are never returned publicly to guests.
- **public**: Deterministic, masked identifiers.
  - `submission_reference` (e.g. `GSR-XXXXX`) - Returned for the entire group.
  - `request_reference` (e.g. `REQ-XXXXX`) - Returned per service item.

## Database Indexes
- **`guest_service_submissions`**
  - `tenant_id`, `property_id`, `booking_id`, `idempotency_key` (UNIQUE) - Ensures idempotent race prevention.
  - `tenant_id`, `submission_reference` (LOOKUP)
- **`qr_requests`**
  - `tenant_id`, `submission_group_id`, `service_code` (UNIQUE PARTIAL: `{submission_group_id: {$exists: true}, service_code: {$exists: true}}`) - Ensures no duplicate services within a submission group.
  - `tenant_id`, `request_reference` (UNIQUE PARTIAL: `{request_reference: {$exists: true}}`) - Global public reference resolution.

## Notification Guarantee
Notifications (WebSockets and Guest Chat) are **best-effort**.
They are executed **after** persistence guarantees have successfully written the documents and completed the ledger. Notification failure logs a warning but never causes a `500` or rollback.

## Error Contract & Public Visibility
For security and privacy against probing:
- Detailed schema violations are swallowed and masked as "Geçersiz girdi".
- Requests for disabled services, unknown modes, or out-of-hours fallbacks return a generic "Talep işleme alınamadı".
- Explicit `service_code` details are not exposed when a service is rejected.

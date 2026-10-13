# Agency booking completion

The canonical PMS booking contains `agency_completion` in the same atomic booking insert. A successful booking response means the reservation exists, not that every integration has finished. Portal responses expose `integration_status`; marketplace lists merge tenant/agency-scoped canonical records so ledger failure cannot hide a new booking.

## Processing guarantees

- Workers atomically claim a booking with a two-minute owner lease. Expired leases recover after process termination. Each external step has a 45-second deadline; progress renews the lease and is owner-conditional.
- Folio, marketplace ledger, notification and audit writes use deterministic Mongo `_id` upserts. Folios receive a stable folio number. Successful steps are not repeated. A failed step does not prevent independent inventory/notification steps.
- Inventory events use the existing durable outbox with a stable dedup key. Startup requires the unique outbox dedup index. Completion waits for outbox dispatch acknowledgement, not just enqueue.
- Webhooks reuse stable delivery IDs, skip acknowledged successes, and expose stable recipient idempotency keys. Delivery is **at least once**, not exactly once: remote consumers must deduplicate uncertain acknowledgements. WebSocket emission is also at least once and does not prove every client received it.
- Eight failed completion attempts lead to `failed`, with exponential retry up to one hour. Persisted errors contain step and exception class only, never provider messages/tokens.
- Downstream connector jobs have their own queues and dashboards; completion does not certify final OTA acceptance or guest delivery. Existing messaging pending markers remain managed by their existing worker.

## Operations

Open **Acente Yönetimi → Eksik entegrasyonlar** (`/admin/agency-integrations`). List and retry endpoints require the existing system-admin guard. Pagination covers the backlog. Retry only requeues eligible incomplete work and failed inventory events; it never recreates the booking or steals an active worker lease.

Fix provider/configuration problems before retry. An unavailable worker leaves persisted work visible. Monitor oldest pending age and failed count. A prolonged `waiting` state should be investigated in the outbox/channel monitoring screens.

## Release and acceptance

This PR is stacked on legacy portal parity (#1266). Deploy after that stack. No historical bookings are silently backfilled: old records need a separately reviewed reconciliation because blind replay could duplicate legacy folios or external messages. No production data migration or real message transmission is part of this PR.

In staging, create one reservation in each portal, terminate the API/worker after the booking commit, restart, and verify one canonical booking, one folio, one ledger for marketplace, and completed progress. Temporarily reject webhook/connector delivery, verify visible retry/failure, restore service and use the repair action. Confirm another agency cannot see the reservation and a non-admin cannot access repair APIs. Automated tests cover claims, recovery, partial failure, deterministic writes, redaction, visibility, authorization wiring and UI retry behavior; actual provider delivery requires this staging acceptance.

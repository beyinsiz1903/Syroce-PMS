---
name: OTA unmatched-reservation hold
description: Design constraints for the shared hold/alarm helper that parks unmappable Exely/HotelRunner reservations.
---

# OTA unmatched-reservation hold

When an OTA reservation can't be room/rate-mapped (`pending_mapping` /
`unmapped_room_type`), a shared helper creates a "hold" PMS booking + sentinel
inventory locks + an urgent idempotent alarm, instead of silently parking it
(overbooking risk). Helper lives in
`backend/domains/channel_manager/providers/unmatched_hold.py`.

## Two non-obvious constraints (get these wrong and it breaks silently)

1. **The hold booking MUST omit `source.external_reservation_id`.**
   `core/import_decision.check_booking_source_exists` matches a duplicate on
   `source.provider` + `source.external_reservation_id`. If the hold carried
   both, the import-bridge duplicate short-circuit would treat the hold as the
   real booking on the rebind re-run and skip creating the real booking.
   The hold keeps `external_reservation_id` only as a TOP-LEVEL field (used by
   release/cancel lookups), and `source = {provider, kind, hold:true}`.
   **Why:** rebind correctness depends on the duplicate check NOT firing on the hold.

2. **Sentinel locks do NOT block a real room type — by design.**
   Locks use `room_id = ota-unmatched::{provider}::{external_id}`, which does
   not exist in `rooms`. `core/room_type_inventory_service.compute_room_type_inventory`
   joins lock.room_id -> room_type and `continue`s on unknown ids, so sentinel
   locks never reduce any real type's `sellable` (verified by test). Channel
   inventory sync reads the same single-source `get_room_type_inventory`, so it's
   safe there too.
   **Why:** the real room type is unknown, so we can't block a specific type. The
   sentinel lock is an honest Layer-1 artefact of the held state; the REAL
   operational protection is the alarm. Don't "fix" this by counting sentinel
   locks against a type — that would be wrong inventory math.

## Alarm & PII
- Title is exactly `ACİL: EŞLEŞMEYEN REZERVASYON - AKSİYON BEKLİYOR` (Turkish İ).
- Per-reservation idempotency via in-app notification `dedup_key=unmatched_mapping_{ext}`.
- Guest name (PII) goes ONLY in the tenant-isolated in-app notification; it is
  kept OUT of the Control Plane alert context/message and the websocket payload
  (those can egress to Slack/email). Websocket uses tenant-scoped
  `broadcast_booking_update(..., tenant_id=...)`, NOT the global notifications room.
- Honest limitation: `controlplane/alerting.fire` cooldown is per-trigger GLOBAL,
  so the cp channel can under-alert across different reservations in a short
  window; in-app dedup is the per-reservation guarantee.

## Lifecycle wiring (4 live callers)
- `release_unmatched_reservation_hold(delete_hold=True)` = rebind (delete hold +
  locks, then caller builds the real booking — no double count).
- `delete_hold=False` = cancel (free locks, mark hold cancelled, keep audit row).
- Exely live path = `common_ingest.process_reservation` + `exely/auto_import.py`
  (Exely does NOT use the unified pipeline). HR live path = `ingest/pipeline.py`
  + `core/import_bridge_service.auto_import_reservation_to_pms`.
- `hotelrunner_ingest` is DEAD (no non-test callers) — don't wire it.

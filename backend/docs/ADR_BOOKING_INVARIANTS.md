# ADR-001: Booking Integrity Invariants

**Status**: ACCEPTED  
**Date**: 2026-03-22  
**Decision Makers**: System Architecture  
**Scope**: Reservation lifecycle, room-night inventory, availability truth

---

## Context

Syroce PMS manages hotel room inventory where overbooking is not a "bug" but a **trust violation**. Every reservation touches financial commitments, guest expectations, and OTA contractual obligations. The booking subsystem must enforce invariants that hold under concurrency, partial failures, retries, and race conditions.

This document defines the **non-negotiable invariants** that all booking-related code must respect. Any PR that violates these invariants is a release blocker.

---

## Invariants

### INV-1: Sellable Inventory Never Goes Negative

```
For any (tenant_id, room_id, night_date):
  count(active_locks) <= 1
  
For any (tenant_id, room_type, night_date):
  sellable_count >= 0
```

**Enforcement**: Unique compound index on `room_night_locks(tenant_id, room_id, night_date)`. DuplicateKeyError = hard reject (409).

**Consequence of violation**: Guest arrives to a double-booked room. Compensation cost, review damage, OTA penalty.

---

### INV-2: Full-Stay Reservation is All-or-Nothing

```
A reservation for N nights either:
  - Claims ALL N night-locks and inserts the booking, OR
  - Claims ZERO night-locks (full rollback on any failure)

Partial reservations (3 of 4 nights claimed) MUST NOT exist.
```

**Enforcement**: Sequential lock acquisition with compensation on failure. If night K fails, nights 0..K-1 are released before raising BookingConflictError.

**Audit**: Every rollback writes a `lock_compensation` event to `event_timeline` with metadata listing claimed and failed nights.

---

### INV-3: Idempotency Key Produces Identical Results

```
For the same (tenant_id, idempotency_key):
  - First request: executes and returns result
  - Subsequent requests with same payload: returns cached result
  - Subsequent requests with different payload: 409 Conflict

No idempotency key replay ever consumes additional inventory.
```

**Enforcement**: `idempotency_locks` collection with unique index on `(tenant_id, scope, idempotency_key)`. Lock acquired before any side effects.

---

### INV-4: Cancel / Modify / Rebook Precedence is Deterministic

```
Race resolution rules (in priority order):
  1. Cancel always wins over concurrent new booking for same nights
  2. Modify shrink (fewer nights) always succeeds
  3. Modify expand requires lock acquisition for new nights (may fail)
  4. Rebook after cancel succeeds only after locks are fully released
  5. Parallel updates to same reservation: first-write-wins via version check
```

**Enforcement**:
- Cancel: releases locks immediately, then updates booking status
- Modify: acquires new locks before releasing old ones (expand), or releases excess locks (shrink)
- Version field `_version` on booking document; update requires `_version` match

**Timeline events**: Every cancel, modify, and rebook race writes a `booking_state_transition` event with `previous_state`, `new_state`, and `trigger` (user/system/channel).

---

### INV-5: OOO / OOS / Maintenance Writes to Same Availability Truth

```
A room marked OOO/OOS/maintenance:
  - Inserts lock documents into room_night_locks with booking_id="OOO:{room_id}" or "OOS:{room_id}"
  - These locks participate in the same uniqueness constraint
  - Attempting to book an OOO room returns 409 with clear reason

Removing OOO/OOS status releases the corresponding locks.
```

**Enforcement**: Same `room_night_locks` collection and unique index. Lock `booking_id` prefix distinguishes operational holds from guest bookings.

**Rationale**: If OOO/OOS lives in a separate system, the booking engine can sell rooms that operations has closed. Single source of truth eliminates this category of bugs.

---

### INV-6: Every Conflict / Reject / Auto-Release Appears in Event Timeline

```
The following events MUST write to event_timeline:
  - lock_acquired: night-lock successfully claimed
  - lock_conflict: DuplicateKeyError on night-lock (409)
  - lock_compensation: partial claim rolled back
  - lock_released: cancel/modify/expiry released locks
  - hold_expired: TTL-based hold auto-released
  - ooo_applied: room taken out of order
  - ooo_released: room returned to service
  - booking_state_transition: any status change

Each event includes: tenant_id, correlation_id, booking_id, room_id, 
night_dates affected, trigger source, timestamp.
```

**Rationale**: A booking system that rejects correctly but can't explain _why_ is operationally useless. The timeline makes every decision auditable in <5 seconds.

---

## Decision

All booking code paths (UI, API, channel manager import, group booking, front desk) go through `core/atomic_booking.py`. This single entry point enforces INV-1 through INV-6.

No code path may directly insert into the `bookings` collection without going through `create_booking_atomic()`.

No code path may modify room availability without going through `room_night_locks`.

---

## Consequences

- **Positive**: Overbooking becomes physically impossible at the database level
- **Positive**: Every rejection is explainable via timeline
- **Positive**: Channel manager and UI share the same truth
- **Positive**: Retry storms cannot consume phantom inventory
- **Negative**: Lock acquisition adds ~2-5ms per night per booking
- **Negative**: OOO/OOS changes require lock management (not just a status flag)

---

## Test Criteria (CI Hard Gate)

| Scenario | Expected | Gate |
|----------|----------|------|
| 100 concurrent same room-night | Exactly 1 success | HARD |
| 4-night booking, night 3 contested | 0 partial reservations | HARD |
| Same idempotency key retry | No duplicate inventory | HARD |
| Cancel + new booking race | Deterministic winner | HARD |
| Modify expand + availability race | Consistent state | HARD |
| OOO room booking attempt | 409 with clear reason | HARD |
| Hold expiry | Auto-release + timeline event | HARD |
| Cancel then rebook same dates | Success after full release | HARD |

---

## References

- `core/atomic_booking.py` — Lock acquisition and release
- `modules/pms_core/reservation_state_machine.py` — State transitions
- `modules/reservations/services/create_reservation_service.py` — Booking creation
- `modules/reservations/services/update_reservation_service.py` — Booking modification
- `controlplane/timeline_writer.py` — Event timeline

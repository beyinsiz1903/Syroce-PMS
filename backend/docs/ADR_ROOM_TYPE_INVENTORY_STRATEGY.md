# ADR-003: Room-Type Level Inventory Strategy (Phase C)

## Status: DRAFT
## Date: 2026-03-24
## Authors: System Architecture
## Scope: Room-type aggregation, availability computation, channel manager inventory sync

---

## Context

### Current State: Room-Level Locking (ADR-001)
The booking system currently operates at the **individual room** level:

```
room_night_locks (unique index: tenant_id + room_id + night_date)
├── Room 101 × 2026-04-01 → booking_abc
├── Room 101 × 2026-04-02 → booking_abc
├── Room 102 × 2026-04-01 → booking_def
└── Room 103 × 2026-04-01 → OOO:103
```

This guarantees **INV-1** (no overbooking) at the physical room level. However, hotels and OTAs operate at the **room-type** level:

- A guest books "Deluxe Double" not "Room 214"
- Channel managers push availability as `{room_type: "DBL", date: "2026-04-01", available: 5}`
- Revenue managers set prices per room type, not per room

### Problem

There is currently **no formal layer** that:
1. Aggregates individual room locks into room-type availability counts
2. Serves as the authoritative source for "how many DBL rooms can I sell tonight?"
3. Feeds the channel manager with real-time, accurate availability numbers
4. Handles the assignment of a room-type booking to a specific physical room

The channel manager's `reconciliation_service.py` computes availability ad-hoc by counting rooms and subtracting bookings. This is fragile and diverges from the lock-based truth.

### Consequences of No Room-Type Layer
- **Availability drift**: Channel manager pushes stale availability because it recalculates from scratch each time
- **No allotment control**: Cannot set "sell max 3 DBL on Booking.com" without a dedicated layer
- **Assignment ambiguity**: Booking creation picks a room arbitrarily; no optimization for housekeeping, guest preferences, or revenue
- **Rate-availability mismatch**: Rate manager sets prices per room type, but availability is computed separately

---

## Decision

### Introduce a 3-layer inventory model

```
┌─────────────────────────────────────────────────┐
│  Layer 3: Channel Inventory (per OTA/channel)   │
│  Collection: channel_inventory                   │
│  Schema: {tenant, channel, room_type, date,      │
│           allotment, sold, available, stop_sell}  │
│  Purpose: What each channel is allowed to sell   │
├─────────────────────────────────────────────────┤
│  Layer 2: Room-Type Inventory (property-wide)    │
│  Collection: room_type_inventory                 │
│  Schema: {tenant, room_type, date,               │
│           physical_total, locked, sellable,       │
│           holds, ooo, oos}                        │
│  Purpose: Authoritative sellable count per type  │
├─────────────────────────────────────────────────┤
│  Layer 1: Room-Night Locks (physical rooms)      │
│  Collection: room_night_locks (existing)         │
│  Schema: {tenant, room_id, night_date,           │
│           booking_id, lock_type, ...}             │
│  Purpose: Physical room-level truth (ADR-001)    │
└─────────────────────────────────────────────────┘
```

### Layer 2: Room-Type Inventory (New — Core of Phase C)

#### Schema: `room_type_inventory`

```json
{
  "tenant_id": "string",
  "room_type": "string",        // e.g. "DBL", "SGL", "STE"
  "date": "2026-04-01",         // ISO date string
  "physical_total": 10,         // Total rooms of this type
  "locked_booking": 6,          // Rooms locked by confirmed bookings
  "locked_hold": 1,             // Rooms locked by TTL holds
  "locked_ooo": 1,              // Rooms locked by OOO
  "locked_oos": 0,              // Rooms locked by OOS/maintenance
  "sellable": 2,                // = physical_total - locked_* (derived)
  "last_computed_at": "ISO8601",
  "computation_source": "event" // "event" (real-time) or "reconciliation" (batch)
}
```

**Index**: Unique compound `(tenant_id, room_type, date)`

#### Computation Strategy: Event-Sourced + Periodic Reconciliation

**Real-time path** (hot path — on every booking/cancel/hold/OOO event):
```
Event (lock_acquired / lock_released / hold_expired / ooo_applied)
  → Room-Type Inventory Updater
    → atomic $inc on room_type_inventory
    → channel_inventory fan-out (if configured)
```

**Reconciliation path** (cold path — every 5 minutes + on-demand):
```
Reconciliation Worker
  → Query room_night_locks grouped by (tenant, room_type, date)
  → Compare with room_type_inventory
  → Fix any drift
  → Log discrepancies to event_timeline
```

### Layer 3: Channel Inventory (New — Phase C.2)

#### Schema: `channel_inventory`

```json
{
  "tenant_id": "string",
  "connector_id": "string",     // Channel manager connector
  "channel": "string",          // "booking_com", "expedia", "direct"
  "room_type": "string",
  "date": "2026-04-01",
  "allotment": 5,               // Max rooms this channel can sell
  "allotment_type": "soft",     // "soft" (auto-calculated) or "hard" (manual cap)
  "sold": 3,                    // Rooms sold on this channel
  "available": 2,               // = min(allotment - sold, property_sellable)
  "stop_sell": false,            // Manual or automated stop-sell flag
  "last_pushed_at": "ISO8601",  // When availability was last pushed to OTA
  "last_pushed_value": 2,       // What value was pushed
  "push_pending": false          // True when available != last_pushed_value
}
```

**Index**: Unique compound `(tenant_id, connector_id, room_type, date)`

---

## Room Assignment Strategy

Currently, booking creation picks a room arbitrarily. Phase C introduces a **deferred assignment** model:

### Booking Flow (Before vs After)

**Before (current)**:
```
Guest selects "Deluxe Double" for Apr 1-3
→ System picks Room 201 (first available)
→ Locks Room 201 × Apr 1, Room 201 × Apr 2
→ Done
```

**After (Phase C)**:
```
Guest selects "Deluxe Double" for Apr 1-3
→ System checks room_type_inventory: sellable >= 1 for all dates
→ System reserves TYPE-level inventory (atomic $inc locked_booking)
→ Booking created with room_type="DBL", room_id=null (unassigned)
→ Room assignment happens:
   Option A: Immediately (auto-assign best available)
   Option B: At check-in (front desk assigns)
   Option C: By housekeeping optimizer (batch assignment)
→ Once assigned: insert room_night_locks for physical room
```

### Assignment Algorithm (Priority Order)
1. **Same room continuity**: If guest has multi-night stay, prefer the same physical room for all nights
2. **Housekeeping optimization**: Prefer rooms already clean/inspected for today's arrivals
3. **Floor preference**: Use guest profile preferences if available
4. **Revenue optimization**: Reserve premium rooms for potential upsells
5. **Wear leveling**: Distribute usage across rooms to even out maintenance cycles

---

## Integration Points

### 1. Atomic Booking (`core/atomic_booking.py`)
- `create_booking_atomic()` will check `room_type_inventory.sellable >= 1` BEFORE attempting physical room lock
- If room is pre-assigned: current flow (physical lock)
- If room is deferred: type-level decrement only

### 2. Channel Manager (`channel_manager/`)
- ARI push reads from `channel_inventory` instead of ad-hoc calculation
- `reconciliation_service.py` validates `channel_inventory` against `room_type_inventory`
- Stop-sell propagation is instant (flag flip → push)

### 3. Booking Hold Service (`core/booking_hold_service.py`)
- Holds decrement `locked_hold` in `room_type_inventory`
- Hold expiry increments `sellable` back
- No change to physical lock behavior

### 4. Event Timeline (`controlplane/timeline_writer.py`)
- New event types: `inventory_type_updated`, `inventory_drift_detected`, `channel_push_triggered`
- Drift events include: `expected_sellable`, `actual_sellable`, `lock_count`, `source`

### 5. Front Desk / PMS UI
- Room assignment widget for unassigned bookings
- Auto-assign button with algorithm selection
- Visual: room grid with type-level availability overlay

---

## Migration Strategy

### Phase C.1: Read-Only Materialized View (Non-Breaking)
1. Create `room_type_inventory` collection
2. Deploy reconciliation worker (every 5 min) that:
   - Counts rooms per type from `rooms` collection
   - Counts locks per type from `room_night_locks`
   - Writes computed values to `room_type_inventory`
3. Add API endpoint `GET /api/inventory/room-types?date=YYYY-MM-DD`
4. **No booking flow changes** — existing physical-lock path untouched
5. Verify accuracy: compare with ad-hoc channel manager calculation

### Phase C.2: Event-Driven Updates (Incremental)
1. Hook `room_type_inventory` updates into:
   - `create_booking_atomic()` → on lock success: $inc locked_booking
   - `release_booking_nights()` → on cancel: $dec locked_booking
   - `create_booking_hold()` → $inc locked_hold
   - `sweep_expired_holds()` → $dec locked_hold
   - `apply_room_block()` → $inc locked_ooo/locked_oos
2. Keep reconciliation worker as drift detector (not primary source)
3. Add `channel_inventory` collection
4. Wire ARI push to read from `channel_inventory`

### Phase C.3: Deferred Room Assignment (Optional, High-Impact)
1. Allow bookings with `room_id=null`
2. Implement assignment algorithm
3. Update front desk UI for manual assignment
4. Add auto-assign cron for next-day arrivals

---

## Invariants (Extensions to ADR-001)

### INV-7: Room-Type Sellable Count is Consistent with Locks

```
For any (tenant_id, room_type, date):
  room_type_inventory.sellable == 
    room_type_inventory.physical_total 
    - count(room_night_locks WHERE room.type == room_type AND date == date)
    
Drift tolerance: 0 (exact match required)
Drift detection: every 5 minutes via reconciliation worker
Drift resolution: reconciliation overwrites + event_timeline alert
```

### INV-8: Channel Inventory Never Exceeds Property Inventory

```
For any (tenant_id, room_type, date):
  sum(channel_inventory.available) <= room_type_inventory.sellable

Channel oversell is prevented by:
  1. Channel allotments capped at property sellable
  2. On property sellable decrease: reduce channel allotments proportionally
  3. Stop-sell triggered when sellable == 0
```

---

## Test Criteria (T0 Battle Tests — Phase C)

| Scenario | Expected | Gate |
|----------|----------|------|
| Room-type inventory matches lock count | Exact match after booking | HARD |
| Concurrent bookings reduce type inventory atomically | No race to negative | HARD |
| Cancel restores type inventory | sellable increments | HARD |
| Hold → confirm transitions type inventory correctly | hold→booking transfer | HARD |
| OOO reduces type sellable | Correct lock category | HARD |
| Channel inventory never exceeds property | Sum check per type/date | HARD |
| Reconciliation detects artificial drift | Alert + auto-fix | HARD |
| Deferred assignment → physical lock (C.3) | Lock acquired at assignment time | HARD |

---

## Telemetry & Observability

### Metrics to Collect
- `inventory.drift.count` — Number of drift detections per hour
- `inventory.drift.magnitude` — Absolute difference when drift detected
- `inventory.reconciliation.duration_ms` — Time to run full reconciliation
- `inventory.push.latency_ms` — Time from event to channel push
- `inventory.push.pending_count` — Channels with stale availability
- `inventory.type.sellable` — Gauge per room type (for dashboards)

### Dashboard Integration
- Control Plane: new "Inventory Health" section
- Show: type-level availability heatmap (room type × date)
- Alert: drift detected, push failures, sellable-zero events

---

## Risks & Mitigations

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Dual-write inconsistency (lock vs type inventory) | Medium | High | Reconciliation worker as safety net; drift alerts |
| Race condition on type-level decrement | Low | High | MongoDB `$inc` is atomic; unique index on type+date |
| Migration breaks existing bookings | Low | Critical | Phase C.1 is read-only; no booking flow changes |
| Channel oversell during push delay | Medium | Medium | INV-8 + conservative push (round down) |
| Deferred assignment guest experience | Low | Medium | Auto-assign 24h before check-in; manual override |

---

## Estimated Effort

| Phase | Scope | Effort | Risk |
|-------|-------|--------|------|
| C.1 | Read-only materialized view + API | 1-2 sprints | Low |
| C.2 | Event-driven updates + channel inventory | 2-3 sprints | Medium |
| C.3 | Deferred room assignment | 2-3 sprints | Medium |

**Recommended approach**: Ship C.1 first, run in shadow mode for 1-2 weeks, measure drift, then proceed to C.2.

---

## References

- ADR-001: Booking Integrity Invariants (`docs/ADR_BOOKING_INVARIANTS.md`)
- ADR-002: Test Quarantine Strategy (`docs/ADR_TEST_QUARANTINE_STRATEGY.md`)
- `core/atomic_booking.py` — Current room-level locking
- `core/booking_hold_service.py` — Hold lifecycle
- `channel_manager/application/reconciliation_service.py` — Current ad-hoc availability
- `channel_manager/infrastructure/repository.py` — Channel manager data access

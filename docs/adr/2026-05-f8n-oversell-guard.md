# ADR — F8N Reservation Oversell Guard (Task #215)

**Status:** Accepted
**Date:** 2026-05-20
**Surface:** `backend/core/atomic_booking.py`, `backend/bootstrap/phases/audit_indexes.py`,
`backend/modules/reservations/services/create_reservation_service.py`,
`backend/routers/pms_bookings.py`

## Context

F8N CI stress run (spec `95-reservation-lifecycle-deep.spec.js`, test C — *Overbooking
Detection*) reproduced a P0 oversell: a duplicate POST `/api/pms/quick-booking` for the
same room (`473d650d…`) over the same date window (`2026-05-20 → 2026-05-24`) returned
**2× HTTP 2xx** and persisted **two confirmed bookings** for the same room/nights.

Investigation showed every reservation-create code path funnels through
`core.atomic_booking.create_booking_atomic`, which relies on a **UNIQUE compound index**
`ux_room_night (tenant_id, room_id, night_date)` on `room_night_locks` as the
race-free oversell barrier. Root cause was twofold:

1. `backend/bootstrap/phases/audit_indexes.py` referenced the RNL field as `date`
   while the actual document field is `night_date`. The audit therefore could not
   verify the unique index existed.
2. In long-lived environments (stress DB; seed inserts that pre-date the unique
   index migration) the index could exist in a **non-unique** form created by an
   older deployment, which would silently fail the oversell guarantee. The
   bootstrap path swallowed the `IndexOptionsConflict` and moved on.

Either condition reduced the system to a single read-then-write check (no atomic
barrier) and allowed the duplicate insert observed in CI.

## Decision

### 1. Defense-in-depth: bookings-level overlap pre-check

`create_booking_atomic` now performs a **bookings-collection overlap query**
(`_find_overlapping_active_booking`) immediately before claiming room-night
locks. This query excludes terminal-state docs:

```python
TERMINAL_BOOKING_STATUSES = ("cancelled", "no_show", "checked_out")
```

If an active overlap is found, the function emits an overbooking alert and
raises `BookingConflictError(conflicting_booking_id=…, conflict_type="booking")`.

This is **not** the primary atomic guarantee — the unique RNL index still is —
but it closes the legacy-data hole the CI failure exercised: a pre-existing
booking inserted *without* claiming locks (seed scripts, broken older deploys)
is now detected before the new write commits.

### 2. Index contract hardening

`ensure_booking_indexes` was hardened with:

- **Pre-flight duplicate scan** of `(tenant_id, room_id, night_date)` groups
  in `room_night_locks` — duplicates are **logged at WARNING** with up to 5
  sample groups. Rows are **never deleted automatically** (per task guard
  rules — operators must adjudicate).
- **Non-unique drop** — if `ux_room_night` already exists without
  `unique=True` it is dropped so the unique re-create succeeds. Older
  deployments that created the index pre-uniqueness are self-healed on next
  boot.
- **Post-create verification** — after the create loop, `index_information()`
  is inspected; missing or non-unique `ux_room_night` produces a
  **CRITICAL** log line so monitoring/alerting can wire to it. The boot
  does not crash — the bookings-level overlap check remains as the
  in-memory guard for the degraded mode.

### 3. Audit job field-name fix

`backend/bootstrap/phases/audit_indexes.py` now references the correct field
name `night_date` (was `date`), so the daily index-audit job actually
exercises the oversell-barrier contract instead of a phantom field.

### 4. Structured 409 response

`CreateReservationService.create` and the multi-room loop in
`routers/pms_bookings.py` now return a structured 409 body:

```json
{
  "detail": {
    "message": "...",
    "conflicting_booking_id": "<uuid>",
    "conflict_type": "booking",
    "conflict_window": {
      "room_id": "...",
      "check_in": "YYYY-MM-DD",
      "check_out": "YYYY-MM-DD"
    }
  }
}
```

Backward-compatible: FastAPI still wraps it as `detail`, and the human-readable
message is preserved under `detail.message` so any client reading
`response.detail` as a string continues to surface the same text. New clients
can drive UX off `conflicting_booking_id` / `conflict_window`.

### 5. Terminal-state exception

`TERMINAL_BOOKING_STATUSES = ("cancelled", "no_show", "checked_out")` is now a
module-level constant. Both the bookings-level overlap query and the existing
cancelled-state short-circuit reference it, so the contract is one-line
auditable. A `cancelled` / `no_show` booking inserts without claiming locks
(unchanged); a `checked_out` booking releases its locks via
`release_booking_nights` (unchanged).

## Atomicity & race-freedom

The two-layer guard order is:

1. **Bookings overlap check** (read; cheap; catches seeded/legacy duplicates).
2. **RNL claim via per-night `update_one(upsert=True)`** under the unique
   `(tenant, room, night_date)` index (atomic; race-free even under parallel
   inserts).

Layer 2 remains the source of truth for the *“exactly one wins under N parallel
inserts”* guarantee. Layer 1 cannot reintroduce a TOCTOU race because any
concurrent inserter that slips past layer 1 will still be rejected by layer 2.

## Regression test

`backend/tests/test_atomic_booking_oversell_guard.py` (7 cases, direct DB,
no HTTP dependency):

| # | Case | Assertion |
|---|------|-----------|
| a | Serial overlap (identical + partial) | 2nd raises `BookingConflictError` |
| b | Adjacent windows (`co == next ci`) | Both succeed |
| c | Terminal state — `cancelled` / `no_show` / `checked_out` | Fresh booking succeeds |
| d | 5× concurrent `asyncio.gather` | Exactly 1 success, 4 conflicts, 0 errors |
| e | `_find_overlapping_active_booking` ignores terminal docs, finds active overlap | helper contract |
| f | Defense-in-depth: seeded booking with NO RNL rows | Still raises `BookingConflictError` (mirrors CI repro) |

Each test runs under a unique throwaway `tenant_id` (`f8n_oversell_test_*`) and
wipes its `bookings` + `room_night_locks` rows in fixture teardown. Tests
auto-skip when MongoDB is not reachable (conftest session-loop fixture).

## Operator notes

- **Old deployments** with a non-unique `ux_room_night` self-heal on next
  `ensure_booking_indexes()` run (boot or manual call). A WARNING line names
  the action.
- **Duplicate RNL rows** that pre-existed the unique index produce WARNING
  logs but are **not** auto-deleted. Operators must adjudicate (cancel one
  of the colliding bookings, then re-run the index ensure phase). Until
  resolved, the unique index creation will fail with
  `DuplicateKeyError` — the CRITICAL post-verify line is the alert signal.
- **CI**: stress spec C should now go green once the deployed env has either
  the unique index in place or the bookings-level defense path active.

## Out of scope

- E-fatura / GIB integration paths (untouched).
- Multi-room booking *order* heuristic — only the per-row failure now returns
  a structured 409; group rollback semantics unchanged.
- Auto-deletion of duplicate RNL rows — explicit task guard.

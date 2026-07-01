# Task #33 — /api/pms/rooms mid-suite 0-row regression — VERIFICATION (CLOSED)

> **Status: CLOSED — issue no longer reproduces.**
> The regression described in
> [`20260524_stress_full_stress_suite_f8ah_NOT_GREEN.md`](20260524_stress_full_stress_suite_f8ah_NOT_GREEN.md)
> (specs 03 / 05 / 10 receiving 0 stress-prefixed rooms mid-suite) was
> resolved by the F8A tur-15 hardening that landed before the
> 2026-05-26 84-spec GREEN baseline (Run #143, commit `3b3891d`).
> No new code change required.

## 1) Cause confirmed (post-hoc)

Original symptom: `fetchAllByPrefix(/api/pms/rooms)` returned 0
stress-prefixed rows in the setup steps of specs 03-room-move,
05-reservation-lifecycle, 10-qr-requests, even though the stress seed
verification logged `actual_rooms_total=560 / actual_rooms_with_prefix=560`
right after insert (drill 2026-05-24 §“F8A § 02 — rooms-fetch
regression”).

Root cause was **prior-round residue accumulation in the stress
tenant** (~9 000 stale `stress_seed=True` rooms tagged with previous
`stress_prefix` values) combined with a **fetcher pagination cap that
was too low** for that residue volume:

- `/api/pms/rooms` sorts ascending by `_id`, so the current-round
  500 base + 60 extras (latest inserts → highest `_id`s) land at the
  END of the result set.
- `fetchAllByPrefix` was capped at `maxPages=8 × pageSize=200 = 1600`
  rows, which only covered the OLDEST 1 600 residue docs.
- The prefix filter therefore matched 0 → spec setup saw an empty
  pool and reported `actual_rooms_with_prefix=0` mid-suite even
  though the DB had the 560 fresh rows.

This is consistent across specs 03 / 05 / 10 because all three call
`fetchAllByPrefix(... '/api/pms/rooms' ...)` during setup. Cache,
projection, and the `include_virtual` toggle were ruled out as
contributing causes (spec 03 already passes `include_virtual=true`
which bypasses the cache path, yet it still failed — DB-side
pagination over a polluted tenant was the dominant factor).

## 2) Fix already merged (responsible side: BOTH)

Two-layer fix, both layers landed pre-2026-05-26 baseline:

### A) Server-side pre-insert orphan scrub (primary)

`backend/domains/admin/router/stress.py` lines 1871-1918: before
inserting this round's seed, scrub all `stress_seed=True` docs whose
`stress_prefix != current` across `rooms`, `bookings`, `guests`,
`folios`, `folio_charges`, `room_night_locks`, `housekeeping_tasks`,
`room_qr_requests`, `service_complaints`, `messages`, `notifications`
and the F8C / F8D / F8E mirror lists. Scoped to the stress tenant +
`stress_seed=True` marker so it never touches real data; pilot tenant
blocked at the outer gate. Idempotent (delete_count=0 when no residue).

### B) Client-side pagination ceiling (defense-in-depth)

`frontend/e2e-stress/fixtures/stress-helpers.js` lines 5-15:
`maxPages` bumped 8 → 60 (12 000-doc capacity) so even if backend
orphan scrub misses untagged legacy residue, pagination fails LOUDLY
(hits maxPages) instead of silently dropping current-round docs at
the tail of an ascending `_id` sort.

### C) Seed observability (acceptance item #3)

`backend/domains/admin/router/stress.py` lines 2078-2091: seed
response includes `verification.actual_rooms_total`,
`actual_rooms_with_prefix`, `actual_extras_total`,
`actual_extras_with_prefix` (counts only, no PII) immediately after
`_chunked_insert(db.rooms, …)`. The 2026-05-26 baseline reports
`actual_rooms_total = 500 base + extras = 560` for the stress tenant
post-seed.

## 3) Evidence the regression no longer fires

- **Run #143 (2026-05-26)** — full 84-spec suite GREEN, 556 tests,
  `failedTests=0`, `P0=P1=0`, verdict GO WITH WATCH. Spec 03 / 05 / 10
  all PASS (rooms snapshot non-empty; no `Setup: stress room havuzu
  boş` assertion fail). Reporter artifact + drill report:
  [`20260526_stress_full_stress_suite_GREEN_84spec.md`](20260526_stress_full_stress_suite_GREEN_84spec.md).
- **Seed observability** verified in current code
  (`backend/domains/admin/router/stress.py:2080-2091`).
- **Pagination ceiling** verified in current helper
  (`frontend/e2e-stress/fixtures/stress-helpers.js:5-15`,
  `const maxPages = opts.maxPages ?? 60`).
- **Orphan scrub** verified in current seed
  (`backend/domains/admin/router/stress.py:1883-1918`, `rooms`
  present in collection list, `stress_prefix: {"$ne": prefix}` filter).

## 4) Recommendation

Close Task #33. No further action required on the rooms fetch path.
Continued protection comes from the GREEN-baseline gate (any
re-occurrence would surface as a `Setup: stress room havuzu boş`
hard fail on spec 05, or pages-exhausted warning on the helper, in
the next full-suite run).

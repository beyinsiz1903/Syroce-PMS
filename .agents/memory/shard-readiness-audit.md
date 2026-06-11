---
name: shard-readiness audit
description: Sharding prep facts — recommended shard keys vs actual indexes, doc/code naming drift, why live index inspection is the source of truth.
---

# Shard-readiness audit (tenant_id sharding prep)

Tool: `backend/scripts/audit_shard_readiness.py` (read-only) + test
`backend/tests/test_audit_shard_readiness.py`. Recommended shard keys live in
`docs/DATABASE_SHARDING_STRATEGY.md` §2; the readiness table is §9.

## Durable findings (not derivable without cross-referencing doc + live DB)
- **`folios` has NO `{tenant_id, created_at}` prefix index.** Every folio index
  leads with `tenant_id` but pairs it with `status`/`booking_id`/`folio_type`/
  `balance`, never `created_at` alone. So the doc's recommended folios shard key
  `{tenant_id, created_at}` is unsupported → REVIEW (not a blocker: shardable on
  `{tenant_id}` today; add the composite only if that exact shard key is chosen).
- **No `tasks` collection exists.** The doc lists `hotel_pms.tasks`; the codebase
  uses `housekeeping_tasks` (front-of-house board) + `task_queue` (job poller),
  both tenant_id-leading. Any tasks-sharding step must target those two.
- bookings/guests/rooms/audit_logs all have proper tenant_id-leading shard-key
  indexes; bookings' is `check_in:+1` while doc wants `check_in:-1` (field match,
  direction differs — create exact-direction index at shard time).

## Why the audit reads live indexes, not source
Index declarations are spread across `perf_indexes.py` + `audit_indexes.py`
(data-driven literal tables looped over `_raw_db[coll].create_index`),
`d_perf.py` (explicit calls), and `database_optimizer.py` + `atomic_*.py`
(aliased `coll = self.db.X` / `coll.create_index`). A static AST scan can't
reliably resolve the aliased/loop forms → would emit false "missing index".
**`index_information()` on the live cluster is the authoritative source.** The
script's static half is limited to the query scan (raw `_raw_db.<coll>` reads
lacking `tenant_id` = scatter-gather risk); proxy `db` reads auto-inject
tenant_id so they are shard-routable by construction and not scanned.

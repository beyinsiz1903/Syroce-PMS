---
name: When a Mongo index cannot fix a high query-targeting path
description: Query shapes that a btree index fundamentally cannot accelerate, so adding one is fake-green; plus how to triage Atlas "Query Targeting > 1000" alerts.
---

Atlas "Query Targeting: Scanned Objects / Returned > 1000" alerts mean a query
examined 1000x+ the docs it returned (missing/unselective index). Before adding
indexes, check whether the shape is even index-serviceable, and confirm the true
offender via the Atlas Query Profiler / Performance Advisor for the alert window
— do NOT add speculative indexes that the planner can't use (that is fake-green).

**Shapes a plain btree index CANNOT accelerate (do not "fix" with an index):**
- **Unanchored case-insensitive regex** (`{$regex: term, $options: "i"}`,
  substring search). The planner only uses an index for case-SENSITIVE
  `^prefix` regex. `$options:"i"` (or any non-prefix pattern) → scan within the
  tenant_id-narrowed set. This is the guest/booking "search box" pattern.
- **Substring search over encrypted fields.** Guest name/email/phone are stored
  encrypted; you cannot index ciphertext for plaintext substring/`i` matching at
  all — it is always a scan regardless of indexes.
- **Predicates evaluated AFTER `$unwind`** in an aggregation. A `$match` that
  runs post-unwind is in-memory; no index applies to it.

**Real fix for case-insensitive substring search (not an index alone):**
a normalized lowercase field (e.g. `name_lower`) queried with anchored/equality
semantics + a normal index, OR Atlas Search (text index) for true substring/`i`.
Both are write-path + backfill changes — scope them separately, don't bolt a
no-op index onto the bootstrap.

**Where an index DID genuinely help (night audit):** the daily-revenue pipeline
matched `$or:[{date:bd},{payment_date:bd}]` on `payments`; `payment_date` was
partially covered but the legacy `date` field had no index, so the date branch
scanned tenant-wide. A `(tenant_id, date)` index serves that branch. Note the
`status:{$ne:"voided"}` predicate (string field) is NOT equality and does not let
the `(tenant_id, voided, ...)` indexes substitute — `$ne` can't anchor an index.

**Triage tip:** when these alerts cluster in the same window as a stress run,
suspect synthetic load first (auto-CLOSED alerts that recur are usually transient
spikes), but still close genuinely-unindexed hot paths surfaced by the profiler.

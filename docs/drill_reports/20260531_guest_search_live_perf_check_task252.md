# Guest-name search — live Atlas performance confirmation (Task #252)

**Date:** 2026-05-31
**Scope:** Confirm the Task #248 guest-name search prefix conversion is actually
index-served on the live Atlas cluster (read-only `explain(executionStats)` +
backfill verification). No code changed. No data mutated.

## Context

Task #248 converted the guest-name search (`routers/pms_guests.py` `search_guests`)
and the complaints guest-picker (`domains/pms/misc/complaints.py`
`get_guests_for_complaints`) from an un-indexable unanchored case-insensitive
regex to an anchored prefix **RANGE** on `<field>_lower` companion fields, backed
by `(tenant_id, <field>_lower)` compound indexes. That was verified by code review
+ unit sanity + startup logs but NOT against real Atlas query plans (the sandbox
was believed to lack `MONGO_URL`). This task closed that gap.

**Note on the premise:** the task assumed the shell has no DB URI. In fact
`MONGO_ATLAS_URI` *is* present in the shell env, so the live `explain` was run
directly from a read-only script (`.local/verify_guest_search*.py`) using
`MONGO_URL=$MONGO_ATLAS_URI`, `DB_NAME=syroce-pms`.

## Findings — GREEN (conversion confirmed working)

### Indexes present
`guests` carries all three companion indexes:
`sn_tenant_id_name_lower`, `sn_tenant_id_first_name_lower`,
`sn_tenant_id_last_name_lower` — keyPattern `(tenant_id, <field>_lower)`.

### Backfill complete
- `search_normalize_backfill` marker `guests:v1` → `{done: true, updated: 7923}`.
- `db.guests.count_documents({name_lower:{$exists:false}})` = **0** globally and
  for every active tenant (stress 7822, pilot 98, plus 3 single-row tenants).

### explain(executionStats) — selective prefix (realistic "starts typing")
Pilot tenant, prefix `'fa'` (12 matching guests), query
`{tenant_id, name_lower:{$gte,$lt}}` sorted by `name`, limit 10:
- winningPlan: `IXSCAN` on **`sn_tenant_id_name_lower`** → FETCH → SORT → PROJECT.
- `nReturned=10 totalKeysExamined=12 totalDocsExamined=12` → **ratio ~1.0** (the
  Atlas query-targeting alert metric). `'zz'` (0 matches) → 0 examined.
- Full real main-search `$or` shape (name/first/last `_lower` ranges) uses **three
  IXSCAN** stages (one per companion index), no `COLLSCAN`, ratio ~1.2.

### The one nuance — broad prefix on the synthetic stress tenant
First pass *looked* like the old `idx_guest_name` was chosen with ratio 1.0. That
was a measurement artifact: the stress tenant's 7822 guests are all named
`E2E…`, so prefix `'e2'` matches **5739/7822 (73%)**. For such a non-selective
predicate the planner reasonably prefers `idx_guest_name` (which *also* satisfies
the `.sort('name')`, avoiding a blocking SORT) and residual-filters `name_lower`;
because nearly everything matches, it still fills the `limit=10` after ~10 docs.
This is the cost-based planner working correctly, not a scan regression:
- Selective predicate → planner picks the `name_lower` companion index (proven
  above on the pilot tenant).
- Non-selective predicate → planner picks the sort-serving index but the result
  is capped by the endpoint `limit` (10 main / 100 complaints), so
  Scanned/Returned stays ~1 either way.

The dangerous shape (selective predicate forced onto a full-tenant scan) does NOT
occur — that is exactly the case the planner routes to the companion index.

### Encrypted branch (unchanged, still indexed)
The main search's encrypted email/phone/id branch uses `_hash_<field>` exact-match
conditions served by the existing `hash_*_idx` indexes (present on the collection),
not regex scans. (Field encryption isn't loadable in the sandbox without keys, so
this was confirmed via the index inventory + existing memory, not a live explain
of that branch.)

## Verdict

The guest-name prefix conversion is **confirmed index-served on live Atlas** for
realistic searches (IXSCAN, Scanned/Returned ~1), backfill is complete, and the
marker is done. The query-targeting alert's driving metric is resolved. The Atlas
alert *dashboard* state over a soak window can only be read from the Atlas console
/ API (not from the app), so that remains an ops observation; the underlying
metric it triggers on is verified GREEN here.

## Artifacts (gitignored, read-only)
- `.local/verify_guest_search.py` — indexes, marker, coverage, canonical explain.
- `.local/verify_guest_search2.py` — selective vs broad prefix, sort on/off.
- `.local/verify_guest_search3.py` — full real main-search `$or` shape.

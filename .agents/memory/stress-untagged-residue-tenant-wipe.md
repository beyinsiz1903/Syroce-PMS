---
name: Stress collections filled by strict-Pydantic production POSTs need a tenant-scoped wipe
description: Why some stress collections accumulate residue the prefix sweep can't clean, and the established fix
---

A stress spec that creates rows through a PRODUCTION endpoint whose request model is a strict Pydantic model (extra fields dropped) cannot tag those rows with `stress_seed`/`stress_prefix`. Both the unified cleanup sweep and the seed-time cross-prefix orphan scrub filter on `stress_seed=True`, so they NEVER delete such rows. If the endpoint also soft-deletes (sets `active:false` instead of removing) and a spec reads with `include_inactive=true`, the untagged rows accumulate across every run.

Failure shape: a list-back / "our_seen=N/M" check silently drops fresh rows once the collection crosses a list cap (e.g. `.sort(...).to_list(200)`), because hundreds of stale rows crowd the sorted page. Looks like a visibility/backend bug; it is test-harness residue.

**The fix is NOT to loosen the spec assertion.** Add the collection to BOTH tenant-scoped wipe sites in `backend/domains/admin/router/stress.py`:
- seed-time `orphan_cleanup` block: `delete_many({"tenant_id": stress_tid})` BEFORE the tagged seed re-inserts (wipe-then-insert keeps baseline seed rows) — gives an immediate same-run drain, no 1-run lag.
- cleanup endpoint: add the collection name to the `CURRENCY_RATES_TENANT_SCOPED` exception set so teardown full-wipes it and cleanup#2 stays idempotent (empty → deleted_count=0).

**Why:** this is the same documented pattern already used for currency_rates, performance_reviews, reservation_waitlist, recipes, inventory_items, payroll_runs/revisions — all created via strict production POSTs in the stress tenant. Safe because cleanup gates already enforce stress-tenant-only + pilot-blocked + destructive flag, and the wipe is `tenant_id=stress_tid` scoped.

**How to apply:** when a stress spec's data-state finding (empty list, our_seen<floor, stale residue) involves a collection it populates via a production POST rather than the seed builder, check whether the rows carry stress tags before assuming a backend bug. Untagged → add to the tenant-scoped wipe set, don't seed and don't weaken the assert.

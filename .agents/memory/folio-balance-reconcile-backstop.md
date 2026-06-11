---
name: Folio balance reconciliation backstop
description: Why the open-folio balance backstop reconciles against charges/payments (not folio_ledger) and must use get_system_db()
---

# Folio balance reconciliation backstop

A fail-safe backstop reconciles each OPEN folio's cached `folio.balance`
against the authoritative total and (apply mode, env-gated) repairs it.

## Authoritative source = charges − payments, NOT folio_ledger
`folio.balance` is a CACHE. Its authoritative value is the EXACT formula
that SETS it — `core.utils.calculate_folio_balance` /
`pos_folio_consumer._recalc_folio_balance`:

    SUM(folio_charges.total||amount WHERE voided == False)
  - SUM(payments.amount            WHERE voided == False)   (round 2)

**Why:** the POS hot path applies charges asynchronously via the
Outbox/Compensation ("B") consumer, which writes `folio_charges`/`payments`
and recomputes `folio.balance` — it NEVER writes `folio_ledger`. So
reconciling against the immutable `folio_ledger` audit stream (what the
existing `ReconciliationEngine` does) MISSES exactly the B-path cache drift
this backstop targets. The two are complementary: ledger-vs-balance =
audit integrity; charges/payments-vs-balance = operational B safety net.

**How to apply:** mirror the `voided == False` match and the
`$ifNull[total,amount]` fallback EXACTLY. Using `voided: {$ne: True}` would
include legacy field-less docs and compute a different total than B did →
false drift.

## In-process background job must use get_system_db()
The scheduler runs in-process with no HTTP request, so there is no tenant
context. The tenant-scoped proxy `from core.database import db` raises
`STRICT_TENANT_MODE=true ... distinct on tenant-scoped collection 'folios'
without tenant context is forbidden`. Use
`from core.tenant_db import get_system_db` and `db = get_system_db()` for the
cross-tenant scan/repair (same root cause as WS-auth + super-admin
cross-tenant routes). The repair update is still explicitly filtered by
`tenant_id` AND `status == "open"` so blast radius stays 0.

**Why:** verified live — the first restart logged the STRICT_TENANT_MODE
error; switching to `get_system_db()` (returns raw unscoped `_raw_db`,
bypassing the proxy guard) fixed it.

## Drift is real, not a formula artifact (verified)
Live dry-run flagged ~2010 open folios in a STRESS tenant (not pilot) with
charges summing far above the stale cached balance (e.g. cached 25 vs
authoritative 1730). That is genuine cache drift by the system's own
contract, surfaced correctly. The pilot tenant scanned clean
(found_total=0) and is never mutated (apply skips it; dry-run is default).

**How to apply:** standalone CLI (`python -m scripts...`) outside `start.sh`
can't reach Atlas (no `MONGO_ATLAS_URI` → localhost refused) — that is an
env quirk, not a code bug; verify against Atlas by exporting
`MONGO_URL=$MONGO_ATLAS_URI`.

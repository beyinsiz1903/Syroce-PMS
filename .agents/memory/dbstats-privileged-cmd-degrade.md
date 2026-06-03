---
name: Infra-stats endpoints must degrade on privileged-command denial
description: serverStatus/collStats are denied on Atlas shared tiers; a blanket try/except turns the whole endpoint into a 500. Guard each sub-call, return 200 + partial.
---

# Infra-stats endpoints must degrade on privileged-command denial

An admin/system stats endpoint that calls privileged Mongo commands
(`db.command('serverStatus')`, `collStats`, index/collection optimizers) works in
a self-hosted dev Mongo but FAILS on Atlas shared tiers (M0/M2/M5), which restrict
`clusterMonitor`-level commands. If those calls sit under one blanket
`try/except: raise HTTPException(500)`, a single denied command collapses the
entire endpoint into a 500 — and a stress RBAC matrix that expects the route's
any-auth roles to get 2xx then logs it as a REVIEW.

**The fix is NOT to change the spec's RBAC expectation.** If the route is
`Depends(get_current_user)` (any-auth by design), `expectAuthorized: ROLES` is
correct; forcing the spec to super-admin-only would mask the 500 and fake the RBAC
posture. Instead, isolate each privileged sub-call in its own try/except, collect
failures into a `degraded[]` list, and return 200 with whatever succeeded (same
guarded-return posture as the audit-logs / hr-staff read hardening).

**Why:** the REVIEW looks like an RBAC question but is really a tier-availability
question; the privileged command is denied, not the user.

**How to apply:** any read endpoint that surfaces DB/server internals must assume
each privileged command can be denied per-deployment and degrade gracefully.
Verifying the happy path live in dev can be blocked separately — `get_collection_stats`
iterating many accumulated dev collections can take >90s; that latency is
pre-existing and not added by the per-sub-call wrapping.

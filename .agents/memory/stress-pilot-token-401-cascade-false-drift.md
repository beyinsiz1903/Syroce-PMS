---
name: Stress pilot-token 401 cascade = false pilot_drift, not a code regression
description: How to triage a stress run where a cluster of failures is all cached-token 401 plus a negative pilot_drift, and why it is usually CI env/auth-state, not the pushed code.
---

# Signature

A stress run flips from a known GREEN baseline to a handful of failures that ALL
share one root: a cached principal token (typically the pilot super_admin token,
and at teardown the stress token too) starts returning **401** partway through
the run. It cascades into unrelated-looking specs:
- LLM-diagnostics / AI dry-run setups 401
- eod-report pilot preview 401
- cross-tenant probes that expected 404 get **401** instead
- a "Pilot drift = 0" assert fails with `after=undefined` and a negative drift
- teardown: `cleanup#1 status=401`, `cleanup#2 idempotent=false (deleted_counts={})`,
  `pilot_drift=-N (baseline=M after=undefined)`

# Why the negative pilot_drift is a FALSE alarm here

`after=undefined` is the tell. The drift step computes `before - after`; when the
pilot **count read itself 401s**, `after` is undefined/0, so drift comes out as
`-baseline` (e.g. -30/-31). That is a failed READ, not 30 deleted pilot bookings.
A real pilot mutation would show a concrete smaller number, not `undefined`.
**Do not treat this as a pilot_drift doctrine breach without confirming** the
pilot tenant row counts are actually intact (read-only) — the cascade fakes it.

# The decisive triage (do this BEFORE patching anything)

`git diff --name-only <green-baseline-sha>..HEAD` and check TWO things:
1. **e2e-stress specs/helpers/global-setup/global-teardown unchanged?**
2. **backend auth/security/token/login code unchanged?**

If BOTH are unchanged, the exact spec+auth combination that went GREEN is intact,
so a 401 cascade is **CI env / auth-state / token-lifetime**, NOT a regression
from the pushed commits (SPA-serving, room-search, frontend, CI-yaml, lockfile
changes cannot produce a backend 401). Do NOT patch backend auth, do NOT weaken
anything, do NOT promote/demote the baseline — the green baseline stays current.

# Likely causes & next step (operator-side, re-run to confirm)

Run duration vs `JWT_EXPIRATION_MINUTES` is the first suspect, but rule it out if
the green baseline run was as long or longer (same TTL, longer green run => not
pure expiry). Then suspect a token-INVALIDATION event: a jti landing in
`revoked_tokens`, a Redis pub/sub auth-invalidation, or pilot-account state left
by a prior run's 2FA/logout/teardown. Resolution is environmental: re-dispatch
the suite (agent cannot dispatch full stress). If it reproduces, open the
trace.zip / error-context for the FIRST 401 to find the invalidation trigger.

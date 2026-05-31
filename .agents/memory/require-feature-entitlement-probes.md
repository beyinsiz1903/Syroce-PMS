---
name: require_feature entitlement probes
description: How to gate stress/test surfaces on a real feature-flag entitlement without false positives.
---

# require_feature entitlement probes

When a backend write surface is gated by `require_feature("<flag>")`, a stress/E2E
spec that wants to exercise it must verify the *target tenant* actually has the
flag — and must do so with that tenant's own token.

**Why:** `super_admin` (and similar bypass roles) pass `require_feature`
unconditionally. Probing entitlement with a super_admin token is a false positive:
the surface looks "entitled" but a normal tenant token would 404. Always probe with
the real (non-bypass) tenant token.

**Opt-in extra features** (in `core/helpers.py` `OPT_IN_EXTRA_FEATURES`) belong to no
subscription plan, so they default OFF and a per-tenant `features` override is the
*only* way to grant them. If `resolve_tenant_features` doesn't special-case opt-in
keys, a `features.{flag}=true` override is silently dropped (the key isn't in any
plan) and the override appears to do nothing.

**How to apply:**
- Add a tiny read-only `entitlement-check` GET behind the same `require_feature`
  dependency; the spec probes it with the stress token and hard-gates the lifecycle
  on a 2xx. Non-entitled -> honest REVIEW + remediation script (no skip-as-pass).
- Grant the flag for the stress tenant via the stress seed endpoint (idempotent,
  stress-only, fail-soft) plus a standalone operator script (pilot-guarded).

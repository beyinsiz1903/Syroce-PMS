---
name: Stress/E2E test-auth bypass rules
description: How to safely add a test-only auth bypass for the stress suite without weakening prod or risking pilot drift.
---

# Stress/E2E test-auth bypass rules

When the stress suite needs to exercise a normally-protected webhook/endpoint
(e.g. Exely IP-allowlisted webhook), add a **multi-condition fail-closed** test
bypass — never reuse the single-flag dev escape hatch the operator forbids
(e.g. `ALLOW_UNAUTHENTICATED_*`).

## Rule 1 — bypass gate must be multi-condition + fail-closed
Activate ONLY when ALL hold at once: a dedicated `*_TEST_*_MODE=open_for_testing`
sentinel, env is NOT prod, `E2E_EXTERNAL_DRY_RUN=true`, `E2E_ALLOW_DESTRUCTIVE_STRESS=true`,
and `E2E_STRESS_TENANT_ID` set. Any single missing/blank condition → closed.
**Why:** one stray env var must never open the surface in production.

## Rule 2 — removing transport auth also removes tenant protection; re-bind it
If the bypassed control was the thing enforcing the tenant boundary (an IP
allowlist usually fronts a single tenant's provider), the bypass silently opens
**every** tenant mapped in that non-prod deployment — including pilot.
After resolving tenant server-side, **hard-bind** it: `resolved_tenant ==
E2E_STRESS_TENANT_ID` else reject (404/403 + audit). Keep this in a pure helper
so it is unit-testable without DB.
**Why:** architect caught exactly this gap — "tenant resolved server-side" alone
does NOT guarantee pilot-drift-impossible once the allowlist is gone.
**How to apply:** any new test bypass that drops a per-tenant transport guard
must add the explicit stress-tenant binding in the same change.

## Rule 3 — stress suite has TWO environments; don't confuse them
- **CI runner** (`stress.yml`, Playwright): only test-side values live here
  (e.g. HMAC secret used to sign outbound test requests).
- **Stress BACKEND deployment** (operator-controlled, off-repl): this is where
  `KBS_TEST_MODE`, `GRAPHQL_INTROSPECTION`, `EXELY_*`, HotelRunner secret mirror
  are actually read by the backend.
Wiring an env var only on the CI runner does NOT change backend behavior →
"blind runner-env wiring" is fake-green. The agent cannot set backend deployment
env; document it as an operator devops step instead.

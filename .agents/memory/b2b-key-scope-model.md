---
name: B2B API key per-subrouter scope model
description: How B2B agency API-key scopes gate the 12 b2b_api subrouters; the legacy fail-open vs scoped fail-closed contract.
---

# B2B API key per-subrouter scope model

Each B2B agency API key may carry a `scopes` field gating which of the 12
b2b_api subrouters it can reach. The canonical scope list + all shared auth
lives in `backend/routers/b2b_api/_scope.py` (`B2B_SCOPES`,
`normalize_scopes`, `authenticate_b2b_agency`).

The scope semantics (do not change without migration):
- `scopes` absent OR `None` -> **unrestricted** (legacy keys keep full access; fail-OPEN, intentional for back-compat).
- `scopes` == a list -> **restricted**; any subrouter not in the list returns **403** (fail-CLOSED).

**Why:** Pre-existing keys had no scopes field; making them fail-closed would
break live agency integrations on deploy. New/explicitly-scoped keys are
least-privilege. Deny happens in the `get_b2b_agency` dependency BEFORE the
usage_count write, so denied calls don't bump usage.

**How to apply:**
- Every subrouter's `get_b2b_agency` must delegate to
  `authenticate_b2b_agency(x_api_key, required_scope="<module>")` — adding a
  new subrouter means adding its name to `B2B_SCOPES` AND wiring the scope.
- `regenerate_api_key` must preserve the prior key's scopes (no silent
  privilege widening on rotate).
- Stress spec 41B test D hard-asserts the matrix (granted->non-403,
  ungranted->403); a 404 there means the route isn't deployed, not a scope
  pass — keep it a REVIEW carve-out, never skip-as-pass.

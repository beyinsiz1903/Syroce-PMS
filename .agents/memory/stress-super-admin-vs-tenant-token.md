---
name: Stress specs — super_admin principal vs tenant-scoped reads
description: Which bearer a stress spec must use for require_super_admin admin endpoints vs tenant-scoped reads, and why mixing them up SKIPs the whole module.
---

A stress spec that hits `require_super_admin` admin-management endpoints with the
stress-tenant admin token gets 403 → its module probe reports `moduleBlocked` →
every dependent test SKIPs (vacuous "blocked", not honest). The fix is to call
those endpoints with the **super_admin principal**, NOT to weaken any RBAC check.

**Token map (from the stress fixtures):**
- `stressRoles.super_admin` — the pilot super_admin (cross-tenant). In CI it equals
  `pilot_token`; locally `role_tokens` may be empty so fall back:
  `stressRoles.super_admin ?? stressTokens.pilot_token`. In an `afterAll` that reads
  the token blob directly, use `tokenBlob.role_tokens?.super_admin ?? tokenBlob.pilot_token`.
- `stressTokens.stress_token` — the **stress-tenant** admin (tenant-level, NOT super_admin).

**Use super_admin token for** `require_super_admin` surfaces:
`/api/admin/tenants`, `POST/DELETE /api/admin/tenants/{tid}/team[/{uid}]`,
`PATCH /api/admin/tenants/{tid}/info`, `/stats`, `/api/admin/users`,
`/api/admin/web-push/metrics`, and any "super-admin baseline" control test.

**KEEP `stress_token` for tenant-scoped reads** — these are accessible by a tenant
admin AND filter by the caller's `tenant_id`: `/api/hr/staff`, salary-history,
`/api/hr/departments`, `/api/hr/system-users`, `/api/security/audit-logs`,
`/api/audit/timeline`, `/api/system/*`, `/api/rbac/*`, `/api/gdpr/*`.

**Why:** using super_admin (whose own tenant is the pilot) on a tenant-scoped read
returns the **pilot** tenant's data, not the stress tenant's — wrong scope, and it
would defeat the test (e.g. looking for the stress tenant's audit entry / HR rows).
Conversely using the tenant admin on a super_admin endpoint just 403s and blocks
the module. Negative-matrix tests still use the low-priv `roleTokens` (created via
team-create as super_admin) and asserting 403/404 there is the CORRECT RBAC outcome,
not a failure to mask.

**How to apply:** capture a module-scoped `let superToken = null;`, set it once at
the top of the spec's `Setup` test (`superToken = stressRoles.super_admin ?? stressTokens.pilot_token`),
add `stressRoles` to the Setup fixture signature, and swap only the admin-management
calls. Pilot-drift stays 0 because all mutations target the stress tenant id.

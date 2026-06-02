---
name: Super-admin cross-tenant admin endpoints need get_system_db
description: Why require_super_admin per-tenant admin routes 403 "Yetkisiz islem" and how to fix without weakening isolation
---

# Super-admin cross-tenant admin endpoints must use get_system_db()

A `require_super_admin` endpoint that operates on a path-bound `{tenant_id}` OTHER than the
caller's own tenant will fail with **403 `{"detail":"Yetkisiz islem"}`** if it uses the
tenant-scoped `core.database.db` proxy.

**Diagnostic shortcut:** `403 "Yetkisiz islem"` is the `@app.exception_handler` for
`core.tenant_db.TenantViolationError` (server.py). It is NOT an RBAC/permission denial and NOT
`require_super_admin` (that path 404s non-super principals). If you see this 403 on a super_admin
admin route, suspect a scoped-proxy cross-tenant read/write, not an auth gate.

**Why:** `TenantContextMiddleware` sets the request tenant context ONLY from the caller's JWT
`tenant_id` claim (no `X-Tenant-Id` header override). The super_admin's own tenant becomes the
context. The scoped proxy's `_inject_doc`/`_inject_filter` then raise `TenantViolationError` on any
explicit foreign `tenant_id` (insert `{tenant_id: <target>}` or filter `{"tenant_id": <target>}`).
So such endpoints structurally cannot manage any tenant except the super_admin's home tenant. No
principal is both super_admin AND scoped to the target tenant, so there is no token-only workaround.

**How to apply:** For `require_super_admin` endpoints whose target tenant comes from the validated
path and whose every query already carries an explicit `tenant_id`, use `get_system_db()` (raw
unscoped db) — the documented pattern for "cross-tenant admin queries" (`get_system_db` docstring;
`routers/auth.py` does `db = get_system_db()` module-wide; `domains/admin/router/stress.py` uses it).
Keep the module-level scoped `db` for all other (own-tenant) endpoints. Authorization stays enforced
by `require_super_admin`; isolation is preserved by the explicit per-query `tenant_id`.

**Corollary — email is globally unique:** login resolves users by email via the system db
(`auth.py`), so any team-member email-duplicate check MUST be global. A scoped dup-check (the old
behavior) only sees the caller's tenant and can admit a global collision that later breaks login.

**How this surfaced:** masked for a long time behind an earlier 422 (a stress spec used the RFC 6761
reserved `.test` TLD; `EmailStr` rejected it before the request reached the insert). Fixing the email
domain unmasked the latent 403. Lesson: when a validation/spec fix "moves" an error, the new error
may be a real latent bug the old failure was hiding — don't assume the second error is also spec drift.

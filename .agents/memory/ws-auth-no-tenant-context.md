---
name: WebSocket auth has no tenant context
description: Why WS auth/bookkeeping DB lookups must not go through the tenant-aware proxy, and how isolation is still enforced
---

# WebSocket auth runs with NO tenant context

`TenantContextMiddleware` is HTTP-only — it bails on any non-`http` ASGI scope and
only sets the per-request tenant contextvar for HTTP. WebSocket connections never
traverse it, so inside a WS handler/hub the tenant contextvar is unset.

Consequence: any `db.<tenant_scoped_coll>.<dataop>()` through the tenant-aware
proxy during a WS connection returns a `SchemaOnlyCollection` under
`STRICT_TENANT_MODE=true`, whose data ops raise `TenantViolationError`. A broad
`except` in the auth path then silently turns that into "auth failed" — so EVERY
valid token is rejected at the WS handshake. This is invisible in soft mode
(default `STRICT_TENANT_MODE=false` returns the raw collection), so it only bites
after strict mode is enabled in an env (e.g. a deployed stress/prod backend).

**Rule:** WS auth's user lookup must use `get_system_db()` (raw/unscoped) — the
tenant is being *derived from* the token, so it cannot be known before the
lookup. After the lookup, bind the connection's task with
`set_tenant_context(user_ctx['tenant_id'])` so later same-task tenant-scoped
writes (e.g. `ws_connection_log` in connect/disconnect) don't raise.

**Why this is NOT auth/isolation weakening:** the unscoped lookup is immediately
followed by the explicit consistency checks that already existed and stay intact —
refresh-type rejection, jti revocation, `tokens_invalid_before` watermark, reject
orphan docs with no `tenant_id`, and reject `jwt_tenant != doc_tenant`. A forged
or cross-tenant token still cannot connect as another tenant; this is
equivalent-or-stronger than the REST path (which relies on middleware pre-scoping
plus the same explicit check).

**How to apply:** any context-less surface (WS hubs, workers, startup) that needs
a tenant-scoped collection must use `get_system_db()` / `get_db_for_tenant()` and
enforce tenant identity explicitly — never assume the request middleware scoped it.

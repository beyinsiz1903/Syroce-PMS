---
name: HotelRunner webhook cryptographic tenant binding
description: Why inbound HR webhook tenant must come from the secret-owning connection, not client input; per-property secret namespace.
---

# HotelRunner inbound webhook: cryptographic tenant binding

The processed tenant for an inbound HotelRunner webhook MUST be derived from
the connection whose per-property secret verifies the HMAC, bound onto
`request.state.hr_webhook_tenant_id`. Endpoints prefer that bound value over
any client-supplied `X-Tenant-ID` / query / body tenant.

**Why:** the old code trusted client-supplied tenant and had an insecure
"first active connection" fallback — an attacker who knew/guessed a tenant_id
(or any single-tenant deployment) could forge create/modify/cancel events for
an arbitrary tenant. Trusting the secret owner closes the cross-tenant forge.

**How to apply:**
- Per-property secret (SecretsManager) wins; global `HOTELRUNNER_WEBHOOK_SECRET`
  is backward-compat fallback only; neither set → 503 fail-closed
  (`ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK=1` is the only escape).
- The "first active connection" fallback in tenant resolution is REMOVED — do
  not reintroduce it.
- Every rejection writes a security log (reason + source_ip + untrusted hints),
  NEVER the secret/signature material.
- Webhook secrets live in a separate namespace `"<provider>_webhook"` (field
  `webhook_secret`), distinct from API token creds, so rotating one never
  touches the other. SecretsManager metadata persists to Mongo, so a live
  dev roundtrip needs Mongo running (unit tests monkeypatch the lookup/load).
- Signature helper stays defensive (`getattr` for query_params/client/state)
  so the locked signature unit tests (partial request shims) keep passing.

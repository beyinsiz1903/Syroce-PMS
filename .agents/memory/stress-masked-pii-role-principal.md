---
name: Stress masked-PII needs a role lacking the gating permission
description: Why proving a permission-masked response path live requires a dedicated low-permission principal, plus the messaging delivery-log seeding gotcha.
---

To hard-assert a *masked* (PII-redacted) response branch end-to-end through the
live API, the test principal must LACK the gating permission. Tenant admin and
pilot super_admin both bypass permission checks (always see unmasked), so they
can only prove the *visible* branch, never the masked one.

**Why:** The messaging activity feed masks the guest recipient for roles without
`view_guest_list` (VIEW_REPORTS) and shows it raw otherwise. The pre-existing
"low-trust" stress principal is a `front_desk` user — but front_desk HOLDS
view_guest_list, so it sees unmasked data exactly like admin. A `housekeeping`
principal (no VIEW_REPORTS) is required to exercise the masked branch.

**How to apply:** When a stress/e2e spec must prove a permission-masked or
permission-denied path, check the actual ROLE_PERMISSIONS map first
(`backend/models/enums.py` ROLE_PERMISSIONS + `modules/pms_core/
role_permission_service.py`). Don't assume "low-trust staff" lacks a given perm.
Provision the principal via the real create endpoint in the STRESS tenant only
(no pilot mutation), fail-soft (null token → honest SKIP, never fake-green).

**Seeding gotcha:** the messaging `/send` flow only writes a `messaging_delivery_logs`
row for channels in CHANNEL_PROVIDER_MAP (`email`, `whatsapp`). `in_app` is NOT
mapped → "Unknown channel" → NO log written. To seed an activity-feed row, send
with channel `email`; with no provider config it persists status=failed +
recipient and makes zero external calls (email fallback chain is empty).

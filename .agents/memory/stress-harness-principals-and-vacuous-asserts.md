---
name: Stress harness principals & vacuous assertions
description: Which stress token maps to which role, why require_super_admin probes 404 not 403, and why empty seed sets turn security asserts vacuous.
---

# Stress harness principals & vacuous assertions

## Principal mapping (non-obvious)
- `stressTokens.stress_token` / `role_tokens.stress_admin` = stress-tenant **ADMIN** (NOT global super_admin).
- `stressTokens.pilot_token` / `role_tokens.super_admin` = pilot **super_admin**.
- `require_super_admin` returns **404** (not 403) to a non-super caller. So a stress-admin probe of a super-admin-only endpoint records `auth_404_not_deployed` and looks like a missing route. Probe such surfaces with `pilot_token` or you get a spurious REVIEW.
- ADMIN and SUPER_ADMIN both **bypass all permission checks** (role_permission_service). So neither stress_admin nor a low-trust staff role with `view_guest_list` (e.g. front_desk) is a valid principal to hard-assert PII *masking* — only HOUSEKEEPING-type roles get masked. PII-mask behavior is locked by backend pytest (`test_messaging_activity_pii_rbac.py`), not reachable from the stress harness's available tokens.

**Why:** stress specs kept drifting to REVIEW because they probed super-admin-only ops endpoints (outbox/webhooks/feature-flags) with the tenant-admin token and saw 404.
**How to apply:** for `/api/outbox/status`, `/api/webhooks/status`, `/api/admin/feature-flags` (all require_super_admin) use `pilot_token`; for `get_current_user` surfaces (`/api/lockdown/runtime/cockpit`, `/api/infra/backup/status`) any authenticated token works.

## Vacuous security assertions on empty sets
A cross-tenant-leak / PII-mask assertion over a collection that the seed never populated **trivially passes on the empty set** → the spec records a REVIEW for "empty feed (vacuous assert)" instead of real coverage.

Example: `/api/messaging-center/activity` reads `notifications` where `type=="messaging_automation"` **plus** `messaging_delivery_logs`. F8B only seeded complaint/guest-request notification types and zero delivery logs, so the feed was always empty.

**Why:** an empty result makes the isolation/mask assert meaningless; that is fake-green by omission, not a pass.
**How to apply:** seed the *exact* shape the endpoint reads (here: both `messaging_automation` notifications AND `messaging_delivery_logs` rows) so the assert runs non-vacuously. Use RFC 2606 reserved domains (`.example.com`/`.test`/`.invalid`) and synthetic all-zero phones for recipients — never real PII. The free-text-PII check in spec 45 exempts those reserved domains.

## Endpoint contract gotchas (verified)
- `/api/messaging/conversations` returns `{ messages: [...], count }` — NOT a `conversations`/`items` field; same-tenant raw recipient is by-design (staff need contact info), so only assert tenant isolation, not masking.
- `/api/infra/backup/status` returns `last_successful` (dict with `started_at`/`completed_at`) + `enabled` + `history_count`; `enabled===false` is an expected posture (no timestamp), distinct from shape drift.

# REVIEW/SKIP Zeroing — Package D Candidate Drill

**Date:** 2026-05-30
**Baseline:** Run #168 (official GREEN BASELINE, commit `52575268c025d97ce67b409d187b041283c74064`). **Pointer NOT moved.**
**Status:** Candidate (CI-deferred — full stress dispatched by operator; agent ran targeted checks only).
**Companion:** `docs/drill_reports/20260530_review_skip_package_d_inventory.md` (per-surface classification with file evidence).

## Doctrine compliance

- No fake-green, no broad RBAC grant, no auth weakening, no PII exposure, no pilot mutation, external_calls=[] preserved.
- Baseline pointer #168 NOT moved; full stress NOT run (operator dispatch); no mobile/F10.
- No blind stub added; no backend code touched (spec-only change).

## What changed (single safe fix)

**`frontend/e2e-stress/specs/96-cross-tenant-pentest.spec.js`** — `messages` surface list path drift corrected:

- `'/api/messaging/messages?limit=50'` → `'/api/messaging/conversations?limit=50'`.
- Reason: `/api/messaging/messages` has no backend route; the real messaging list surface is `/api/messaging/conversations` (`backend/domains/guest/messaging/router.py`, prefix `/api`, L303). The drift made the pentest mark the surface blocked (404) → the cross-tenant leak scan never ran (vacuous) and left a standing P2 `surface_blocked:messages`.
- Stress-token reachability of `/api/messaging/conversations` is already proven by `13-messaging.spec.js` § B. `itemArray()` (L77) already handles the `conversations` response key.

## Why it is safe (cannot regress the baseline)

- `withModuleProbe` degrades gracefully on any non-2xx: a blocked surface produces a **P2 informational**, never a FAIL. So the change cannot introduce a FAIL.
- Best case (expected): `/api/messaging/conversations` is reachable and tenant-scoped → the leak scan runs and PASSes → one P2 `surface_blocked:messages` clears, and the messaging surface gains **real cross-tenant leak coverage** (strengthening).
- Worst case: same blocked-P2 as today. No net negative.
- If a genuine cross-tenant leak existed on the real endpoint, the pentest would now correctly surface P0 — that is the intended security value, not fake-green.

## Verification performed (targeted only)

- `node --check` PASS on `96-cross-tenant-pentest.spec.js`, `13-messaging.spec.js`, `98B-websocket-tenant-isolation.spec.js`, `31-settings-audit.spec.js`.
- Grep confirms no remaining `/api/messaging/messages` call sites (only the explanatory comment).
- Backend route existence confirmed by code read: `domains/guest/messaging/router.py` exposes `/messaging/send-email|send-sms|send-whatsapp|conversations` under prefix `/api` → `13-messaging.spec.js` paths are correct (NOT drift) and `/api/messaging/conversations` is valid.

## Expected next-run delta (to validate on operator dispatch)

- P2 / REVIEW: one fewer `surface_blocked:messages` (P2) if `/api/messaging/conversations` is reachable under the stress token (expected).
- PASS: +1 messaging cross-tenant surface now actually scanned.
- FAIL/P0/P1: unchanged at 0 (no FAIL risk by construction).
- external_calls=[], pilot_drift=0 unchanged.

## Items deliberately NOT changed (CONFIRM-BY-DESIGN / ROADMAP)

See inventory doc §1-§8. Summary: super_admin fail-closed 404s (admin/tenants, feature-flags, webhooks/dlq, outbox/status, global user-create), EntitlementMiddleware 403 (spa/mice), HMAC-gated public QR, env-only QR rotation (no HTTP route), and the enterprise_live WS mount (unconditionally mounted; spec 404-fallback is defensive). None are bugs; making any of them 2xx would weaken auth or add a stub — forbidden.

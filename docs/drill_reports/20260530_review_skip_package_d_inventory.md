# REVIEW/SKIP Zeroing — Package D Inventory & Classification

**Date:** 2026-05-30
**Baseline:** Run #168 (official GREEN BASELINE, commit `52575268c025d97ce67b409d187b041283c74064`).
**Scope:** Endpoint / Surface / Module-blocked REVIEW/SKIP reduction over web/backend Full Stress Suite.
**Hard rules honored:** no fake-green, no broad RBAC grant, no auth weakening, no PII exposure, no pilot mutation, external_calls=[], baseline pointer #168 NOT moved, full stress NOT run (operator dispatches; targeted checks only), no mobile/F10.

Classification legend: **SPEC-DRIFT-FIX** | **SEED/HARVEST-FIX** | **CONFIRM-BY-DESIGN** | **ROADMAP/BACKLOG** | **OPERATOR-ENV**.

---

## 1. admin/settings surface 404 — CONFIRM-BY-DESIGN

- `/api/admin/tenants` (`backend/domains/admin/router/tenants.py`), `/api/admin/feature-flags` (`backend/domains/admin/entitlement_router.py`) are mounted but return **404** to non-super-admin via `require_super_admin_guard(not_found=True)` (`backend/core/helpers.py` L252). 404-not-403 is deliberate existence-hiding (Wave 8 doctrine, category 8 by-design).
- The stress admin token is intentionally **tenant-scoped, not platform super_admin**, so these 404s are correct. Making them 2xx = auth weakening = FORBIDDEN.
- `/api/admin/settings-audit` is genuinely absent; the real audit surfaces are `/api/audit/timeline` and `/api/security/audit-logs`. Spec `31-settings-audit.spec.js` **already uses the correct audit paths** (L116-117) and degrades gracefully when `/api/admin/tenants` probe is non-2xx (moduleBlocked → P2 informational, A/B/C/D skip, F pilot_drift still enforced). **No drift, no fix.**

## 2. webhook_admin_dlq surface — CONFIRM-BY-DESIGN

- `/api/webhooks/status`, `/api/webhooks/dlq` (`backend/routers/webhook_admin.py`), `/api/outbox/status` (`backend/routers/outbox_admin.py`) are mounted, super_admin-gated → 404 to tenant-scoped stress admin (same fail-closed obscurity as §1).
- `/api/admin/cm/outbox/stats` appears only inside **candidate-fallback lists** in `00-gates.spec.js` L76 and `01-bulk-seed-500.spec.js` L138 (specs try several paths and degrade gracefully). The real `/api/outbox/status` is itself super_admin-gated, so adding it to the candidate list would still 404 for the stress admin — no behavioral gain. **Honest leave, no fix.**

## 3. digital-key / QR rotation surface contract — CONFIRM-BY-DESIGN + ROADMAP(env-only)

- Digital key is REAL: `GET /api/guest/digital-key/{booking_id}` + `POST /api/guest/digital-key/{booking_id}/refresh` (`backend/domains/guest/operations_router.py`), JWT + email-owner match, status-gated.
- Room QR rotation is **env-only** via `ROOM_QR_SECRET` (`backend/routers/room_qr_requests.py`); there is intentionally **no HTTP rotation route** (rotating a secret over HTTP would be a security liability). Spec `63-public-token-rotation.spec.js` already documents "intentionally absent (env-only)" and verifies the fail-closed contract. **No fix.**

## 4. ws_tenant_isolation / enterprise_live mount decision — CONFIRM-BY-DESIGN

- `routers.enterprise_live` is **unconditionally mounted** (`backend/bootstrap/router_registry.py` L65, in `_EXTRACTED_ROUTERS`, no env/flag gate). WS endpoint `/api/enterprise/ws/live` is real (`backend/routers/enterprise_live.py` L86); tenant_id is derived DB-authoritatively in `WebSocketHub` (`backend/modules/platform_scaling/websocket_hub.py`).
- Spec `98B-websocket-tenant-isolation.spec.js` L190-203: the "HTTP GET 404 → enterprise_live router mount yok" branch is a **defensive module-block fallback** that does not trigger when the router is mounted (a WS route returns 426/405 to a plain GET, not 404), so the real A/B/C isolation probes run. **No change needed; defensive fallback is correct as-is.**

## 5. marketplace endpoint 404 leftovers — CONFIRM-BY-DESIGN

- Both marketplace surfaces are mounted: `/api/module-store` (`backend/routers/marketplace.py`) and `/api/marketplace` (`backend/routers/marketplace_b2b.py`, `backend/domains/pms/marketplace_router.py`). 404s on restricted endpoints are super_admin-guard misclassification (same as §1), not missing mounts. **No fixable leftover.**

## 6. spa catalog 403 module-blocked posture — CONFIRM-BY-DESIGN

- `/api/spa/*` (`backend/domains/spa/router.py`) and `/api/mice/*` (`backend/routers/mice.py`) are gated by `EntitlementMiddleware` (`backend/core/entitlement.py`, `ROUTE_MODULE_MAP`), returning **403 ENTITLEMENT_DENIED + upgrade_url** when the module is not in the tenant plan/subscription. 403 (known-but-unpaid) is the correct module-blocked posture — distinct from the §1 super_admin 404 (existence-hiding). **Correct by design.**

## 7. public token rotation / blocked room harvest — CONFIRM-BY-DESIGN

- Public room-QR (`GET/POST /api/public/room-qr/{tenant_id}/{room_id}`) is HMAC-token gated (`ROOM_QR_SECRET`); enumeration/harvest is blocked without a valid token, and guest name is PII-masked in the GET. Review invites use high-entropy `uuid4().hex` single-use tokens. **Correct security posture.**

## 8. HR RBAC per-role user creation 404 — CONFIRM-BY-DESIGN

- HR user creation is mounted under `require_op("manage_hr")` (`backend/domains/hr/router.py`); global per-role user creation (`backend/domains/admin/router/users.py`) is a super_admin task → 404 to tenant admin (same fail-closed obscurity as §1). **Correct by design.**

---

## Actionable outcome (only safe fix)

**SPEC-DRIFT-FIX — `frontend/e2e-stress/specs/96-cross-tenant-pentest.spec.js` L61 (`messages` surface).**

- Before: `list: '/api/messaging/messages?limit=50'` — this path does **not** exist in the backend. There is no router with prefix `/api/messaging` exposing `messages`; the only messaging routers are `routers/messaging.py` (`/api/messaging-center`) and `domains/guest/messaging/router.py` (`/api`). The drift caused `withModuleProbe` to mark the `messages` surface **blocked (404)**, so the cross-tenant leak scan for messaging **never ran** = vacuous pentest surface + a standing P2 `surface_blocked:messages`.
- After: `list: '/api/messaging/conversations?limit=50'` — the real messaging list surface (`domains/guest/messaging/router.py` L303, prefix `/api`). Stress-token reachability is already proven by `13-messaging.spec.js` § B (which GETs `/api/messaging/conversations?limit=100` with the stress token successfully). The spec's `itemArray()` already handles the `conversations` response key (L77).
- Safety: `withModuleProbe` degrades gracefully on any non-2xx (blocked → P2 informational, never FAIL), so this change **cannot introduce a FAIL** into the green baseline. Best case: a previously-blocked surface becomes real cross-tenant leak coverage (strengthening, not fake-green) and one P2 clears. Worst case: same blocked-P2 as before. No RBAC change, no auth weakening, no pilot mutation, no stub.

### Non-actionable summary

| # | Surface | Classification |
|---|---------|----------------|
| 1 | admin/settings 404 | CONFIRM-BY-DESIGN (super_admin fail-closed 404); audit spec already uses real paths |
| 2 | webhook_admin_dlq | CONFIRM-BY-DESIGN (super_admin 404; candidate-fallback lists honest) |
| 3 | digital-key / QR rotation | CONFIRM-BY-DESIGN (digital-key real) + ROADMAP (QR rotation env-only, no HTTP route) |
| 4 | ws_tenant_isolation / enterprise_live | CONFIRM-BY-DESIGN (mounted; spec 404-fallback defensive, isolation probes run) |
| 5 | marketplace 404 leftovers | CONFIRM-BY-DESIGN (mounted; super_admin-guard misclassification) |
| 6 | spa catalog 403 | CONFIRM-BY-DESIGN (EntitlementMiddleware module-blocked 403 + upgrade_url) |
| 7 | public token rotation / room harvest | CONFIRM-BY-DESIGN (HMAC-gated, PII-masked, harvest blocked) |
| 8 | HR RBAC per-role user creation | CONFIRM-BY-DESIGN (manage_hr mounted; global create super_admin 404) |

**Net:** 1 safe SPEC-DRIFT-FIX (96-pentest messaging surface), 7 CONFIRM-BY-DESIGN, 1 ROADMAP note (QR rotation env-only). No stub added, no backend code touched, no RBAC/auth change.

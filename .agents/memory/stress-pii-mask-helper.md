---
name: assertPiiMasked field-key limitation + activity-feed PII vector
description: Why passing free-text field names to assertPiiMasked is a no-op, and the genuine activity-endpoint RBAC/PII gap.
---

# `assertPiiMasked` only detects PII by known field-key + pattern

`frontend/e2e-stress/fixtures/stress-helpers.js` `assertPiiMasked(testInfo, module, body, fields)`
delegates to `looksLikePlainPii(field, value)`, which **only** recognizes a hardcoded
set of field names: `identity_number` (11-digit TC), `phone`, `email`, `passport_no`, `iban`.

**Rule:** passing any other field name (e.g. `recipient`, `message`, `note`) to
`assertPiiMasked` does **nothing** — it silently no-ops and gives a *false impression
of coverage*. To check PII inside an arbitrary free-text string field you must do a
local regex scan in the spec (or extend the helper's pattern logic), not just add the
field name to the `fields` array.

**Why:** caught during Wave 8 REVIEW/SKIP zeroing (architect round-2). A spec claimed
to mask `recipient`/`message` by adding them to the fields list; the assertion was
vacuous.

**How to apply:** when a payload embeds PII inside free-text (not as a structured
key matching the known names), write an explicit regex scan. For stress data, exempt
synthetic test domains (`.invalid`/`.test`/`.example`) and keep real-domain matches at
**REVIEW severity** unless you are certain real domains can never legitimately appear —
demo seeds sometimes embed real-domain emails by design (false-P0 risk on hard-fail).

# Genuine activity-feed RBAC/PII gap (Wave 9 candidate)

`GET /api/messaging-center/activity` (`backend/routers/messaging.py`) is guarded only
by `get_current_user`, while `GET /api/messaging-center/delivery-logs` requires
`require_op("view_guest_list")`. The activity feed embeds the recipient inside each
item's free-text `message` (`"{recipient} — {use_case}"`), and the messaging demo
seed (`_get_demo_delivery_logs`) uses real-domain (`@gmail.com`) recipients.

**Net:** activity exposes recipient PII without the guest-list gate that delivery-logs
enforces. This is a product-contract / RBAC decision (add the op-gate, or mask/redact
recipient in the activity payload), **not** a test-drift item. Deferred to Wave 9.

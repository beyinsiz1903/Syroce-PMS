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

# Sibling endpoints over the same PII must share the same RBAC gate (RESOLVED)

`GET /api/messaging-center/activity` and `GET /api/messaging-center/delivery-logs`
(`backend/routers/messaging.py`) both surface the recipient (guest email/phone), but
activity originally only required `get_current_user` while delivery-logs required
`view_guest_list` (VIEW_REPORTS). Activity embeds recipient inside a free-text
`message` (`"{recipient} — {use_case}"`), so the looser gate leaked PII to roles like
HOUSEKEEPING.

**Resolution:** activity now masks the recipient via a local `_mask_recipient` helper
unless the caller holds `view_guest_list` (checked through `RolePermissionService`).

**Why:** when two endpoints expose the same sensitive field, the weaker gate defines the
real exposure — auditing only the "obvious" PII endpoint misses the sibling.

**How to apply:** when adding/auditing an endpoint that returns guest contact data, grep
for sibling endpoints over the same collection/field and confirm they enforce the *same*
permission; visibility must gate on a permission, not merely on authentication. Masking
in-payload (vs 403) is the right tool when the row itself is legitimately listable but a
single field is sensitive.

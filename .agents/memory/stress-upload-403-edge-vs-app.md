---
name: Upload-security 403 = edge WAF, not app
description: Malicious-upload stress FAIL where status=403 instead of app's 400 — it's the deploy edge proxy, a stricter reject, not a regression.
---

When the file-upload-security stress spec FAILs with status **403** on `<script>`/`<html>`/`<svg>`
payloads (svg_mime, html_as_pdf_polyglot, html_as_png_polyglot, svg_as_image) but the
app code returns **400/413**:

- The app has NO content-WAF — verify with a localhost probe: unauth `<script>` body → 401
  (same as benign), never 403. App rejects malicious content with 400 (bad MIME / magic-bytes)
  or 413 (oversized). Backend unit tests (test_upload_validator_document.py) confirm.
- The stress suite runs against a **deployed target** (STRESS_E2E_BASE_URL) behind Replit's
  edge proxy. The edge WAF intercepts request bodies containing `<script>/<html>/<svg>` and
  returns **403 before the request reaches the app**. Only markup-bearing payloads get 403;
  `MZ`/`%PDF`/oversized/empty (no markup) reach the app and get the correct 400/413.

**Rule:** 403 is a HARD reject (upload denied / never stored) — add it to the reject-class for
the markup-bearing cases only. Do NOT add 403 to non-markup cases (scope creep; edge won't 403
them). This is NOT assertion-loosening: a 2xx accept still fails; the same spec already treats
403 as "rejected" for its cross-tenant download steps. **Why:** edge-layer WAF is a stricter
outer defense layer than the app's own validation; both are valid rejections of malicious content.
**How to apply:** can't reproduce edge from the workspace (dev port 8000 isn't edge-mapped →
"Run this app" 404); confirm app-side 400 via code read + unit tests, attribute 403 to edge.

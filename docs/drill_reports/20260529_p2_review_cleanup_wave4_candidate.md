# P2/REVIEW Risk Cleanup — Wave 4 (Candidate Drill Note)

- **Date**: 2026-05-29
- **Status**: CANDIDATE (local backend pytest only; full stress suite NOT run)
- **Official baseline (UNCHANGED)**: Run #161, commit `ba9dfc7aafc0a694b70841d3405f8445ecfc1b67`, 702 test, GO WITH WATCH.
  - Pointer NOT moved. No GO claim. No /100 claim. No P2/REVIEW/SKIP downgrade.

## Scope

Wave 4 continues reducing high-risk P2/REVIEW items by hardening test coverage
(and, where missing, behavior) on four areas. Waves 1-3 already landed the core
code changes; Wave 4 closes the explicit per-area test matrix the operator
requested. The full stress suite will be dispatched later by the operator.

## Area 1 — file_upload_security (HR docs polyglot)

- **Behavior (already in place, Wave 1A)**: `security/upload_validator.py::validate_document_bytes()`
  sniffs real magic bytes (PDF `%PDF-`, OOXML/zip `PK`, OLE `D0CF11E0`, images via
  Pillow) and returns the *detected* canonical content-type. The HR upload route
  (`domains/hr/router.py::upload_staff_document`) persists the detected type, not
  the attacker-declared MIME, and sanitizes filenames at both upload and download.
- **Tests**:
  - `test_upload_validator_document.py` (existing): valid PDF/DOC/DOCX/PNG/JPEG
    accepted; HTML-as-PDF / SVG / executable / plain-text rejected (400); empty
    rejected (400); oversized rejected (413).
  - `test_hr_doc_filename_sanitize.py` (NEW, 7): path traversal → basename,
    leading-dots dropped, CRLF/quote header-injection neutralized, empty→`document`,
    length capped, safe chars preserved.
- **Download content-type safety**: the route serves `media_type=doc['content_type']`
  where `content_type` is the magic-byte-detected value stored at upload — so a
  spoofed `text/html` can never be echoed back.

## Area 2 — GraphQL introspection policy

- **Behavior (Wave 1B)**: `graphql_api/schema.py::_introspection_enabled()` is
  fail-closed for production/stress/staging; explicit `GRAPHQL_INTROSPECTION=true`
  opt-in for local. When disabled, `AddValidationRules([NoSchemaIntrospectionCustomRule])`
  rejects introspection queries.
- **Tests** (`test_graphql_introspection_policy.py`, existing 7): blocked by
  default in prod/stress; allowed only when env explicitly true; normal
  (non-introspection) query still works under the rule. Tenant isolation is
  orthogonal to the validation rule and unchanged (rule only strips `__schema`/
  `__type` meta-fields, never tenant-scoped resolvers).

## Area 3 — rate limit boundary

- **Policy (documented, not guessed)**: `security/auth_throttle.py` enforces
  per-IP and per-account sliding windows (login 20/60s IP, 10/300s account; 2FA
  15/60s `always_on`; etc.). `enforce()` raises HTTP 429 with a `Retry-After`
  header. Security-critical (`always_on`) throttles ignore the dev escape hatch.
- **Tests** (`test_auth_throttle_boundary.py`, NEW 5): burst eventually 429;
  Retry-After header present and >= 1; normal sub-cap usage not blocked; per-key
  (per-IP vs per-account) separation; reset drains the counter. Runs against the
  deterministic in-memory fallback (Redis absent in test env).

## Area 4 — maintenance assets/plans 422

- **Root cause (Wave 2)**: stress spec sent schema-foreign fields
  (`asset_tag`/`category`/`frequency`); the backend schema (which matches the
  frontend) is the source of truth. Spec payloads were aligned — schema NOT
  loosened.
- **Tests**:
  - `test_maintenance_schema_contract.py` (existing 4): valid canonical asset/plan
    accepted; legacy bogus payloads rejected (ValidationError).
  - `test_maintenance_rbac.py` (NEW 5): asset/plan routes registered; POST routes
    tenant-scoped (`get_current_user`) AND RBAC-gated (`require_op("view_system_diagnostics")`);
    GET list routes tenant-scoped.

## Local verification

All sprint backend tests pass together:

```
tests/test_upload_validator_document.py
tests/test_graphql_introspection_policy.py
tests/test_maintenance_schema_contract.py
tests/test_ops_readiness_endpoints.py
tests/test_invoice_tax_id_contract.py
tests/test_guest_anonymization_flag.py
tests/test_hotelrunner_webhook_signature.py
tests/test_marketplace_routes_registered.py
tests/test_hr_doc_filename_sanitize.py     (NEW)
tests/test_auth_throttle_boundary.py       (NEW)
tests/test_maintenance_rbac.py             (NEW)
=> 66 passed
```

## Rules honored

- No fake green: every assertion exercises real code paths (no skip-as-pass).
- No baseline pointer movement; Run #161 remains official.
- No GO / no /100 claim.
- No P2/REVIEW/SKIP downgrade; schema not loosened (spec corrected instead).
- Full stress suite deferred to operator dispatch.

# QR Guest Service Catalogue Architecture

## Overview
The QR Guest Service Catalogue provides a property-configurable, multilingual, and strict-typed service selection layer for guests. It operates alongside the existing mandatory free-text Room QR request flow.

## 1. Data Models
All catalogue configurations are stored in dedicated property-scoped MongoDB collections:
- `guest_service_catalogue_settings`: Global settings per property (`tenant_id`, `property_id`, `mode`).
- `guest_service_departments`: Configurable departments (e.g., Housekeeping, Technical).
- `guest_service_items`: Specific service items mapped to departments.

### Immutable Identifiers
The system exclusively relies on `department_code` and `service_code` for business logic and frontend mapping. These codes are immutable (`^[a-z0-9_]+(\.[a-z0-9_]+)*$`).
**No internal Mongo `_id`s are exposed to the public QR endpoints.**

### Multilingual Validation
Labels and descriptions are strictly validated:
- Language keys must match `^[a-z]{2}(-[A-Z]{2})?$`.
- Values are stripped of whitespace and must not be empty.
- Length bounds: labels up to 100 characters, descriptions/warnings up to 500 characters.

The language resolution fallback is deterministic:
1. `requested language` (e.g., from `lang` query param)
2. `property default language`
3. `"tr"`
4. `"en"`
5. First available non-empty label in alphabetical key order.

## 2. API Design & Security
The read-only public endpoint:
`GET /api/public/room-qr/{tenant_id}/{room_id}/catalogue`

**Security Guarantees:**
- Enforces strict `X-Guest-Session` validation.
- Derives `property_id` and booking scope purely from the verified server-side session.
- Exposes no booking, guest, or occupancy indicators in error responses or generic unavailable fallbacks.
- Index creation and query errors emit sanitized warnings (`group=catalogue_indexes` / `group=catalogue_parse_error`) without logging raw document content, tenant or token data.

## 3. Catalogue Modes and Fallbacks
The system defines explicit mode precedence:
1. **No settings / No records**: Dynamically serves the hardcoded safe template (`default`).
2. **Mode = default**: Explicitly serves the default template, ignoring stored records.
3. **Mode = configured**: Serves valid configured records. If records are partially invalid, they are excluded safely via Pydantic model validation. If no usable valid records remain, it fails closed to a generic unavailable response.
4. **Mode = disabled**: Completely disables the catalogue with a generic unavailable response.

### Default Template Isolation
The `get_default_catalogue()` method always returns a deep-copy of the generic defaults to prevent in-memory cross-tenant contamination.

## 4. Service Filtering Logic
A service is returned to the guest only if all conditions are met:
- The parent department is `enabled`.
- The service itself is `enabled`.
- The parent department explicitly exists in the property's catalogue response.
- The `service_hours` constraint (if configured) allows requests at the current local time relative to the property's configured timezone. 
**Timezone Policy:** If the timezone is malformed or invalid (e.g., cannot be parsed by `zoneinfo`), or if `start == end`, the service strictly fails closed and is hidden.

## 5. Backward Compatibility (PR 1 constraints)
Phase 1 introduces strictly the read-only core and data layer:
- Validates code formats and database uniqueness. Update immutability is not yet enforced (planned for write API PR).
- Existing `room_qr_requests` logic remains unchanged.
- Submission pipelines remain identical.
- Frontend retains its mandatory free-text department flow.

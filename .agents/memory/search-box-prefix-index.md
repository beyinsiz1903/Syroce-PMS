---
name: Search-box scan → prefix index pattern
description: How to make plaintext search-box queries index-serviceable to kill Atlas query-targeting alerts, and why guests can't use it.
---

# Plaintext search-box → index-serviceable prefix

Unanchored case-insensitive regex `{$regex: term, $options:"i"}` on a plaintext
field can NEVER use a btree index → full tenant-slice COLLSCAN → Atlas
"Scanned/Returned > 1000" query-targeting alert.

## The fix (the only honest one for plaintext fields)
- On create/update, write a normalized companion `<field>_lower` (NFKC + strip +
  `.lower()`), incl. dotted/nested paths. Shared helper: `security/search_normalize.py`.
- Query with an anchored **prefix RANGE**, NOT a regex:
  `{<field>_lower: {"$gte": p, "$lt": p_with_last_char_incremented}}`.
  A range gives guaranteed IXSCAN bounds with no dependence on regex
  prefix-optimization heuristics; `^re.escape(p)` regex is fragile by comparison.
- Index `(<leading_key>, <field>_lower)` — `tenant_id` leading where tenant-scoped;
  `leads` (PMS-Lite landing) is global/super-admin-only so it leads with `source`.
- Backfill existing rows once (marker-gated in `bootstrap/phases/search_normalize.py`,
  collection `search_normalize_backfill`, bump `_BACKFILL_VERSION` to re-run).
- Indexes + backfill wired in bootstrap phase C (`c_domain.py`).

**Behavior change (accepted):** substring → prefix ("starts typing a name").
Case-insensitive *effect* preserved because both stored value and query are
lowercased and the range is case-sensitive on already-lowercased data.

## Verifying (no fake-green)
Run an `explain(executionStats)`: winningPlan stages must show `IXSCAN`, and
`totalKeysExamined ≈ totalDocsExamined ≈ nReturned` (ratio ~1 = the alert metric).
Local mongod must be a **child of the verifying python process** (subprocess.Popen);
the Replit sandbox reaps `--fork`/`nohup` daemons between separate tool calls.

## What is OUT, and why
- **Encrypted-PII** (guest/user email/phone/id) keeps the `_hash_<field>` blind
  index exact-match path. NEVER add a `_lower` plaintext copy of an encrypted
  field — it re-exposes the plaintext you encrypted.
<<<<<<< HEAD
- **`folios.guest_name`**: NOT given a companion either — `folios` has ~20+
  decentralized `db.folios.insert_one` sites (no central write helper), so a
  `guest_name_lower` would be missing on most new rows → silent drop. Instead,
  **bridge through the indexed `bookings.guest_name_lower`**: prefix-match
  `bookings`, then fetch folios via the existing `(tenant_id, booking_id)` index.
  Use this bridge pattern for any folio/child collection that links to bookings
  but can't carry its own companion. **Why:** folio.guest_name mirrors the
  booking's guest, so the bridge preserves intent while staying IXSCAN.

## guests is now IN (converted)
`guests.name`/`first_name`/`last_name` are **plaintext** (NOT encrypted) so a
`_lower` companion is safe. Both the main guest search (`routers/pms_guests.py`
`search_guests`, prefix on name/first_name/last_name) and the complaints
guest-picker (`domains/pms/misc/complaints.py`, prefix on name) now use prefix
RANGE; the encrypted email/phone/id_number branch still uses the `_hash_` path.
**Why the earlier "can't do it reliably" worry was wrong:** the companion is
written by `apply_collection_normalized_fields(doc, collection="guests")` /
`normalized_set_for_update(...)`, which is independent of the encryption helper,
so the several raw-doc insert paths (agency_portal, reservation_waitlist,
reservation_detail, walk-in, OTA imports, b2b/marketplace, celery, group
booking, exely auto-import, etc.) each call the normalize helper explicitly.
**The invariant that keeps it honest:** EVERY production `guests.insert_one` and
every name-bearing `guests.update_one` must route through the helper, or new/
renamed guests silently drop out of prefix search. When adding a new guest write
path, grep `guests.insert_one` and confirm the helper is applied. Backfill for
existing rows is marker-gated `guests:v1` (config key `guests` was new → ran
once automatically; no `_BACKFILL_VERSION` bump was needed).

## Centralized vs decentralized write test (before adding a collection)
Only add a collection to `NORMALIZED_SEARCH_FIELDS` if its create/update path is
**centralized** so the companion is written on every new row. Confirmed central:
`bookings` (`core/atomic_booking.py`), `mice_accounts`/`mice_opportunities`/`leads`
(`routers/mice.py`, `domains/sales/*`). Confirmed NOT central → must bridge or
defer: `folios`.

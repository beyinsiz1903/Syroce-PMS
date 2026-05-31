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
- **`guests.name` / complaints guest-picker search**: NOT converted. `guests` has
  ~7 production insert paths and several (agency_portal, reservation_waitlist,
  reservation_detail) insert raw docs that bypass the encryption helper entirely,
  so a companion field can't be written reliably on every new row — partial
  coverage would silently drop new guests from prefix search (worse than the
  scan). `service_complaints` itself has no text-search endpoint, so indexing it
  would be fake-green. Both deferred to a follow-up.

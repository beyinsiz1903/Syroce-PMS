---
name: Encrypted-PII blind-index search invariants
description: How searchable encrypted PII (guest email/phone/id) is queried via _hash_<field> HMAC tokens, and the two ways this silently degrades to a full scan.
---

Searchable encrypted PII fields (guest email, phone, id_number,
passport_number, …) are NOT searched on ciphertext. The encrypt path writes a
deterministic blind-index token `_hash_<field>` = HMAC-SHA256(normalized value)
alongside the encrypted blob. Equality search matches that token; a parallel
case-insensitive regex on the plaintext field is kept only as a dual-read
fallback for un-migrated legacy docs. This is the established encryption-safe
search pattern — do NOT propose plaintext `name_lower` copies of encrypted PII
(that re-exposes the plaintext you just encrypted).

**Two silent-scan traps (both make the hash branch never match → tenant-wide
collection scan, which shows up as Atlas "Query Targeting > 1000"):**

1. **The hash indexes are not created at startup.** `ensure_hash_indexes`
   builds the sparse `_hash_<field>` indexes, but if it is only reachable from
   an admin endpoint (manual trigger), the indexes can be absent indefinitely.
   It must be wired into the bootstrap index phase so it is always-present and
   idempotent. Indexing only the HMAC tokens is PII-safe (no plaintext indexed).

2. **The caller pre-escapes the search value.** The query helper hashes the
   value to build the `_hash_<field>` equality condition; the hash function
   normalizes (strip+lower) to match the token written at encrypt time. If a
   caller passes `re.escape(q)` "to be safe for regex", the HMAC is computed
   over the escaped string (e.g. `a.b@x.com` → `a\.b@x\.com`) and never matches
   the stored token — so every email/id search silently falls back to the regex
   scan. **Contract: the helper owns escaping.** Callers pass the RAW value; the
   helper hashes raw AND `re.escape`s internally for its own regex fallback
   branch. This also closes a latent regex-injection/DoS hole for any caller
   that was already passing raw values into the un-escaped regex branch.

**Why:** both traps defeat an index that *looks* present in code, so they read
as "search works" while quietly scanning. They surface only as query-targeting
alerts or slow search under load, not as errors.

**How to verify without DB/PII:** instantiate the service and assert the helper's
`_hash_<field>` condition value equals `compute_search_hash(raw)` and does NOT
equal `compute_search_hash(re.escape(raw))`, and that the regex branch equals
`re.escape(raw)`.

**Still not index-serviceable:** plaintext `name` (not an encrypted field) uses
unanchored case-insensitive regex — no btree index helps; real fix is prefix
semantics (`name_lower` + anchored) or Atlas Search, both product decisions.

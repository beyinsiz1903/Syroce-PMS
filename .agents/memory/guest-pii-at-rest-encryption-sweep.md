---
name: Guest-PII at-rest encryption read-path sweep
description: Adding field-level at-rest encryption to a PII collection — the write path is easy; the leak-prone work is the systemic read-path/query/recipient sweep.
---

# Guest-PII at-rest encryption: the read path is the hard part

When you add field-level at-rest encryption to a PII collection (guests:
email/phone/id_number/passport_number/dob), converting the **write** paths
(INSERT/UPDATE → `encrypt_guest_insert` / `encrypt_guest_update`, which also write
the `_hash_<field>` blind-index token) is the easy, mechanical part.

The leak-prone part is the **read path**. Three distinct bug classes, each found
across the codebase, and only the obvious routers get caught on the first pass —
the rest hide in joins, partner/BI endpoints, and background jobs:

1. **Ciphertext-DISPLAY leak** — a handler returns a full guest/booking doc (or
   pick of `email`/`phone`) WITHOUT decrypting → client receives AES envelopes
   (`SYR1:`/`aes256gcm:`) plus internal `_hash_*`/`_ng_name`/`_enc_version`
   tokens. Fix: wrap at the return boundary with `decrypt_guest_doc` /
   `decrypt_booking_doc` (None-safe, idempotent; strip the internal tokens).
   Hiding spots: group-booking detail joins, cross-property dedupe/profile,
   complaints guest picker + guest_detail, semantic/stays BI-SDK endpoint.

2. **BROKEN-QUERY (silent miss)** — a plaintext equality/regex on `email`/`phone`
   returns ZERO encrypted rows (AES-GCM is non-deterministic). Fix with dual-read:
   `build_guest_pii_query` / `guest_pii_or_conditions` (exact = hash + plaintext) /
   `guest_pii_regex_or_conditions` (substring = hash + re.escape regex). Pass RAW
   values — the helpers normalize/escape internally.

3. **BROKEN send/recipient path** — notification/messaging code derives
   `recipient_email`/`recipient_phone` from a RAW guest doc → sends to an AES
   envelope → silently fails for migrated guests (inflates total_failed). Fix:
   decrypt the guest BEFORE deriving the recipient (and before building template
   variables). Hiding spots: complaint-resolved email, messaging automation rules.

## Hard rules
- **Decrypt ONLY at the display/read boundary, NEVER on a doc that is later
  re-persisted** — that is a plaintext downgrade. Merge/write paths must keep
  using the encrypt helpers.
- Expect to need **several architect read-sweep passes**: pass 1 caught 4 leaks,
  pass 2 caught 1, pass 3 caught 6 (display + recipient). The "verified SAFE" list
  grows each pass → convergence signal. Name-only / vip-only / existence-only
  projections and id-based lookups that decrypt at their own boundary are SAFE.

## Known residual limitations of the blind-index approach (operator sign-off)
- Phone **suffix-match dedupe** can't pre-filter encrypted rows; reach those via
  email/last_name then score on the decrypted candidates.
- Substring (`?q=`) search on encrypted email won't match (only exact via hash or
  prefix on a `_lower` companion).
- `FIELD_ENCRYPTION_PEPPER` dev default must be set per-env before backfill.
- Backfill (`encrypt_guest_pii_backfill.py`) MUTATES pilot data → fail-closed
  (`ALLOW_GUEST_PII_BACKFILL=true` + `--apply`); operator runs it, not the agent.

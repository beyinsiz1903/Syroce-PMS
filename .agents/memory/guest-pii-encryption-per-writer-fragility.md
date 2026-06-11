---
name: Guest PII encryption is enforced per-writer, not centrally
description: Each guest insert/update must call _encrypt_guest itself; there is no central choke point, so new guest-write paths silently store email/phone/id_number as plaintext.
---

# Guest PII encryption is per-writer (no central choke point)

PII-at-rest encryption for the `guests` collection is applied by each writer
calling `_encrypt_guest` (routers.pms_guests) / `encrypt_document(collection=
"guests")` right before the Mongo write. There is **no** middleware or model-layer
guard that enforces it. So any code path that builds a guest dict and calls
`db.guests.insert_one/update_one` directly will store `email`/`phone`/`id_number`
(and the other ENCRYPTED_FIELDS["guests"]) as **plaintext** unless its author
remembered to encrypt.

**Confirmed pattern:** the guest-CREATE/insert paths are the weak spot. The
canonical CRUD (pms_guests create/update, walkin) encrypts correctly, but several
booking-side guest-create paths (waitlist promote, marketplace B2B, channel
imports, agency/department/B2B booking creators) call only
`apply_collection_normalized_fields(...)` (plaintext name companions) and skip
encryption. Result: real guest email/phone stored plaintext AND no
`_hash_<field>` blind-index token, so those guests are invisible to the hashed
exact-match search in pms_guests.

**Two independent consequences of a missed `_encrypt_guest`:**
1. KVKK PII-at-rest leak (plaintext email/phone/id_number on disk).
2. Broken encrypted search (no `_hash_` token written) — guest not findable.

**How to apply:** when touching any guest-write path, confirm it routes through
`_encrypt_guest`/`encrypt_document` before the write; compute plaintext search
companions (`normalized_set_for_update` / ngram) BEFORE encryption and merge them
back AFTER, mirroring `pms_guests.update_guest`. The durable fix for the whole
class is a single choke point (a `guests`-collection write wrapper or a pre-write
hook) rather than N per-site reminders. Note: a re-encryption **backfill** of rows
already written plaintext mutates pilot guest docs too — that is a pilot-data
mutation (pilot_drift) and needs explicit operator sign-off, separate from the
code fix.

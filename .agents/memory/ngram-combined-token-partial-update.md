---
name: Combined search-token companion partial-update clobber
description: Why a concatenated search-token companion field must be recomputed from the MERGED stored doc on partial updates, not from the update payload alone.
---

# Combined search-token companion partial-update clobber

A search companion field that CONCATENATES several source fields into one token
array (e.g. guests `_ng_name` built from `name` + `first_name` + `last_name`)
must, on update, be recomputed from the MERGED stored doc + update — not from
the update payload alone.

**Why:** the per-update recompute helper only sees the changed fields. A
name-only rename (e.g. PMS `update_guest`, whose allow-list has `name` but not
`first_name`/`last_name`) recomputes the combined field from `{name}` only and
silently DROPS the untouched fields' trigrams → an OTA-imported guest with split
first/last names stops being infix-findable by surname. The bug hides because
the per-field `_lower` prefix companions are computed per-field and are immune,
so prefix search still works.

**How to apply:** when adding/maintaining a combined-token companion, every
write site that does partial updates must pass the existing stored name fields
(plaintext for guests — name/first/last are NOT encrypted) overlaid with the
update. Use the merged-doc variant of the set helper. Sites that already set all
source fields together (e.g. OTA auto_import) are fine. Unlike the marker-gated
backfill, this does NOT self-heal — the field exists, so a stale value persists
until the next full recompute. Re-verify (substring) still rejects false
candidates, so the only symptom is missing recall, not over-match.

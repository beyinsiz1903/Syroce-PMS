---
name: Self-healing unique-index backstops
description: Why best-effort unique index builds must retry instead of caching "ready", and the shared helper that does it.
---

The "no duplicate supplier/contract" safeguards (mice_accounts tax_no/email,
corporate_contracts rate_code/contact_email) are enforced ONLY by partial
unique indexes. Those indexes are GLOBAL across tenants, so duplicate rows in
ANY hotel make the build fail — silently disabling the guard for everyone.

**Rule:** a best-effort unique-index build must never cache an "indexes ready"
flag once a unique build was deferred. Retry it on every relevant call (subject
to a throttle), so cleaning the duplicate data self-heals the safeguard with no
process restart.

**Why:** the old code set `_indexes_ready=True` / `_contract_indexes_ready=True`
even when a unique build failed, so it was never retried until a restart against
clean data. Live proof: `uniq_corp_contract_contact_email` sat OFF for a long
time behind ~29 legacy duplicate rows.

**How to apply:** use `shared_kernel/index_backstops.py`
(`register_expected` + `attempt_backstop`). It records active/deferred/unknown,
logs a warning + bumps Prometheus (`hotel_pms_unique_index_backstop_active`
gauge, `..._deferred_total` counter) on deferral, throttles retries (60s), and
powers ops endpoint `GET /api/production-golive/uniqueness-backstops`. The
non-unique index batch can still be built once; only the unique backstops retry.
Boot prewarms both ensure fns in server.py `_startup` so deferral surfaces at boot.

**Residue often self-clears:** the ~29 legacy `corporate_contracts.contact_email`
dup rows that kept `uniq_corp_contract_contact_email` deferred were E2E_STRESS
residue; the stress CRM residue sweeper (HARD DELETE) removes them, so the
backstop self-heals on the next boot/ensure call with NO manual dedupe needed.
Before running `scripts/dedupe_crm_uniqueness`, check live first: dry-run +
`index_information()` may already show 0 dup groups and the unique index built.
Run the script against Atlas with `MONGO_URL=$MONGO_ATLAS_URI DB_NAME=syroce-pms`
(get_system_db reads MONGO_URL; DB_NAME defaults to hotel_pms, not the real DB).

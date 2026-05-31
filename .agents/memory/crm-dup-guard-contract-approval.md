---
name: CRM duplicate guard + corporate-contract approval lifecycle
description: Where CRM customer/contract uniqueness and contract approval state live, and the piggyback gotcha.
---

# CRM duplicate guard + contract approval

- `mice_accounts` is a shared collection: CRM client accounts AND banquet-competitor
  rows live there, discriminated by `account_type`. Any tenant-scoped uniqueness
  guard on tax_no/email MUST filter to `account_type='client'` (`_CLIENT_ACCT_FILTER`)
  or competitor rows trigger false 409s. `AccountIn` carries an `email` field.
- Corporate contracts (`corporate_contracts`, served by `rms_router/sales.py`, path
  `/api/sales/corporate-contract`) have TWO orthogonal status fields:
  `status` (active/expired) and `approval_status` (draft→pending→approved/rejected,
  rejected→draft resubmit, approved terminal). They are independent — do not conflate.
- Approval transitions go through `POST /api/sales/corporate-contract/{id}/approval-transition`
  driven by `CONTRACT_APPROVAL_TRANSITIONS`. Illegal skip/terminal-reopen → 409.

**Why:** Task #176 closed the crm-offers-contracts REVIEW gap (no dup guard, no
approval state machine). Implemented as tenant-scoped app-level guards (not a unique
index) to avoid index-build failure on existing dup/null data; observable 409 is identical.

**How to apply:** When touching account/contract uniqueness, keep the client-scope
filter and the self-exclude (`exclude_id`) on updates.

**Race-safety backstop (now implemented):** The app-level find_one guard is now
backed by tenant-scoped *partial unique* indexes — `mice_accounts` on
(tenant_id, tax_no) & (tenant_id, email), `corporate_contracts` on
(tenant_id, rate_code) & (tenant_id, contact_email). Insert/update paths catch
`DuplicateKeyError` and re-raise the SAME field-specific 409 (field sniffed from
the index name in the error string). Two invariants the partial filter MUST keep:
(1) scope `mice_accounts` to `account_type:"client"` so piggyback rows never
collide; (2) exclude blanks/nulls with `{field: {"$gt": "", "$type": "string"}}`
— required fields like rate_code/contact_email can be `""` and the app guard
ignores blanks, so an empty-string-in-index would both break the build and cause
false 409s. Index build is wrapped per-index (try/except + warning) so a
pre-existing duplicate only disables that one backstop, never aborts boot.
mice indexes live in `_ensure_indexes`; contract indexes in lazy
`_ensure_contract_indexes` (sales.py).

**Deferred-index trap (proven live, Task #216):** these partial unique indexes
are GLOBAL (span all tenants), and `_ensure_indexes`/`_ensure_contract_indexes`
set `_indexes_ready/_contract_indexes_ready = True` even when an individual
unique build is *deferred* by its per-index try/except. So if a backend process
first runs ensure-indexes while ANY duplicate exists in ANY tenant (e.g. stress
residue: `E2E_STRESS_F7_*` dup `contact_email` rows blocked
`uniq_corp_contract_contact_email`), that backstop is silently absent for the
whole process and never retried — the race window is open even though unit tests
("index params + DuplicateKeyError→409") stay green. Only a restart against
clean data rebuilds it. To prove/repair: delete the blocking duplicate rows,
restart backend, hit any endpoint that calls ensure-indexes, then verify via
`index_information()` that the `uniq_*` index exists with `unique=True`.

**demo@hotel.com == the PILOT tenant** (5bad4a34-…). Any live integration test
using the demo login mutates pilot, so it MUST be net-zero: purge created rows
in `finally` (delete_many by the unique identifier) so a failed assertion can't
leak duplicate rows and break pilot_drift=0. Live race proof:
`backend/tests/integration/test_crm_duplicate_race_live.py`.

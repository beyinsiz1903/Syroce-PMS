# CRM contact_email duplicate-guard reactivation — cleanup drill

**Date:** 2026-06-10
**Task:** Turn the supplier/contract duplicate guard back on by cleaning old
duplicates.
**Target DB:** live Atlas (`MONGO_URL=$MONGO_ATLAS_URI`, `DB_NAME=syroce-pms`).

## Objective

The `corporate_contracts.contact_email` partial unique index
(`uniq_corp_contract_contact_email`) was reported deferred behind ~29 legacy
duplicate rows (the index is global across all hotels), leaving the
duplicate-prevention backstop OFF. This drill runs the dedupe remediation,
verifies the backstop activates, and runs the previously precondition-skipped
live race test.

## Result: GREEN — backstop active, 0 residue, race test passing

**Drift note:** there were **no duplicate rows left to clean**. The legacy
residue was E2E_STRESS-generated and had already been removed by the stress CRM
residue sweeper, so the backstop self-healed on backend boot. The dedupe run is
therefore a confirmed no-op (idempotent), and the indexes are already built.

## Evidence

### 1. Dedupe dry-run + apply (`scripts/dedupe_crm_uniqueness`)

```
===== DRY-RUN =====
CRM uniqueness dedupe (DRY-RUN) — all tenants
  mice_accounts (client): 0 duplicate group(s)
  corporate_contracts: 0 duplicate group(s)
[crm-dedupe] no blocking duplicates remain in scope.
DRYRUN_EXIT=0

===== APPLY + BUILD-INDEXES =====
CRM uniqueness dedupe (APPLY) — all tenants
  mice_accounts (client): 0 duplicate group(s)
  corporate_contracts: 0 duplicate group(s)
  -- applied --
    mice client rows retired   -> 0
    contract fields blanked    -> 0
  re-scan remaining (actionable) -> 0
  -- build-indexes --
    uniq_mice_acc_client_taxno     -> OK
    uniq_mice_acc_client_email     -> OK
    uniq_corp_contract_rate_code   -> OK
    uniq_corp_contract_contact_email -> OK
[crm-dedupe] no blocking duplicates remain in scope.
APPLY_EXIT=0
```

### 2. Backstop status — `GET /api/production-golive/uniqueness-backstops`

```json
{
  "all_active": true,
  "any_deferred": false,
  "deferred_count": 0,
  "backstops": [
    {"name": "uniq_corp_contract_contact_email", "collection": "corporate_contracts", "active": true, "status": "active", "deferred_count": 0},
    {"name": "uniq_corp_contract_rate_code",     "collection": "corporate_contracts", "active": true, "status": "active", "deferred_count": 0},
    {"name": "uniq_mice_acc_client_email",        "collection": "mice_accounts",       "active": true, "status": "active", "deferred_count": 0},
    {"name": "uniq_mice_acc_client_taxno",        "collection": "mice_accounts",       "active": true, "status": "active", "deferred_count": 0}
  ]
}
```

`uniq_corp_contract_contact_email` → **active**; `all_active: true`.

### 3. Live race test — `test_crm_duplicate_race_live.py`

```
tests/integration/test_crm_duplicate_race_live.py::test_concurrent_account_create_same_tax_no_one_wins PASSED
tests/integration/test_crm_duplicate_race_live.py::test_concurrent_account_create_same_email_one_wins PASSED
tests/integration/test_crm_duplicate_race_live.py::test_blank_identifiers_no_false_positive PASSED
tests/integration/test_crm_duplicate_race_live.py::test_piggyback_competitor_no_false_positive PASSED
tests/integration/test_crm_duplicate_race_live.py::test_concurrent_contract_create_same_rate_code_one_wins PASSED
tests/integration/test_crm_duplicate_race_live.py::test_concurrent_contract_create_same_contact_email_one_wins PASSED
============================== 6 passed in 34.16s ==============================
```

The previously precondition-skipped
`test_concurrent_contract_create_same_contact_email_one_wins` now **runs and
passes** (one create 2xx, the other 409, exactly one row), confirming the
contact_email race backstop is enforced end to end.

## Reproduce

```bash
cd backend
# dry-run
MONGO_URL="$MONGO_ATLAS_URI" DB_NAME=syroce-pms python -m scripts.dedupe_crm_uniqueness
# apply (no-op when clean) + confirm index builds
ALLOW_CRM_DEDUPE=true MONGO_URL="$MONGO_ATLAS_URI" DB_NAME=syroce-pms \
  python -m scripts.dedupe_crm_uniqueness --apply --build-indexes
# live race test (needs running backend)
VITE_BACKEND_URL="http://localhost:8000" MONGO_URL="$MONGO_ATLAS_URI" DB_NAME=syroce-pms \
  python -m pytest tests/integration/test_crm_duplicate_race_live.py -v
```

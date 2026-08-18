# Syroce Pre-Pilot Reset and Module RBAC Seed

This runbook prepares a clean, controlled starting point before the first live
pilot property is onboarded. The implementation is intentionally fail-closed.
Merging the code does **not** delete data or create users.

## What is protected

The reset command always preserves every user whose role is `super_admin`.
It also excludes platform/security/migration/billing configuration from the
reset allowlist. Provider-side records are outside this tool's scope.

The command never calls `drop_database` or `drop_collection`. Operational data
is removed only with explicit tenant-scoped `delete_many` filters from the
reviewed allowlist in `backend/scripts/pre_pilot_reset.py`.

If a super-admin is attached to a tenant, that tenant is automatically
protected. The operator must resolve that relationship deliberately rather than
allowing the reset to leave the super-admin with a dangling tenant reference.

## Phase 1 — mandatory dry-run

From the backend directory:

```bash
python scripts/pre_pilot_reset.py reset \
  --all-non-super-admin-tenants \
  --all-non-super-admin-users \
  --expected-super-admin-email '<existing-super-admin-email>' \
  --report-path /tmp/syroce-pre-pilot-plan.json
```

Dry-run is the default. It performs read-only counts and prints:

- the active protected super-admin count;
- selected tenant IDs;
- per-collection deletion counts and exact filters;
- non-super-admin user count;
- tenant count;
- the list of preserved collection names.

Do not proceed if any selected tenant, collection count, or filter is
unexpected. A fresh backup must be taken after the plan is approved and before
execution.

Operational audit collections are excluded by default. They are added only
when `--include-operational-audit` is explicitly supplied and reviewed in the
dry-run report. Security audit collections remain protected.

## Phase 2 — reset execution

Reset execution requires a separate operational approval. The following is an
example only; replace every placeholder with the approved exact value:

```bash
export ALLOW_PRE_PILOT_RESET=true

python scripts/pre_pilot_reset.py reset \
  --all-non-super-admin-tenants \
  --all-non-super-admin-users \
  --execute \
  --confirmation RESET_PRE_LIVE_SYROCE \
  --expected-database-name '<exact-db-name>' \
  --expected-super-admin-email '<existing-super-admin-email>' \
  --backup-reference '<immutable-backup-id>' \
  --report-path /secure/path/pre-pilot-reset-result.json
```

Execution is blocked when any gate is absent or mismatched. The command checks
that the protected super-admin ID set is unchanged after deletion and verifies
that selected users and tenants are gone. A post-condition failure is treated
as critical and must not be retried blindly.

## Module QA users

Module users are seeded only after an explicit target tenant exists. This can
be an internal QA tenant or the approved pilot tenant. The seed command creates
one user for each of these scopes:

- frontdesk
- housekeeping
- cashier
- finance
- invoice
- pos
- stock
- procurement
- hr
- reports
- channel_manager
- sales
- tasks
- maintenance

Each document has exactly one explicit `module_scopes` entry. Explicit scopes
are authoritative, so even a legacy role with broader defaults is narrowed to
the one seeded module by `module_scope_service.py`.

Read-only plan:

```bash
python scripts/pre_pilot_reset.py seed-module-users \
  --tenant-id '<pilot-or-qa-tenant-id>' \
  --email-domain qa.syroce.app \
  --report-path /tmp/syroce-module-users-plan.json
```

Execution example, requiring separate approval:

```bash
export ALLOW_MODULE_RBAC_SEED=true

python scripts/pre_pilot_reset.py seed-module-users \
  --tenant-id '<pilot-or-qa-tenant-id>' \
  --email-domain qa.syroce.app \
  --execute \
  --confirmation SEED_MODULE_QA_USERS \
  --expected-database-name '<exact-db-name>' \
  --credentials-output /secure/path/module-qa-credentials.json
```

The credentials file is created with mode `0600`, contains unique temporary
passwords, and must be transferred through an approved secret-sharing channel.
Passwords are never printed to standard output. Seeded users are marked
`must_change_password=true` and `is_internal_test_user=true`.

## Module authorization integration

Backend routers can adopt the reusable dependency incrementally:

```python
from fastapi import Depends
from modules.pms_core.module_scope_service import require_module_scope

@router.get('/example', dependencies=[Depends(require_module_scope('reports'))])
async def example():
    ...
```

Frontend navigation and route guards can use:

```javascript
import { hasModuleAccess } from '@/utils/moduleAccess';

hasModuleAccess(currentUser, 'reports');
```

`super_admin` retains full platform access. Legacy users without an explicit
`module_scopes` field use conservative role defaults, while an explicit empty
list denies every module.

## Explicitly out of scope

This utility does not:

- call Nilvera, HotelRunner, Exely, or any other provider;
- remove provider-side Sandbox or production records;
- deploy the application;
- change production configuration;
- create a pilot tenant;
- execute automatically from CI;
- replace the required backup and operator approval process.

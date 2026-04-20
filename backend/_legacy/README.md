# _legacy/

Quarantined legacy Python modules preserved here because active application code still imports them.

Files moved to this directory during the enterprise codebase cleanup (2026-03-22).

## ⚠️ Still in use

Do **not** delete the following files without first migrating their contents:

| File | Imported by |
| --- | --- |
| `accounting_endpoints.py` | `backend/domains/accounting/router.py` |
| `accounting_models.py` | `backend/routers/finance/accounting.py` |
| `booking_availability.py` | `backend/integrations/booking_adapter.py` |
| `graphql_schema.py` | `backend/server.py` (optional GraphQL mount) |

## Cleanup history

- 2026-04-20: Removed `payment_gateway_models.py` (no references in codebase) and `__pycache__/`.
- Prior READMEs incorrectly claimed all files were safe to delete — this was out of date.

## Future removal

These files should be migrated out of `_legacy/` into their logical module homes
(e.g. `domains/accounting/`) and this directory removed entirely. That is a larger
refactor and should be tracked as a dedicated task.

# HR workflow hardening — 2026-09-07

## Fixed findings

- Payroll posting serializes per tenant/month, rejects a second unreversed full
  payroll snapshot (including sibling revisions and child-before-parent posting),
  and preserves same-run replay. Journal, counter and sequence reservation writes
  share one MongoDB transaction.
- Leave decisions serialize per tenant/staff. Final approval checks approved-date
  overlap and annual balance for every affected year. Decision, shift projection
  and requester notification commit together. Retries cannot duplicate them;
  retrying an older approved leave also repairs its missing shift projection.
- Overtime decisions serialize per tenant/staff; the annual cap is checked within
  the same transaction as approval. Requester notification is transactional.
- Annual/sick usage is clipped to each calendar year. Leave input dates must be
  canonical YYYY-MM-DD and supplied day counts must match the inclusive interval.
  This preserves the existing calendar-day convention; no new holiday policy.
- Active super-admins and users explicitly granted manage_hr join existing HR
  manager notification recipients, scoped to the tenant. The missing HR logger
  is initialized so notification failure logging itself does not raise NameError.
- HR XLSX exports contain values, never executable formulas inferred from text.
- HR tabs follow URL query navigation, including notification clicks, direct
  loads and browser back. Entitlement loading does not erase the requested tab.
  Overtime notifications now carry an HR tab link.

## Deployment requirements and data safety

MongoDB transactions require a replica set / sharded cluster. There is deliberately
no standalone non-transactional fallback: unsupported deployment returns 503.
The new workflow_locks collection uses stable _id keys incorporating tenant and
resource. Rows are serialization anchors, not expiring leases; a worker crash
does not leave a permanent held lock. Tenant isolation remains enabled.

Deploy all backend workers before relying on cross-worker protection; older
workers do not participate in the new workflow serialization protocol.
No production database migration, deletion, reversal, payment or payroll
recalculation is performed by this patch. Existing financial journals stay intact.
Existing malformed/overdrawn leave data is not silently rewritten.

## Verification

207 selected backend tests pass, including the original failed audit cases,
calendar boundaries, XLSX contents, PII/RBAC, HR entitlements and GL ledger tests.
The Mongo tests launch disposable local single-node replica sets and exercise
actual transaction conflicts, rollback after writes, retries, and the production
TenantScopedDB wrapper. They need mongod on PATH and explicitly skip if absent.
No deployment secrets or live database are used.

Frontend: 3 useHRTab navigation tests pass; production Vite build passes.
Targeted Ruff and git diff --check pass. Openpyxl emits pre-existing UTC API
deprecation warnings; the build reports outdated Browserslist metadata.

Not claimed: live verification of this new patch before deployment, complete
cross-role browser sessions, or actual downloaded browser CSV/XLSX contents.
Previous live requester notifications were observed; the manager-recipient fix
and notification navigation still require a post-deployment live recheck.

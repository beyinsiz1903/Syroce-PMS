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
filter and the self-exclude (`exclude_id`) on updates. For race-safety upgrade, a
partial unique index is the follow-up, not a behavior change.

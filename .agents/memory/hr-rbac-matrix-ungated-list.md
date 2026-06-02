---
name: HR/RBAC matrix — split by-design grants from real ungated leak
description: How to triage a stress RBAC-matrix finding where multiple roles get 2xx on "sensitive" endpoints — decompose per (role,endpoint), separate intentional role grants from a genuine missing gate.
---

# Triaging a stress RBAC matrix "N/M violations" finding

When a stress spec reports `count=N/M` cross-department violations over `roles × endpoints`,
do NOT treat the whole block as one bug or one false-positive. Decompose per (role, endpoint)
and read each endpoint's actual gate. The count almost always splits into two very different buckets:

- **By-design role grants** — a role legitimately holds the gating permission. Example: the
  `finance` role has `VIEW_FINANCIAL_REPORTS`, and the `view_hr` op maps to
  `[VIEW_HR, VIEW_FINANCIAL_REPORTS]` (OR semantics, a backward-compat alias). So finance
  passing every `view_hr`-gated HR read surface (staff list, payroll, salary-history,
  leave-balance) is intentional, documented in `enums.py` ("Finance rolü bordro/maaş
  raporlarını görür"). The spec mismodels finance as a low-priv cross-dept role. This is a
  spec-vs-product decision — escalate, do NOT silently tighten the backend or loosen the spec.

- **A real missing gate** — one endpoint among gated siblings has no authorization at all.
  Example found: `GET /hr/performance` (list) had only `Depends(get_current_user)` while its
  siblings were gated (`POST /hr/performance` → `require_op("manage_hr")`;
  `GET /hr/performance/{staff_id}` → `_authorize_staff_access(require_manage=True)`, docstring
  "performans notları hassas → SADECE manage_hr ... Finance erişemez"). That ungated list let
  front_desk/housekeeping/sales/finance read every staff review. Fix = add the matching gate
  (`require_op("manage_hr")`). Pure hardening, doctrine-safe, no escalation needed.

**Why:** mixing these two buckets either fake-greens a real leak (if you dismiss the whole
finding as "by design") or breaks legitimate workflows (if you tighten a deliberate role grant).
The decisive arithmetic check: sum the per-endpoint expected passers from the code; if it equals
the reported count, you've fully explained the finding and can act on only the genuine gap.

**How to apply:** for each endpoint in the spec's sensitive list, read its FastAPI dependency
(`require_op` / `_authorize_staff_access` / none) and the role→permission map. An endpoint with
no gate sitting next to gated create/detail siblings is the real bug. Match the sibling's gate.

## Finance PII is payroll-scoped, not directory-scoped (operator decision)
The `finance` role is a legitimate PAYROLL consumer: it keeps UNMASKED PII on
payroll/salary/leave surfaces (it needs salary + IBAN to run payroll/SGK/tax),
but it must NOT get cross-department PII from the general staff DIRECTORY.
`_mask_hr_pii` carries `allow_finance_unmask` (default True at every caller);
only the staff-list directory caller passes False, so finance is masked there
and unmasked everywhere else. **Why:** KVKK least-privilege — "finance does
payroll" is real, "finance browses everyone's TC/phone" is not. **How to apply:**
when a stress matrix flags finance on an HR surface, decide per-surface: payroll
surface -> finance authorized + unmasked (don't tighten); generic directory ->
finance authorized to READ but PII masked (mask, don't deny). Do NOT widen the
mask to per-staff profile detail or to manage_hr/super_admin without a fresh
operator call — those were deliberately left out of scope.

## PII-masking matrix corollary
`_mask_hr_pii` unmasks for `manage_hr` holders, `super_admin`, and self-service. `finance` unmasks
ONLY where `allow_finance_unmask=True` (the default — payroll/salary/leave); the staff-directory
caller passes False so finance IS masked there now (see the operator-decision section above).
On the directory the masking branch is exercised by finance and by any granted "department manager"
(view_hr + assigned_department, no manage_hr). A PII-masking assertion run with the tenant ADMIN token
(`stress_token`, role=admin → has manage_hr) is a FALSE POSITIVE (fake-RED): admin seeing unmasked PII
is correct-by-design, so asserting masking against admin tests behavior the product deliberately does
NOT implement. **Operator decision:** the directory PII-mask guard must be asserted with the FINANCE
principal (lacks the unmask gate on the list), NOT admin; admin gets only an authz (2xx) + no-token-leak
check. **Why this surfaced late:** the assertion was vacuous-green while the directory was empty; once
the role-provisioned team users (front_desk/hk/finance/sales) appeared as "derived" staff with
plaintext phones, the admin-unmask read tripped a PHONE_PLAIN P0 that drove the whole suite NO-GO.
**Watch:** if finance provisioning fails the masking step is an honest SKIP (visible in the ledger),
not a pass — don't let an empty/no-principal directory masquerade as a passed PII guard.

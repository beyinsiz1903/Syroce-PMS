# HR payroll completion: extras, employer contributions and split GL

## Scope and rate source

Standard private-sector 4/a, TRY, 2026, **no incentives**. Employer SGK is 21.75% and employer unemployment 2%, both calculated on the existing day-adjusted capped premium base and rounded separately to cents. Source checked September 7, 2026: [ÇSGB 2026 minimum wage, page 3 (no premium discount)](https://www.csgb.gov.tr/Media/gm2fekds/asgari-%C3%BCcret-2026.pdf).

Employer contributions increase employer cost, never reduce the employee's promised net. There is no automatic incentive eligibility determination. SGDP, special regimes, incentive settlement and ceiling-exceeding bonus carry remain out of scope. Net/gross payroll's existing fail-closed rules remain in place.

## Workflow

1. Save a payroll draft, or open a revision of a locked run. Existing extras are retained when opening revisions in the UI.
2. In the selected draft, add a bonus, advance offset or other deduction with employee, positive TRY amount and document/explanation. Saving recomputes the draft, including taxes and employer premiums. Removing a line and saving removes it explicitly.
3. Draft writes require payroll lifecycle permission, tenant scope, expected updated_at and status=draft. Stale writes / concurrent finalization fail with 409. Foreign or missing-period extra staff fail rather than being silently omitted. Unsaved UI extras disable finalization.
4. Configure payroll GL mapping using existing tenant chart accounts. This does not create accounts, post a payment or modify previous journals.
5. Finalize, then post. New version-2 payroll runs require complete statutory rows and split mapping. Missing employer context, unverified legacy rows, inconsistent totals or absent mappings fail closed.

## New posting

- Debit wage expense: gross.
- Debit employer premium expense: employer SGK + unemployment.
- Credit personnel payable: net after advance/other deductions.
- Credit tax payable: income tax + stamp tax.
- Credit SGK payable: employee + employer SGK and unemployment.
- Credit personnel advance receivable: advance offset, not a tax (e.g. 196).
- Credit configured other deduction counterpart: other net deductions.

SGK and tax mappings cannot be the same. Posting core still validates active tenant-owned accounts and preserves existing atomic period/revision checks and idempotency.

Historical locked runs are not recalculated/migrated. Existing posted entries are returned unchanged on retry. Historical runs without the accounting_version=2 marker retain their previous posting contract; to obtain a full new calculation use a revision with confirmed salary/matrah context, and reverse an existing parent journal before posting that revision. No old journal is automatically reversed or rewritten.

## Independent synthetic reference

October 2026; monthly gross 50,000; 3 approved overtime hours (1,000); bonus 2,000; advance 500. Opening GV base 390,000 and opening exemption base 252,679.50; 30 days / 225 normal hours.

Gross 53,000; employee SGK 7,420; employee unemployment 530; income tax 5,848.40; stamp 151.57; net after advance **38,550.03**. Employer SGK **11,527.50**, employer unemployment **1,060**; employer cost **65,587.50**.

GL debit gross 53,000 + employer cost component 12,587.50 = credit net 38,550.03 + taxes 5,999.97 + SGK 20,537.50 + advance 500 = **65,587.50**.

## Verification

Coverage includes real disposable MongoDB extras recomputation, locked parent preservation, stale-version/locked write rejection, tenant/role gates, negative/NaN amounts, foreign staff rejection, independent employer-rate/ceiling calculations, split postings and idempotent retry, missing mapping fail-closed, frontend add/remove/save/read-only/error states. Existing salary, payroll atomic and HR audit tests are included in regression runs.

CSV of a selected run now exports the saved snapshot including extras, instead of recomputing a live preview without them. XLSX snapshot export includes four employer columns; both contents are covered by isolated tests. Money is displayed to cents in payroll UI. This is implementation/test verification, **not post-deploy live verification**. Production QA journals were not modified during development.

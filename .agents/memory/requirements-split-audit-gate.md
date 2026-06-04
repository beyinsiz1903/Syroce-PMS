---
name: Backend requirements split is the audited source, not the legacy aggregate
description: CI installs/audits the requirements split; bumping the legacy aggregate alone does not clear the dependency-audit hard gate.
---

The backend has a requirements split under `backend/requirements/` (base/api/worker/
ml/reports/integrations/dev + compose files all.txt, api-runtime.txt, worker-runtime.txt).
A legacy aggregate `backend/requirements.txt` still lingers but is NOT what CI uses.

**Rule:** the CI `Python dependency security audit (CRITICAL — hard gate)` step (and
the test/deploy jobs) `pip install -r requirements/all.txt` then `pip-audit` the
INSTALLED env. `all.txt` chains `-r api.txt` (and api-runtime.txt chains api.txt too).
So a security/version bump must land in the relevant SPLIT subset file (usually
`api.txt`), not just the legacy aggregate.

**Why:** a CVE bump applied only to the legacy `backend/requirements.txt` leaves the
audited pin stale in `api.txt`, so the audit keeps failing on the "fix" commit even
though the local `pip-audit -r backend/requirements.txt` looks clean. (Seen with
aiohttp CVE-2026-34993: legacy bumped to 3.14.0 but api.txt stayed 3.13.5 → gate
still red.)

**How to apply:** for any backend dependency change, edit the correct split subset
(grep the package across `backend/requirements/`; each package is a single direct
entry — `check_requirements_split_parity.py` forbids cross-subset duplicates). Then
verify with `python backend/scripts/check_requirements_split_parity.py` (no dup) and
`pip-audit -r backend/requirements/api.txt`. The parity script only checks intra-split
duplicates now (Phase 8.2), NOT legacy-vs-split version parity — so a stale legacy
file won't be caught by it. Keep the legacy aggregate consistent too, but the split
is authoritative.

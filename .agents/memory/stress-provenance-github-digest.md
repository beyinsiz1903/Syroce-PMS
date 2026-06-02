---
name: Stress baseline provenance via GitHub API digest
description: How to fetch CI run/job/artifact provenance (incl. artifact sha256) for baseline bookkeeping without a valid token.
---

When promoting/recording a stress-suite baseline you must capture run ID, job ID,
commit, and each artifact's ID + sha256 — and provenance must NEVER be fabricated.

**Rule:** Fetch it from the GitHub REST API. The repo is public, so the runs/jobs/
artifacts metadata endpoints work **anonymously** (no auth header) even when
`GITHUB_TOKEN` is invalid / `gh auth` fails / there is no GitHub connector. Use the
code_execution sandbox `fetch` against `api.github.com/repos/<owner>/<repo>/...`.

- Find the run by commit: `GET /actions/runs?head_sha=<sha>` → match `run_number`.
- Or by number: page `GET /actions/workflows/<workflow_id>/runs?per_page=50&page=N`.
- Job: `GET /actions/runs/<id>/jobs`.
- Artifacts: `GET /actions/runs/<id>/artifacts` — each artifact's `digest` field is
  `sha256:...` of the artifact contents. **No download/zip-hashing needed.**

**Why:** Older chain entries computed sha256 by downloading artifacts (needs auth);
the API `digest` field gives it directly, anonymously. This unblocks provenance even
with no working credentials and keeps the "never fabricate provenance" doctrine.

**Consistency gotcha (baseline reports):** A stress report's per-test inventory is
Playwright **case-level** (passed = no hard throw), while P2/REVIEW triage lines are
harness **step-level** annotations inside those passing cases (e.g. "hard-assert"
specs gracefully degrade a module-access 403 or empty data-state to REVIEW). So
"inventory passed but triage says failed" is a granularity artifact, NOT stale
carryover — confirm by checking the module table's REVIEW distribution sums to the
report's total REVIEW count before deciding it's real vs stale.

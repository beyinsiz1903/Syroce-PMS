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

There are actually THREE axes: (1) Playwright case inventory (passed/skipped),
(2) per-module step PASS/REVIEW/SKIP, (3) severity-triage P0–P3 findings. They are
independent: a module can read 13/0/0 (clean step axis) and STILL carry a P2 (e.g.
"audit marker not found") because the P2 is a soft severity finding on a case that
passes at step level. So "clean module table but a P2 line" is NOT a contradiction
and NOT stale — it's axis (3) vs axis (2). Artifact ZIP **body** download is
auth-gated (401, only metadata/digest is anonymous), so a fresh line-by-line body
re-sum is CI/auth-deferred; when you can't download, say so honestly and rest the
classification on the structural model + the prior baseline's line-by-line check +
operator-transcribed counts — never fabricate a "verified the sums" claim.

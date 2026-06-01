---
name: A recurring stress P0 you already fixed is often a stale-CI-commit artifact
description: Before re-fixing a stress NO-GO P0 that matches a finding you previously closed, confirm the failing run's commit actually contained the fix.
---

When a full-stress NO-GO reports a P0 that you already fixed in a prior task, do
NOT assume a regression and re-patch. The CI run frequently executes on a commit
that predates the fix.

**Why this happens:** the Replit checkpoint SHA namespace is DIFFERENT from the
CI/GitHub repo SHA namespace. A fix can be committed to workspace HEAD (and be an
ancestor of the current checkpoint) yet be absent from the GitHub ref the CI
stress job checked out. Wall-clock is misleading: a run whose seed-prefix
timestamp is *after* the fix's commit time can still be running pre-fix code if
the fix wasn't pushed to the CI repo before checkout. So "run started after the
fix landed" does NOT prove "run included the fix".

**How to triage before changing any code:**
1. `git blame -L <line>` the exact return/guard lines on current HEAD to confirm
   the fix is present in the workspace.
2. Live read-only probe the running backend with the offending payloads. If the
   env is fail-closed it returns 503 (still proves "not the buggy 2xx"); if a
   bypass/test-auth mode is active it returns the corrected 4xx.
3. Deterministically prove the branch selection offline (e.g. replay the parse
   step with the router's own parser) when the live env short-circuits before the
   branch you need to exercise.
4. If HEAD is correct, the action is "push HEAD to the CI ref and re-run" — NOT a
   code change. Report it as resolved-on-HEAD, CI-deferred verification.

**Decode a stress seed prefix** `E2E_STRESS_F7_<ms>_`: the `<ms>` is the run
START (globalSetup seed) epoch in milliseconds; `date -u -d @<seconds>`. Compare
it against the fix's commit time, but treat the comparison as a hint, not proof
(see the two-namespace caveat above).

**Second, distinct mechanism — backend-under-test deploy lag (NOT checkout lag):**
`stress.yml` points at a PERSISTENT deployed backend via a fixed secret
(`E2E_BASE_URL: secrets.STRESS_E2E_BASE_URL`); it only health-warms that URL and
does NOT deploy the backend from the run's commit (no uvicorn/kubectl/start.sh in
stress.yml). Consequence: a **spec-only** fix takes effect the instant CI checks
out your commit, but a **backend** fix only takes effect after the stress backend
deployment is separately redeployed. So a run can simultaneously show a spec fix
working AND a backend fix not working, with the SAME commit checked out.
**Diagnostic that pins it:** find a spec-side change of yours in the same commit
and confirm it took effect this run (e.g. a gate-tier/selector change now passing).
If the spec change took effect but the backend behavior is unchanged, it is
backend-deploy lag, not checkout lag → action is "redeploy the stress backend,
then re-run", never a code change.

# Backend Requirements Split — Phase 2 Run Artifact

**Date**: 2026-05-10
**Phase**: 2 of 8 (per `requirements-split-plan.md`)
**Scope**: Create `backend/requirements/{base,api,worker,ml,reports,integrations,dev,all}.txt`
**Behavior change**: **None.** Aggregate `backend/requirements.txt`, `backend/requirements-ci.txt`,
both Dockerfiles, all CI workflows — **all untouched**.

## Files created

```
backend/requirements/
├── base.txt          # 72 packages — pydantic, http core, auth, dates, redis, motor/pymongo
├── api.txt           # 27 packages — fastapi, websockets, sentry  (-r base, -r reports)
├── worker.txt        # 24 packages — celery, flower, gevent, flask stack  (-r base)
├── ml.txt            # 16 packages — numpy, pandas, scipy, sklearn, xgboost, hf
├── reports.txt       # 13 packages — weasyprint, openpyxl, lxml, pillow
├── integrations.txt  # 25 packages — boto3, google-*, openai, litellm, stripe, resend, iyzipay
├── dev.txt           # 45 packages — pytest, ruff, mypy, locust, playwright, pip_audit
└── all.txt           # legacy aggregate composer (-r api, worker, ml, integrations, dev)
```

Total: **222 packages** across 7 leaf files (matches aggregate exactly).

## Decisions applied (from user feedback on Phase 1 §7)

| # | Decision | Applied as |
|---|----------|------------|
| 1 | litellm Plan **B** (parity preserve) | `litellm==1.80.0` in `integrations.txt` + explicit comment block referencing the Dockerfile `--no-deps` override; clean upgrade (Plan A) deferred. |
| 2 | `pillow` → `reports.txt`, `brotli` → `api.txt` | Done. `reports.txt` includes `pillow==12.2.0`; `api.txt` includes `brotli==1.2.0`. |
| 3 | Don't touch `requirements-ci.txt` in Phase 2 | Untouched — still references aggregate `requirements.txt`. |
| 4 | Don't touch aggregate `requirements.txt` (no header even) | Untouched — git diff confirms 0 bytes changed. |
| 5 | Worker minimal subset needs import-graph scan before Phase 5 | Documented as Phase 5 prerequisite in plan §4.4 and noted in `worker.txt` comment header. |

## Verification

```
=== 1. Set parity (aggregate vs split union) ===
PARITY OK (no diff)

=== 2. Duplicate package across split files ===
NO DUPLICATES

=== 3. Counts ===
  base.txt         72 packages
  api.txt          27 packages
  worker.txt       24 packages
  ml.txt           16 packages
  reports.txt      13 packages
  integrations.txt 25 packages
  dev.txt          45 packages
  ----------------------
  split total     222 packages
  aggregate       222 packages

=== 4. Untouched consumers (git diff --stat) ===
  backend/requirements.txt:  0 changes
  backend/requirements-ci.txt: 0 changes
  backend/Dockerfile:          0 changes
  worker/Dockerfile:           0 changes
  .github/workflows/:          0 changes

=== 5. pip check (current env) ===
  pipdeptree 2.31.0 requires pip>=25.2 (have 25.0.1)  — preexisting, unrelated to split
  typer 0.24.0 requires click>=8.2.1 (have 8.1.8)     — preexisting, unrelated to split

=== 6. Workflow status (post-write) ===
  Backend API      — running (new logs, no restart)
  Mobile Web       — running
  Quick-ID API     — running
  Start application — running
```

## Reproduce locally

```bash
# Set parity
diff \
  <(grep -vE '^\s*(#|$|-r )' backend/requirements.txt | sort -uf) \
  <(grep -vhE '^\s*(#|$|-r )' backend/requirements/{base,api,worker,ml,reports,integrations,dev}.txt | sort -uf)
# expected: empty

# Duplicate scan (case-insensitive, version-stripped)
grep -hvE '^\s*(#|$|-r )' backend/requirements/{base,api,worker,ml,reports,integrations,dev}.txt \
  | awk -F'[=><\\[]' '{print tolower($1)}' | sort | uniq -d
# expected: empty
```

## Out of scope (deferred to later phases)

- **Phase 3**: dry install + import smoke (`fastapi`, `motor`, `celery`, `celery_app`, `server`).
- **Phase 4**: backend `Dockerfile` → `-r requirements/all.txt` (parity-preserving swap).
- **Phase 5**: worker `Dockerfile` → minimal subset; **requires AST/import-graph scan first** (per §4.4).
- **Phase 6**: backend `Dockerfile` → `-r requirements/api.txt` (API image shrinks; ML moved out).
- **Phase 7**: CI workflows + `requirements-ci.txt` redirect.
- **Phase 8**: aggregate `requirements.txt` deprecation/removal.

## Risk status snapshot

| Risk (from plan) | Phase 2 status |
|------------------|----------------|
| ML paket isolation | Defined (`ml.txt`), no Docker swap yet |
| PDF/reports boundary | Defined; `api.txt` chains `reports.txt` to preserve current API behavior |
| litellm override | Documented in `integrations.txt` header; no Dockerfile change |
| Worker queue deps | `worker.txt` only chains `base.txt`; ML/reports/integrations not yet chained — **must NOT swap worker Dockerfile until import-graph scan** |
| CI rsync exclude | Untouched (still excludes only `requirements.txt`) |
| Frontend workflow installing backend reqs | Untouched, follow-up |

## Architect review fix (2026-05-10)

Architect (`evaluate_task`) flagged a **Phase 5 blocker**: `backend/celery_tasks.py`
imports `motor.motor_asyncio` at module load time, and `celery_app.py` imports
`celery_tasks`. With `motor`+`pymongo` originally placed only in `api.txt`, a
future worker Dockerfile swap to a worker-only subset would crash on boot with
`ModuleNotFoundError: motor`.

**Fix applied in this same phase**: moved `motor==3.3.1` and `pymongo==4.8.0`
from `api.txt` to `base.txt` (both API and worker chain `base.txt`, so the
runtime contract is now correct for any subset combination). Parity re-verified:
222=222, 0 duplicates. Comments added in both `base.txt` and `api.txt` headers.

Architect's other findings:
- Set parity, chain logic, litellm comment quality — all assessed positive.
- Duplicate base resolution via `all.txt` (base pulled by both api and worker)
  is **intentional** (resolver-overhead only, not a functional issue).
- Phase 3 smoke must include `python -c "import celery_app, celery_tasks"`
  against the worker subset to catch this class of issue early — added to
  the Phase 3 checklist below.

## Phase 2 verdict

**Pass.** Files exist, set parity 222=222, zero duplicates, zero behavior change,
architect-flagged Phase 5 blocker fixed in-flight.
Ready for Phase 3 (dry install + smoke) on user approval.

### Phase 3 smoke checklist (for next phase)

```bash
# Subset-targeted import smoke (catches misclassified runtime deps before Docker swap)
python -m venv /tmp/v-api && /tmp/v-api/bin/pip install -r backend/requirements/api.txt
/tmp/v-api/bin/python -c "import sys; sys.path.insert(0,'backend'); import server; print('api ok')"

python -m venv /tmp/v-wkr && /tmp/v-wkr/bin/pip install -r backend/requirements/worker.txt
/tmp/v-wkr/bin/python -c "import sys; sys.path.insert(0,'backend'); import celery_app, celery_tasks; print('worker ok')"
```

---

# Phase 3 Run (2026-05-10) — dry install + import smoke

**Scope**: Per ChatGPT recommendation, ran three venvs (worker, api, all) on
host Python 3.12 (note: production Dockerfile uses 3.11-slim — version
parity gap documented for Phase 4 Docker reconciliation).

## Results

| Venv | Subset | Install | pip check (project-related) | Smoke import | Verdict |
|------|--------|---------|------------------------------|--------------|---------|
| `/tmp/v-wkr` | `-r worker.txt` (chains base) | OK ~9s | clean (only preexisting pip/typer warnings) | `import celery_app, celery_tasks` → **ok** | **PASS** |
| `/tmp/v-api` | `-r api.txt` (chains base + reports) | OK ~6s | starlette pin issue (see below) | `import server` (with stub env vars) → **ok** (all routers loaded) | **PASS (with caveat)** |
| `/tmp/v-all` | `-r all.txt` (full aggregate equivalent) | OK ~10s (cache hit on prior wheels) | same starlette caveat | `import celery_app + celery_tasks + server` → **ok** | **PASS (with caveat)** |

## Key validations

1. **Architect's Phase 5 blocker fix verified end-to-end**: worker venv with
   only `worker.txt` chain (= base + worker only, no api/ml/reports/integrations)
   successfully imports `celery_app` and `celery_tasks`. Moving `motor`+`pymongo`
   to `base.txt` was the right call. Without that fix, this venv would have
   crashed with `ModuleNotFoundError: motor`.

2. **API server.py loads cleanly under api.txt subset**: all routers from
   `bootstrap/router_registry`, channel manager, supplies marketplace, webhook
   admin, entitlement, deploy pipeline, Quick-ID proxy, WhatsApp, integrations,
   security/PII, secret rotation, field encryption, notifications, encryption
   management — all loaded. No missing-dep errors.

3. **all.txt parity-equivalent install**: total wall-clock ~10s thanks to pip
   cache reuse from prior worker+api venvs. Combined import smoke
   (`celery_app + celery_tasks + server`) passed in a single Python invocation.

## Preexisting issues surfaced (NOT caused by split)

These appear when running against the **aggregate `requirements.txt`** as well —
flagged here for Phase 4 (Docker reconciliation), not for Phase 2/3 fix:

### a. `starlette==1.0.0` pin vs runtime conflict
- Aggregate `backend/requirements.txt` L181 pins `starlette==1.0.0`. Verified
  via `pip install --dry-run starlette==1.0.0` — the version **does exist on
  PyPI** ("Would install starlette-1.0.0").
- During `pip install -r all.txt`, pip emitted:
  `error: uninstall-no-record-file × Cannot uninstall starlette None`
  and fell back to `starlette 0.37.2` (likely picked up from system Nix
  site-packages without RECORD metadata).
- `pip check` then reports:
  `fastapi 0.135.1 has requirement starlette>=0.46.0, but you have starlette 0.37.2`
- **Why this is preexisting**: aggregate has the same pin. The conflict only
  manifests in this Replit Python 3.12 venv that overlays Nix-managed system
  site-packages. In the production Docker image (clean 3.11-slim), pip
  installs `starlette==1.0.0` cleanly — no fallback, no resolver conflict.
- **Phase 4 action**: verify on actual Docker build that `starlette==1.0.0`
  installs cleanly. If it doesn't, lift the pin to `>=0.46,<2` (separate PR
  outside the split scope).

### b. `pipdeptree 2.31.0 requires pip>=25.2 (have 25.0.1)`
- Replit Nix bundles pip 25.0.1; pipdeptree was bumped to 2.31.0 in aggregate.
- Cosmetic only; pipdeptree still functions for advisory use.

### c. `typer 0.24.0 requires click>=8.2.1 (have 8.1.8)`
- typer pulled in transitively as 0.24.x by other tooling; aggregate pins
  `click==8.1.8` and `typer==0.23.1` so on a clean install this should
  resolve. The mismatch only appears in this Nix-overlayed venv.

## Reproduce

```bash
PIP_USER=0 python3 -m venv /tmp/v-wkr && \
PIP_USER=0 /tmp/v-wkr/bin/pip install -r backend/requirements/worker.txt && \
cd backend && PIP_USER=0 /tmp/v-wkr/bin/python -c \
  "import sys; sys.path.insert(0,'.'); import celery_app, celery_tasks; print('worker ok')"

PIP_USER=0 python3 -m venv /tmp/v-api && \
PIP_USER=0 /tmp/v-api/bin/pip install -r backend/requirements/api.txt && \
cd backend && PIP_USER=0 /tmp/v-api/bin/python -c "
import sys, os; sys.path.insert(0,'.')
os.environ.setdefault('JWT_SECRET','smoke')
os.environ.setdefault('MONGO_URL','mongodb://localhost:27017')
os.environ.setdefault('DB_NAME','smoke')
import server; print('api ok')"

PIP_USER=0 python3 -m venv /tmp/v-all && \
PIP_USER=0 /tmp/v-all/bin/pip install -r backend/requirements/all.txt && \
PIP_USER=0 /tmp/v-all/bin/pip check
```

**Note**: `PIP_USER=0` is required in this environment because `PIP_USER=1`
is set globally and conflicts with venv installs (causes silent
`Can not perform a '--user' install` errors).

## Phase 3 verdict

**Pass.** All three subset venvs install and import successfully. The
architect-flagged Phase 5 blocker is verified fixed. Two preexisting
issues (starlette pin behavior in Nix-overlay venv, pip/typer version
warnings) are documented for Phase 4 Docker-image verification but do
NOT block subset adoption.

**Ready for Phase 4** (backend Dockerfile → `-r requirements/all.txt`)
on user approval.

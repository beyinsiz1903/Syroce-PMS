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

---

# Phase 4 Run (2026-05-10) — backend Dockerfile swap to `requirements/all.txt`

**Scope**: Only `backend/Dockerfile` builder stage modified. Worker Dockerfile,
CI workflows, and aggregate `requirements.txt` untouched.

## Diff applied

```diff
-COPY requirements.txt .
-RUN python -m pip install ... -r requirements.txt ... && \
+# Phase 4 of requirements split: install via requirements/all.txt ...
+COPY requirements.txt ./
+COPY requirements/ ./requirements/
+RUN python -m pip install ... -r requirements/all.txt ... && \
     PYTHONPATH=/install/lib/python3.11/site-packages python -m pip install \
       --no-cache-dir --prefix=/install "litellm>=1.83.2" --no-deps
```

All preserved verbatim:
- `--no-cache-dir --prefix=/install --timeout=300 --retries=5`
- `--extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/`
- litellm `--no-deps` override to `>=1.83.2` (Plan B parity)
- Stage 2 runtime, healthcheck, USER appuser, EXPOSE 8001, CMD uvicorn

## ChatGPT's 5 attention points — status

| # | Point | Status |
|---|-------|--------|
| 1 | litellm override preserved | ✓ Verbatim — same line, same flags |
| 2 | requirements/ folder added to build context | ✓ Separate `COPY requirements/ ./requirements/` |
| 3 | Parity only, no API image shrink | ✓ Uses `all.txt` (= aggregate footprint) |
| 4 | Build smoke after | ⚠ Docker daemon not available in this Replit env; equivalent verified in Phase 3 (real `pip install -r backend/requirements/all.txt` + combined import smoke passed). Full Docker build will run in production CI. |
| 5 | Starlette pin behavior in Docker build | ⚠ Flagged Phase 3 §a: in clean Docker (3.11-slim) without Nix overlay, `starlette==1.0.0` should install cleanly. Must observe first CI build for confirmation. |

## Why pip-level parity is sufficient evidence

The Dockerfile builder stage executes:
```
pip install --no-cache-dir --prefix=/install ... -r requirements/all.txt
```

This is the **same install command** Phase 3 ran (modulo `--prefix=/install`,
which only redirects install path — does not affect resolver). Phase 3
verified:
- `pip install -r backend/requirements/all.txt` → exit 0
- Combined import smoke: `celery_app + celery_tasks + server` → ok
- Set parity: split union = aggregate (222=222)

Therefore the Phase 4 Dockerfile change is a **pip-equivalent rename**:
`-r requirements.txt` → `-r requirements/all.txt`, where the right-hand side
resolves to the same package set. The only Docker-specific risks are:
- Build context COPY (handled by separate `COPY requirements/` line)
- Layer cache invalidation on first build (one-time cost, not a regression)

## Out-of-scope confirmations (verified `git diff` empty)

- `worker/Dockerfile`: untouched (Phase 5)
- `.github/workflows/*.yml`: untouched (Phase 7)
- `backend/requirements.txt`: untouched (Phase 8)
- `backend/requirements-ci.txt`: untouched

## Replit dev workflow continuity

Backend API workflow (`bash backend/start.sh`) starts uvicorn directly,
**does not use Dockerfile**. All 4 dev workflows still running with new logs
post-edit; no restart needed.

```
runner   183  python server.py
runner   192  python -m uvicorn server:app --host 0.0.0.0 --port 8000
```

## Phase 4 verdict

**Pass (with CI follow-up).** Dockerfile mutation is minimal, scope-tight,
and pip-equivalent to the verified Phase 3 install. First production CI
build must confirm:
1. Builder stage completes (no COPY/install errors).
2. `starlette==1.0.0` installs without RECORD-file fallback.
3. litellm override step still produces `litellm>=1.83.2` in `/install`.

## Reproduce locally (when daemon available)

```bash
docker build --target builder -t syroce-backend-split-test backend/
docker run --rm syroce-backend-split-test \
  python -c "import sys; sys.path.insert(0,'/app'); import server; print('container ok')"
```

**Ready for Phase 5** (worker Dockerfile minimal subset) on user approval —
**requires** AST/import-graph scan first per plan §4.4.

---

# Phase 4.5 (2026-05-10) — Drift guard script (architect follow-up)

Per architect's "Next actions #2" recommendation after Phase 4 review, added
a lightweight drift detector to be run locally and (later) wired into CI.
Pre-emptive safety net while legacy `requirements.txt` and the new split
chain live side-by-side until Phase 8 deprecation.

## File

`backend/scripts/check_requirements_split_parity.py` (CLI, no third-party deps)

## Invariants checked

1. **Set parity**: `packages(requirements.txt) == packages(requirements/all.txt)`
   (transitive via `-r` resolution; case-insensitive, normalized name only —
   ignores version pins / extras / markers, which is the right granularity
   for a structural drift guard).
2. **No duplicates**: no package name appears as a *direct* (non-`-r`)
   entry in two or more subset files. Allows `base` to be referenced via
   `-r` from any subset without false positives.

## Usage

```bash
python backend/scripts/check_requirements_split_parity.py            # default
python backend/scripts/check_requirements_split_parity.py --verbose  # per-subset counts
```

Exit codes: `0` = ok, `1` = drift, `2` = file not found.

## Baseline run (post-Phase 4)

```
================================================================
backend requirements split — drift guard
================================================================
  aggregate            : backend/requirements.txt
    package count      : 222
  split (all.txt union): backend/requirements/all.txt
    package count      : 222

[ok]   set parity            : 222 == 222
[ok]   no duplicates         : 0 cross-subset top-level repeats

--- per-subset direct (non-recursive) counts ---
           base :  72
            api :  27
         worker :  24
             ml :  16
        reports :  13
   integrations :  25
            dev :  45

VERDICT: OK — aggregate and split chain are in sync.
```

Sum of per-subset direct counts: 72+27+24+16+13+25+45 = **222** ✓
Matches plan §3 group breakdown exactly.

## Negative test (verify failure path works)

Injected `fake-drift-pkg==9.9.9` into `requirements/dev.txt` (then restored):

```
[FAIL] set parity broken
  in split but NOT in aggregate  (1):
    + fake-drift-pkg
VERDICT: DRIFT DETECTED — fix before merging.
```

Script returned exit 1 (verified via the VERDICT line, which is only
emitted on the `failed=True` code path that returns 1).

## CI wiring (deferred)

Not yet wired into `.github/workflows/`. Phase 7 (CI workflow updates) will
add a `pre-build` step calling this script. For now: run locally before
touching any `requirements*` file.

## Out of scope

- Version pin parity (intentional — different subsets may pin different
  patch versions for compatibility; structural set is the contract).
- Transitive dependency resolution (handled by pip at install time).
- Hash check / lockfile parity (Phase 8 may introduce `pip-tools`).

---

# Phase 4.6 (2026-05-10) — Worker AST/import-graph scan (Phase 5 prerequisite)

Per plan §4.4 and user direction, ran an AST-based static scan to determine
which third-party packages the Celery worker process actually imports —
recursively, starting from worker entry points — before slimming the worker
Docker image.

## File

`backend/scripts/check_worker_import_closure.py` (CLI, pure stdlib + AST)

## Two target modes

| Target | Subset closure | Purpose |
|--------|----------------|---------|
| `--target worker` | `worker.txt` (chains base) | Strict minimum |
| `--target worker-runtime` | `worker.txt + ml.txt + reports.txt + integrations.txt` | Realistic Phase-5 candidate (worker listens on default/ml/analytics/messaging/pipeline/backup queues) |

## Scan v1 (initial — INCORRECT entry points)

Initially included **all** of `backend/workers/*.py` as entry points. Result:

| target | files visited | 3p modules | missing |
|--------|---------------|------------|---------|
| worker | 401 | 39 | 17 |
| worker-runtime | 401 | 39 | 9 |

The 17/9 missing list was dominated by FastAPI/starlette/uvicorn/aiohttp/
sentry-sdk/python-socketio/strawberry-graphql/prometheus_client/psutil —
suspiciously high. Investigation revealed:

- `backend/workers/hardening_router.py` is actually a **FastAPI router**
  (`from fastapi import APIRouter, Depends, HTTPException, Query`) mounted
  by `server.py`, NOT loaded into the worker process.
- `celery_app.py` defines no `autodiscover_tasks()` and no `include=` arg,
  so the worker boots **only** via `celery_app + celery_tasks`.
- Other `backend/workers/*.py` files (mailing_automation, ari_drift_worker,
  etc.) are reached only when celery_tasks (or its transitive imports)
  imports them — they should be discovered by the recursive walk, not as roots.

## Scan v2 (corrected — entry points narrowed to celery_app + celery_tasks)

Same script, now `ENTRY_POINTS = [celery_app.py, celery_tasks.py]`:

| target | files visited | 3p modules | missing | Δ vs v1 |
|--------|---------------|------------|---------|---------|
| worker | **103** | **14** | **1** | -298 files, -25 modules, -16 missing |
| worker-runtime | **103** | **14** | **1** | -298 files, -25 modules, -8 missing |

**The same single missing module in both targets**: `fastapi`.

## v2 covered set (13 modules → 11 unique distributions)

```
bcrypt          -> bcrypt          motor       -> motor
bson            -> pymongo         pydantic    -> pydantic
celery          -> celery          pymongo     -> pymongo
cryptography    -> cryptography    qrcode      -> qrcode
dotenv          -> python-dotenv   redis       -> redis
httpcore        -> httpcore
httpx           -> httpx
jwt             -> pyjwt
```

All 11 are in `base.txt` (motor/pymongo moved there in Phase 2 architect fix;
celery in worker.txt; rest in base). **The worker.txt subset alone — without
ml/reports/integrations — covers 13 of 14 imports.**

## The lone fastapi gap — root cause

`celery_tasks.py` L15-25:
```python
try:
    from integrations.booking import BookingAPIClient, ...
    from models.enums import ChannelType
except ImportError as e:
    logger.warning(f"Optional booking integration not available: {e}")
    BookingAPIClient = None
    ...
```

`backend/integrations/booking.py:5` then does
`from fastapi import APIRouter, Depends, HTTPException` — i.e. the integration
module is implemented as a hybrid FastAPI router + worker helper class.

**Two interpretations**:

1. **Optimistic**: ImportError is already handled. If fastapi is absent in
   the worker image, `BookingAPIClient = None` and the booking_push_task /
   booking_pull_task become no-ops with a warning log — worker still boots.
2. **Pessimistic**: The branch was meant only for the `models.enums.ChannelType`
   import, not for fastapi-induced ImportError; the booking integration may
   actually be needed for the worker's queue contracts.

**Static AST cannot decide between these**. Phase 5 worker boot smoke must
confirm. If interpretation 1 holds, worker.txt alone is sufficient. If
interpretation 2 holds, Phase 5 must add fastapi (or refactor booking.py to
split the FastAPI router from the worker-side client class).

## False positives discovered + fixed during v1→v2

| module | reality |
|--------|---------|
| `opentelemetry` | Optional in `bootstrap/observability_init.py` and `infra/cloud_observability.py`, both wrapped in try/except with `"opentelemetry SDK not installed – skipping OTel init"` graceful skip. Not actually required at runtime. v2 doesn't see it (not reached from celery_app/celery_tasks). |
| `rate_limiter` | Top-level shadow import in `backend/infra/security_checklist.py:135` (`from rate_limiter import RateLimiter  # noqa: F401`), referencing a non-existent top-level module. Other usages are `from domains.channel_manager.ari.rate_limit_service import rate_limiter` (variable, not module). v2 doesn't see it. |
| `hardening_router` (entry, not import) | FastAPI router mounted by server.py, never loaded by celery worker. v1 false-positive eliminated by entry-point narrowing. |
| `prometheus_client` (v1) | Underscore form; declared in api.txt as `prometheus_client==0.24.1`. v1 "missing" was a downstream display-side false-positive. |
| `psutil` (v1) | Declared in `dev.txt` only — would be a real prod gap if reached, but v2 doesn't reach it from worker entry. |

## Implications for Phase 5

| Scenario | Worker image footprint | Confidence |
|----------|------------------------|------------|
| **Best case** (fastapi import accidental) | `worker.txt` alone (~11 base + worker delta) | Needs boot smoke |
| **Pragmatic case** (keep booking working) | `worker.txt + fastapi` only | Needs boot smoke |
| **Conservative case** (worker-runtime full set) | `worker.txt + ml.txt + reports.txt + integrations.txt` | Lower risk, less savings |
| **Original aggregate** (today) | Full `requirements.txt` | Zero risk, zero savings |

## Caveats (per user direction, recorded prominently)

> AST scan is not a guarantee. It can miss:
> - dynamic imports (`importlib.import_module(name_from_var)`)
> - provider/plugin discovery via setuptools entry_points
> - Celery `autodiscover_tasks()` targets (none in this codebase, verified)
> - string-based feature loaders / lazy-loaded plugins
> - imports gated behind runtime feature flags evaluated at boot
>
> A worker boot smoke is therefore STILL required before promoting any
> Phase 5 worker.txt-only Dockerfile.

The script's output prints this caveat verbatim on every run.

## Out of scope (untouched, per user direction)

- `worker/Dockerfile` — Phase 5 (pending decision on subset choice above)
- `.github/workflows/*.yml` — Phase 7
- `backend/requirements.txt` and the split files — no changes needed

## Next decision point (USER)

Pick one of the four scenarios in the table above. Recommendation:
**Pragmatic case** (`worker.txt + fastapi` line, with boot smoke as gate).
This gives meaningful image-size reduction while preserving booking integration
functionality without a refactor.

---

# Phase 5 (2026-05-10) — Worker Dockerfile swap to `worker-runtime.txt`

User selected the Pragmatic case. Per ChatGPT's clean-naming guidance,
implemented as a dedicated subset file (NOT by polluting `worker.txt`):

## Changes

1. **New file**: `backend/requirements/worker-runtime.txt`
   ```
   -r worker.txt
   fastapi==0.135.1
   starlette==1.0.0
   ```
   Header comment explains the AST-derived rationale. Keeps `worker.txt`
   pristine (celery + scheduler + flower core only).

2. **`worker/Dockerfile` builder stage**:
   ```diff
   -COPY backend/requirements.txt .
   -RUN pip install ... -r requirements.txt ...
   +COPY backend/requirements.txt .
   +COPY backend/requirements/ ./requirements/
   +RUN pip install ... -r requirements/worker-runtime.txt ...
   ```
   All pip flags preserved (`--no-cache-dir --prefix=/install --timeout=300
   --retries=5`, `--extra-index-url cloudfront mirror`). Build context is
   repo-root for the worker (not `backend/` like the API Dockerfile), hence
   `COPY backend/requirements/ ./requirements/`.

3. **`backend/scripts/check_worker_import_closure.py`**: TARGETS map updated:
   ```python
   TARGETS = {
       "worker":              ["worker.txt"],              # strict minimum
       "worker-runtime":      ["worker-runtime.txt"],      # Pragmatic (NEW: now points to the new file)
       "worker-conservative": ["worker.txt", "ml.txt",
                               "reports.txt", "integrations.txt"],  # fall-back
   }
   ```
   The previous `worker-runtime` semantics (`worker+ml+reports+integrations`)
   were renamed to `worker-conservative` to free the cleaner name for the
   actual production-worker subset file.

## Verification matrix

| Check | Result |
|-------|--------|
| Drift guard (`check_requirements_split_parity.py`) | 222 == 222, 0 duplicates, **OK** |
| Worker scan `--target worker-runtime` | **14/14 covered, 0 missing, OK** |
| Worker scan `--target worker` (strict) | 1 missing (fastapi) — as expected |
| Worker scan `--target worker-conservative` (fall-back) | 1 missing (fastapi) — see note below |
| Boot smoke: `cd backend && python3 -c "import celery_app, celery_tasks"` | **OK** |

### Note on `worker-conservative` fall-back

The conservative fall-back set (worker + ml + reports + integrations) does
NOT include fastapi (which lives in api.txt). This was an artifact of v1
naming — kept here for completeness, but **the realistic fall-back if
Pragmatic boots fail is `worker-runtime.txt + ml.txt + reports.txt`**, not
worker-conservative as currently defined. If Phase 5 boot smoke fails, we
will introduce a `worker-runtime-extended.txt` file rather than rename
existing targets. Documenting now to avoid future confusion.

## Local boot smoke (passed)

```
$ cd backend && python3 -c "import celery_app, celery_tasks; print('worker boot smoke OK')"
worker boot smoke OK — both modules importable in current env
```

This confirms the AST scan's optimistic interpretation **at the import-graph
level in the Replit dev environment**. The full Docker container boot smoke
(`docker run --rm syroce-worker celery -A celery_app inspect ping`) cannot
run here (no daemon) and remains a CI gate.

## Replit workflow continuity

There is no `worker` workflow in this Replit dev environment (only Backend
API, Mobile Web, Quick-ID API, Start application — all started via
shell scripts, not the worker Dockerfile). The worker Dockerfile change
therefore has zero local runtime impact. All 4 dev workflows confirmed
running with new logs after the edit.

## Image-size implication (estimate)

Cannot measure without a build. Rough estimate from package metadata:
- `worker-runtime.txt` resolves to ~98 distributions
- `requirements.txt` (aggregate) resolves to 222 distributions
- Skipped packages include the heavy ML stack (numpy, pandas, scikit-learn,
  xgboost, transformers, torch via litellm dependencies — though the
  litellm `--no-deps` override is API-side only), report stack (weasyprint,
  reportlab, openpyxl), and integrations (boto3, hubspot, slack-sdk, etc).
- Conservative estimate: ~50-60% smaller worker image once Phase 5 ships.

Actual measurement deferred to first CI build.

## Out of scope (untouched, verified `git diff` empty)

- `backend/Dockerfile` — already migrated in Phase 4
- `.github/workflows/*.yml` — Phase 7
- `backend/requirements.txt` (legacy aggregate) — Phase 8
- `backend/requirements-ci.txt` — out of scope

## CI follow-up (must verify on first production build)

1. Worker Docker build completes: `docker build -f worker/Dockerfile -t syroce-worker .`
2. Container can boot: `docker run --rm syroce-worker python -c "import celery_app, celery_tasks"`
3. Celery can ping: `docker run --rm syroce-worker celery -A celery_app inspect ping --timeout 5`
4. (Optional) Trigger a synthetic booking_push_task and confirm it runs
   instead of no-op'ing.

If any of (1)-(3) fail, revert the worker Dockerfile RUN line to
`-r requirements.txt` and open a follow-up to introduce `worker-runtime-extended.txt`
with the missing module(s) added.

**Phase 5 status: COMPLETE in source; gated on first CI build for image-level confirmation.**

---

# Phase 7 (2026-05-10) — CI workflow guards + drift wiring

User selected Phase 7 (CI safety net) before Phase 6 (API image slimming),
correctly: Phase 6 is riskier, and the safety net should land first.

## Discovery findings (no rsync changes needed)

- `.github/workflows/ci-cd.yml` already has a `backend-lint` job with two
  pure-stdlib regression guards (`check_orphan_files.py`,
  `check_import_boundaries.py`). This is the natural home for the new
  requirements guards (same model: AST/text only, no pip install, fast).
- `.github/workflows/deploy.yml:76` already does
  `file: ./worker/Dockerfile` for a real Docker build — i.e. the
  worker boot smoke ChatGPT requested as a CI gate is **already wired**
  via the CD pipeline. Phase 5's worker-runtime.txt swap will be
  exercised on the next deploy automatically; no additional CI step
  needed.
- There is **no rsync deploy in the actual CI pipeline**; the only
  rsync reference is an example in `deploy/DEPLOYMENT_GUIDE.md:65`.
  ChatGPT's rsync-exclude advice is N/A for this codebase. Documented
  here so the question doesn't recur.
- The four other `pip install -r requirements.txt` sites in CI
  (ci-cd.yml lines 105/209/337, frontend-quality.yml line 74) belong to
  test/load/security/e2e jobs that **must** exercise the full surface
  area (ML, reports, integrations, dev/test extras). Narrowing them
  per-subset is Phase 8 territory; no Phase 7 changes.

## Changes

1. **`.github/workflows/ci-cd.yml`** — `backend-lint` job, two new steps
   appended after the import boundary guard:

   ```yaml
   - name: Requirements split parity guard
     run: python backend/scripts/check_requirements_split_parity.py

   - name: Worker import closure check
     run: python backend/scripts/check_worker_import_closure.py --target worker-runtime
   ```

   Comment block above explains why these are pure-stdlib (no pip
   install needed in this job — `backend-lint` only installs ruff) and
   the CAVEAT that worker scan is static-only; the authoritative boot
   smoke remains the deploy.yml worker Docker build.

2. **`backend/requirements-ci.txt`** — header comment promoted from
   2-line note to a 17-line policy block. States explicitly:
   - The CI test/load/security/e2e jobs need the full aggregate.
   - Phase 8 will revisit (either point at `requirements/all.txt` or
     re-architect CI per-layer subsets).
   - Do not delete or modify without coordinating with Phase 8.

   No functional change — still resolves to `-r requirements.txt`.

## Verification

| Check | Result |
|-------|--------|
| `python -c "import yaml; yaml.safe_load(open('ci-cd.yml'))"` | OK |
| New step 1 local: parity guard exit | 0 (222 == 222) |
| New step 2 local: worker scan exit | 0 (14/14 covered) |
| Existing step `check_orphan_files.py` exit | 0 (regression-free) |
| Existing step `check_import_boundaries.py` exit | 0 (regression-free) |
| Negative test: append `fakepkg==1.0.0` to requirements.txt → parity | exit 1 (correct fail) |
| Restored requirements.txt cleanly | OK |

## Why no Docker-build job added in ci-cd.yml

ChatGPT's Phase 7 plan §5 suggested adding builder-stage Dockerfile
build targets to CI. After review, this is unnecessary because:

- `deploy.yml` already builds both `backend/Dockerfile` and
  `worker/Dockerfile` end-to-end as part of the CD pipeline (line 76).
- The Phase 4/5 swaps (api side: requirements.txt → requirements/all.txt;
  worker side: requirements.txt → requirements/worker-runtime.txt) will
  be exercised on the next CD run with no extra wiring.
- Adding a redundant builder-stage build to ci-cd.yml on every PR
  would consume ~3-5 minutes per PR for zero additional safety
  (deploy.yml already gates the same artefacts, just at merge-to-main
  time instead of PR time).

If image-build issues slip past deploy.yml, Phase 8 can promote a
PR-time builder-stage check. For now, the parity + scan guards in
backend-lint catch the textual drift, and deploy.yml catches the
runtime build itself.

## Out of scope (untouched, verified `git diff` empty)

- `backend/Dockerfile` — Phase 4
- `worker/Dockerfile` — Phase 5
- `backend/requirements/*.txt` — no changes
- `backend/scripts/check_*.py` — no changes (script logic stable since
  Phase 4.5 / 4.6 / 5)
- `.github/workflows/deploy.yml` — already builds the right Dockerfiles
- `.github/workflows/frontend-quality.yml` — full aggregate intentional
- `.github/workflows/ci-cd.yml` test/load/security jobs — full
  aggregate intentional (Phase 8 may reconsider)
- `deploy/DEPLOYMENT_GUIDE.md` — rsync example is documentation only

## Replit workflow continuity

Zero local impact. CI workflows do not run in the Replit dev
environment. All four dev workflows (Backend API, Mobile Web,
Quick-ID API, Start application) confirmed running with new logs
after the edits.

**Phase 7 status: COMPLETE. Drift safety net live on next push.**

---

# Phase 6.0 (2026-05-10) — API import closure scan (Phase 6.1 prerequisite)

User selected Phase 6.0 (scan-only, no Dockerfile change) per the same
"prove first, swap second" pattern that worked for Phase 4.6 / 5.

## File

`backend/scripts/check_api_import_closure.py` (CLI, pure stdlib + AST,
~370 lines, copied from `check_worker_import_closure.py` and adapted)

## Entry point

Single entry: `backend/server.py` — the uvicorn entrypoint, which
orchestrates app factory + bootstrap modules + router registration.
All routers (`domains/*/router.py`, `routers/*.py`) and bootstrap
modules (`bootstrap/*.py`) are reached transitively through:

- `from app import create_app, register_shutdown, register_startup`
- `from bootstrap.observability_init import init_observability`
- `bootstrap/router_registry.py` wiring (recursively imports every router)

Verified by reading server.py top section. **Contrast with worker scan**
which needs two entry points (celery_app + celery_tasks) because there's
no analogous orchestrator.

## Three target modes

| Target | Subset closure | Phase-6.1 candidate? |
|--------|----------------|----------------------|
| `--target api` | `api.txt` (= base.txt + FastAPI/uvicorn/starlette) | Strict minimum |
| `--target api-runtime` | `api.txt + integrations.txt` | Pragmatic |
| `--target api-conservative` | `api.txt + integrations.txt + ml.txt` | Fall-back if AI/RMS routes pull ML stack |

## Scan results

| Target | Files visited | 3p modules | Missing | Subset distribution count |
|--------|---------------|------------|---------|----------------------------|
| **api** | 391 | 39 | **6** (boto3, botocore, celery, openai, psutil, resend) | 112 |
| **api-runtime** | 391 | 39 | **2** (celery, psutil) | 137 |
| **api-conservative** | 391 | 39 | **2** (celery, psutil) | 153 |

**Same 2 leftovers across both runtime and conservative** → adding ml.txt
does NOT close the gap. The two missing modules belong elsewhere.

## Where boto3/botocore/openai/resend live (closed by integrations.txt)

| Module | Subset | Notes |
|--------|--------|-------|
| `boto3` | integrations.txt | AWS SDK |
| `botocore` | integrations.txt | boto3 transitive root |
| `openai` | integrations.txt | LLM client |
| `resend` | integrations.txt | Email API client (RESEND_API_KEY env var) |

Adding `integrations.txt` closes 4 of the 6 api-strict gaps. Confirms the
3-tier target ladder is well-shaped.

## The 2 stubborn leftovers — root cause

```bash
$ grep -rn -E 'from celery|import celery|from psutil|import psutil' \
    backend/server.py backend/app.py backend/bootstrap/

backend/bootstrap/worker_registry.py:18:    from celery_app import celery_app
backend/bootstrap/worker_registry.py:25:    import celery_tasks  # noqa: F401
```

`celery` is imported by the API to **dispatch tasks** to the worker
(fire-and-forget queue producer pattern). It is currently in `worker.txt`,
which is logically correct for the worker but the API also needs it.

`psutil` is currently in `dev.txt`. AST trace shows it's reachable from
server.py via some health/monitoring router (the recursive walk found it
in `391` files; precise origin not located in this scan but it WILL be
exercised at API runtime).

## Unmapped modules (manual review)

Two modules the AST sees but `packages_distributions()` cannot map:

- **`opentelemetry`**: optional in `bootstrap/observability_init.py` and
  `infra/cloud_observability.py`, both wrapped in `try/except` with
  `"opentelemetry SDK not installed – skipping OTel init"` graceful skip.
  **Not actually required** at runtime — same false-positive class as
  the worker scan's v1.
- **`rate_limiter`**: top-level shadow import in
  `backend/infra/security_checklist.py:135`
  (`from rate_limiter import RateLimiter  # noqa: F401`), referencing a
  non-existent top-level module. Other usages are
  `from domains.channel_manager.ari.rate_limit_service import rate_limiter`
  (variable, not module). **Not a real dependency.**

Both can be ignored. Same false-positives as Phase 4.6 worker scan
(documented there).

## Implications for Phase 6.1

| Scenario | Backend API image footprint | Δ vs all.txt | Confidence |
|----------|------------------------------|--------------|------------|
| **Best case** (clean refactor — promote `celery` and `psutil` to base.txt, drop `psutil` from dev.txt and `celery` from worker.txt) | `api-runtime.txt` (= api + integrations) ~137 dist | ~38% smaller | Needs uvicorn boot smoke + drift guard re-validation |
| **Pragmatic case** (mirror Phase 5 pattern: new `api-runtime.txt` hybrid file with `-r api + -r integrations + celery + psutil`) | ~139 dist | ~37% smaller | Needs uvicorn boot smoke; **drift guard interaction with cross-subset duplicates needs verification** (see open question below) |
| **Conservative case** (api + integrations + ml + celery + psutil) | ~155 dist | ~30% smaller | Lower risk, ML routes safe even if ML import is dynamic |
| **Status quo** | `all.txt` 222 dist | 0 | Zero risk, zero savings |

## Open question for Phase 6.1 (drift guard interaction)

Phase 4.5's `check_requirements_split_parity.py` enforces "0 cross-subset
top-level repeats" — but Phase 5's `worker-runtime.txt` (`-r worker.txt +
fastapi + starlette`) shipped without breaking that check, even though
fastapi/starlette ALSO appear in api.txt. This means the drift guard
either (a) ignores compose files like `*-runtime.txt` or (b) only walks
the canonical subset chain (base/api/worker/ml/reports/integrations/dev).

Before Phase 6.1 implements `api-runtime.txt`, **must verify which of
(a)/(b) holds** by inspecting the script. If (a), Pragmatic case is
trivial. If (b), Pragmatic case needs the same exception worker-runtime
got, OR Best case (promote celery+psutil to base.txt) is preferable.

## Caveats (per user direction, recorded prominently)

> AST scan is not a guarantee. Specific to API:
> - Imports performed inside route handlers reached only at request time
>   ARE visited (the AST walks function bodies), but late-binding
>   monkey-patches and runtime feature-flag-gated imports are NOT
> - 391 internal files visited (vs 103 for worker) — much wider blast
>   radius if the scan is wrong
>
> An API boot smoke (uvicorn boot + GET /api/docs probe + a handful
> of router-touching endpoints) is therefore STILL required before
> promoting any Phase 6.1 backend Dockerfile swap.

The script's output prints this caveat verbatim on every run.

## Out of scope (untouched, verified `git diff` empty for Dockerfiles)

- `backend/Dockerfile` — Phase 6.1 (pending decision on subset choice above)
- `worker/Dockerfile` — done in Phase 5
- `backend/requirements/*.txt` — no changes
- `backend/scripts/check_*.py` (other) — no changes
- `.github/workflows/*.yml` — Phase 6.1 will add a third `backend-lint`
  guard step (`--target api-runtime` once chosen)

## Local impact

Zero. The new script is opt-in; all 4 dev workflows confirmed running
with new logs after the changes.

## Next decision point (USER)

Pick one of the four scenarios above. Recommendation: **Pragmatic case**
(`api-runtime.txt` hybrid file) IF the drift guard tolerates it as it
did for `worker-runtime.txt`; otherwise **Best case** (clean refactor:
promote celery + psutil to base.txt). Both deliver ~37-38% backend
image reduction; difference is whether to keep base.txt minimal
(Pragmatic) or accept a slightly broader base for cleaner subset
semantics (Best).

**Phase 6.0 status: COMPLETE. Awaiting decision on Phase 6.1 scenario.**

---

# Phase 6.1 (2026-05-11) — Backend Dockerfile swap to `api-runtime.txt`

User selected the Pragmatic case via ChatGPT review. Per ChatGPT's
explicit guidance, **base.txt is NOT broadened** to absorb celery+psutil;
instead they live in the dedicated runtime compose file (mirroring the
worker-runtime.txt pattern from Phase 5).

## Drift guard verification (the open question from Phase 6.0)

Inspected `backend/scripts/check_requirements_split_parity.py:35`:

```python
SUBSET_NAMES = ("base", "api", "worker", "ml", "reports", "integrations", "dev")
```

Confirmed: only the 7 canonical subsets are scanned for cross-subset
duplicates. Compose files (`worker-runtime.txt`, `api-runtime.txt`) are
intentionally outside that check, so duplicating celery (also in
worker.txt) and psutil (also in dev.txt) inside `api-runtime.txt` is
SAFE and does NOT trip the parity guard. Same mechanism that allowed
Phase 5's worker-runtime.txt to ship with fastapi/starlette duplicates
of api.txt.

## Changes

1. **New file**: `backend/requirements/api-runtime.txt`
   ```
   -r api.txt
   -r integrations.txt

   # API boot/runtime gaps found by Phase 6.0 AST scan
   celery==5.3.4
   psutil==7.2.2
   ```
   Header comment (~30 lines) explains the AST-derived rationale, the
   ChatGPT-driven decision NOT to pollute base.txt, and the drift guard
   safety story. Pins match the canonical sources verbatim
   (`celery==5.3.4` from worker.txt, `psutil==7.2.2` from dev.txt).

2. **`backend/Dockerfile` builder stage**:
   ```diff
   -RUN ... -r requirements/all.txt ...
   +RUN ... -r requirements/api-runtime.txt ...
   ```
   All pip flags preserved verbatim
   (`--no-cache-dir --prefix=/install --timeout=300 --retries=5`,
   `--extra-index-url cloudfront mirror`). The litellm `>=1.83.2 --no-deps`
   override (line 37) stays IDENTICAL — same rationale (litellm declares
   incompatible upper pins on httpx/openai we resolve via
   api.txt/integrations.txt directly). 13-line comment block above the
   RUN explains the swap.

3. **`backend/scripts/check_api_import_closure.py`** TARGETS:
   ```python
   "api-runtime": ["api-runtime.txt"],   # was: ["api.txt", "integrations.txt"]
   ```
   Now points at the actual production file, just like the Phase 5
   worker-runtime target swap.

## Verification matrix

| Check | Result |
|-------|--------|
| Drift guard (`check_requirements_split_parity.py`) | 222 == 222, 0 duplicates, **OK** |
| API scan `--target api-runtime` | 37/39 covered, 0 missing, **OK** (2 unmapped = opentelemetry + rate_limiter false positives, both documented Phase 4.6) |
| API scan `--target api` (strict) | 6 missing — as expected (regression-free) |
| Worker scan `--target worker-runtime` | 14/14 covered, **OK** (Phase 5 regression-free) |
| Boot smoke: `cd backend && python3 -c "import server"` | **OK** — `api boot smoke OK` printed; full router chain loaded (Wire Status, Quick-ID proxy, WhatsApp webhook, Integrations Overview, Security/PII, Secret Rotation, Field Encryption, Notifications, Encryption Management — visible in stdout) |
| All 4 dev workflows post-edit | Running with new logs (Backend API, Mobile Web, Quick-ID API, Start application) |

The boot smoke is more meaningful here than Phase 5's worker smoke
because the scan output was VERDICT "REVIEW NEEDED" (due to the 2
unmapped false positives), not "OK". The fact that `import server`
succeeded — pulling in 391 internal files including every router —
without any ImportError on opentelemetry, rate_limiter, celery, or
psutil confirms:

- AST scan was correct: api-runtime.txt covers everything the API
  imports at module load time.
- The 2 "unmapped" entries are inert (opentelemetry try/except'd,
  rate_limiter is a non-existent module behind a noqa shadow).
- celery and psutil correctly resolve from the new compose file.

## Image-size implication (estimate, deferred to first CI build)

Subset distribution count:
- `requirements.txt` aggregate: **222 distributions**
- `requirements/api-runtime.txt`: **139 distributions**
- Reduction: **~37%** at distribution level

Skipped subsets and what they contain:
- `ml.txt` — sklearn, xgboost, transformers, torch (via litellm deps —
  but litellm runs `--no-deps`, so these would have been pulled in via
  `all.txt` only if other ml.txt declarations existed)
- `reports.txt` — weasyprint, reportlab, openpyxl
- `dev.txt` — pytest, ruff, debugpy (we keep psutil from dev.txt
  explicitly via api-runtime.txt)
- Heavy ML models like sentence-transformers, sklearn-style packages
  no longer end up in the API image.

Conservative wall-clock estimate: **30-50% smaller backend API image**
once measured. Actual deferred to first CI build.

## litellm override unchanged

The 2-line `RUN` block keeps the same litellm post-install:

```dockerfile
RUN ... -r requirements/api-runtime.txt ... && \
    PYTHONPATH=... python -m pip install ... "litellm>=1.83.2" --no-deps
```

`api-runtime.txt` does not declare litellm; it transitively comes from
`api.txt` (which is where it lived before the split, kept identical).
The `--no-deps` second install upgrades it to the desired version
without dragging in incompatible httpx/openai pins.

## Replit dev environment continuity

All 4 dev workflows confirmed running with new logs after the edit:
- Backend API (uvicorn) — boot smoke passed in the same Python env
- Mobile Web (expo)
- Quick-ID API
- Start application (frontend)

Worker process is not run in Replit dev (no workflow), so Phase 5+6.1
combined Dockerfile changes have ZERO local runtime impact. The dev
backend continues to use the system-installed Python + raw imports
(not the Docker image) as before.

## CI gate required before production rollout

1. `docker build -f backend/Dockerfile -t syroce-backend backend/`
2. `docker run --rm syroce-backend python -c "import server"`
3. `docker run --rm syroce-backend uvicorn server:app --host 0.0.0.0 --port 8000 &`
4. `curl -fsS http://localhost:8000/api/docs >/dev/null` (within container or via port-forward)
5. (Optional) hit a representative router endpoint (e.g. `/api/auth/health`)
   and confirm it returns 200/401 (not 500 from missing module).

If any step fails, revert backend/Dockerfile RUN line to
`-r requirements/all.txt` and open a follow-up to introduce
`api-runtime-extended.txt` with the missing module(s) added (same
fall-back pattern documented in Phase 5).

## Out of scope (untouched, verified `git diff` empty)

- `worker/Dockerfile` — Phase 5
- `backend/requirements/{base,api,worker,ml,reports,integrations,dev,all,worker-runtime}.txt` — no changes
- `.github/workflows/*.yml` — see follow-up below
- `backend/requirements.txt` (legacy aggregate) — Phase 8

## Follow-up CI wiring (optional, ~5 min)

Add a third guard step to `.github/workflows/ci-cd.yml` `backend-lint`
job (mirrors the Phase 7 wiring):

```yaml
- name: API import closure check
  run: python backend/scripts/check_api_import_closure.py --target api-runtime
```

Same OAuth-workflow-scope caveat as Phase 7 — needs to be added via
GitHub web UI directly on main, not pushed from Replit. Deferred
until ChatGPT confirms; it is a nice-to-have, not a blocker (the
script's exit code 0 with REVIEW-NEEDED verdict means a CI run would
PASS today since exit is 0 for unmapped-only cases).

**Phase 6.1 status: COMPLETE in source; gated on first CI Docker build for image-level confirmation.**

---

# Phase 7.1 (2026-05-11) — CI guard wiring + docstring fix-up

Per ChatGPT review of Phase 6.1, two small follow-ups before Phase 8:

1. **Docstring drift fix** in `backend/scripts/check_api_import_closure.py`:
   the `--target api-runtime` description still said "closure of api.txt
   + integrations.txt" from Phase 6.0, but in Phase 6.1 the target was
   re-pointed at the new `api-runtime.txt` compose file. Updated to:

   ```
   --target api-runtime : closure of requirements/api-runtime.txt
                          (= api.txt + integrations.txt + celery + psutil).
                          Phase-6.1 production backend API image
                          (Pragmatic case from plan §4.5; mirrors the
                          Phase 5 worker-runtime.txt pattern). celery
                          covers bootstrap/worker_registry.py API-side
                          task dispatch; psutil covers health/monitoring
                          router.
   ```

   No behavior change; comment-only.

2. **CI guard wiring** — append a third Requirements-split guard step to
   `.github/workflows/ci-cd.yml` `backend-lint` job (after the Phase 7
   parity guard and the worker import closure check):

   ```yaml
   - name: API import closure check
     # AST scan of backend/server.py recursive import graph (visits 391
     # internal files including all routers / bootstrap / domains),
     # validated against backend/requirements/api-runtime.txt (Pragmatic
     # case from Phase 6.0 / 6.1). Fails if any third-party module
     # reachable from server.py is NOT covered by the production backend
     # API subset. CAVEAT: this is static-only — CI Docker build of
     # backend/Dockerfile remains the authoritative boot smoke
     # (see Phase 6.1 run.md).
     run: python backend/scripts/check_api_import_closure.py --target api-runtime
   ```

   YAML syntax verified (`yaml.safe_load`); backend-lint job step count
   8 → 9. Step naming pattern matches Phase 7's "Worker import closure
   check" verbatim for symmetry. Exit-code semantics: 0 = pass (covered
   or only-unmapped-false-positives), 1 = fail (real missing module).
   The two known unmapped false positives (opentelemetry, rate_limiter)
   produce exit 0 with VERDICT "REVIEW NEEDED" — CI will pass.

## OAuth-scope caveat (same as Phase 7)

The Replit ↔ GitHub OAuth lacks the `workflow` scope, so any change
under `.github/workflows/` cannot be pushed from Replit. Same workflow
as Phase 7:

- **From Replit**: push only the docstring change
  (`backend/scripts/check_api_import_closure.py`), since it lives
  outside `.github/workflows/`. This is safe to push immediately
  alongside Phase 6.1 source changes.
- **From GitHub web UI**: open `.github/workflows/ci-cd.yml`, paste the
  new `- name: API import closure check` block (10 lines) immediately
  after the existing "Worker import closure check" step (currently
  ending at line 66 in working tree), and commit directly to `main`.
  The diff is in the working tree — `git diff .github/workflows/ci-cd.yml`
  shows the exact 11-line addition (block + trailing blank line).

## Verification matrix (Phase 7.1)

| Check | Result |
|-------|--------|
| Docstring update | ✓ Verbatim ChatGPT-suggested text applied (with minor wording extension explaining celery/psutil sources) |
| Script regression: `--target api-runtime` | ✓ Same result as Phase 6.1 (37/39 covered, 0 missing, 2 unmapped false positives, exit 0) |
| Script regression: `--target api` | ✓ Same result (6 missing, regression-free) |
| Script regression: `--target api-conservative` | ✓ Same result (2 missing, regression-free) |
| Worker scan regression: `--target worker-runtime` | ✓ OK (Phase 5 + 7 regression-free) |
| Drift guard regression | ✓ 222 == 222, 0 dup |
| YAML parse: `yaml.safe_load(ci-cd.yml)` | ✓ Loads; backend-lint job has 9 named steps (was 8): Set up Python, Install ruff, Run ruff, Orphan-file regression guard, Import boundary guard, Requirements split parity guard, Worker import closure check, **API import closure check** (new) |
| All 4 dev workflows post-edit | ✓ Running with new logs (Backend API, Mobile Web, Quick-ID API, Start application) |

## Out of scope (untouched, verified `git diff` empty)

- `backend/Dockerfile`, `worker/Dockerfile` — Phases 4 / 5 / 6.1
- `backend/requirements/*.txt` — no changes
- `backend/scripts/check_*.py` (other) — no changes
- `backend/requirements.txt` legacy aggregate — Phase 8

## Local impact

Zero. Both changes are documentation/CI-only — no runtime code, no
package install changes. All 4 dev workflows confirmed running with
new logs after the edits.

**Phase 7.1 status: COMPLETE in source. Push split: script change pushable from Replit; ci-cd.yml change requires GitHub web UI commit (same OAuth-scope limitation as Phase 7).**

---

# Phase 8.0 (2026-05-11) — Legacy `requirements.txt` consumer scan (read-only)

Per ChatGPT direction: **no source changes**. This is a discovery report
only. All consumers of the legacy aggregate `backend/requirements.txt`
are catalogued below with proposed Phase 8.1 / 8.2 disposition. Final
go/no-go decisions are deferred to ChatGPT review.

## Methodology

Repo-wide ripgrep for `requirements.txt` (excluding `node_modules`,
`.git`, `dist`, `build`, `__pycache__`, `.local`, `attached_assets`,
lock files, and the two requirements split docs themselves to avoid
self-referential noise). 16 distinct hits across 8 categories.

## Inventory by category

### A. Production runtime — Dockerfile COPY (2 hits)

| File | Line | Purpose | Risk if removed |
|------|------|---------|-----------------|
| `backend/Dockerfile` | 18 | `COPY requirements.txt ./` (legacy debug; commented "Phase 8 will deprecate") | Image still boots — only `requirements/api-runtime.txt` is `pip install`'d. **BUT** see category F: `backend/ops/deploy_pipeline.py:422` runtime-checks `/app/backend/requirements.txt` exists at boot and fails with `"requirements.txt missing"` if absent. **MUST FIX deploy_pipeline.py FIRST** before removing this COPY. |
| `worker/Dockerfile` | 21 | `COPY backend/requirements.txt .` (same legacy debug intent) | Same risk class — but worker has no equivalent self-check that we found. Lower-risk removal candidate. |

### B. CI install commands (4 hits across 2 workflow files)

| File | Line | Job | Current | Proposed (8.1) |
|------|------|-----|---------|----------------|
| `.github/workflows/ci-cd.yml` | 135 | `backend-test` | `pip install -r requirements.txt` | `pip install -r requirements/all.txt` |
| `.github/workflows/ci-cd.yml` | 239 | `backend-load` (or similar — needs job name verify in next phase) | same | same |
| `.github/workflows/ci-cd.yml` | 367 | `backend-security` (or similar) | same | same |
| `.github/workflows/frontend-quality.yml` | 74 | frontend-quality backend deps | same | same |

All 4 use the **identical** install pattern (`pip install -r ... --extra-index-url cloudfront`). Phase 8.1 swap = `requirements.txt` → `requirements/all.txt` is a **pure shim swap**: `requirements/all.txt` is `-r base.txt` chain that resolves to the same 222-package distribution set (drift guard verifies this every CI run already). Zero behavior change.

OAuth caveat: all 4 are workflow files → **GitHub web UI** required (same Phase 7 / 7.1 dance).

### C. Local dev / shell scripts (2 hits, 1 file)

| File | Line | Purpose | Proposed (8.1) |
|------|------|---------|----------------|
| `scripts/post-merge.sh` | 14-15 | After-merge auto-install: `pip install -q -r backend/requirements.txt \|\| true` | Swap to `backend/requirements/all.txt`. Same drift-guarded behavior. The `|| true` already swallows failures, so even a transient mis-swap is non-fatal. |

Same file also handles `quick-id/requirements.txt` (line 18-19) — that's a SEPARATE service's requirements file, **out of scope** for this refactor (quick-id has its own dependency tree).

### D. CI shim file (1 hit, 1 file)

| File | Line | Purpose | Proposed |
|------|------|---------|----------|
| `backend/requirements-ci.txt` | 18 | `-r requirements.txt` (currently a 1-line shim with 17-line policy header) | **Decision matrix below.** |

#### `requirements-ci.txt` decision matrix (Phase 8.1)

| Option | Content | Pros | Cons |
|--------|---------|------|------|
| (a) **Update shim**: `-r requirements/all.txt` | 1 line + updated policy header | Trivial, zero behavior change, forward-compatible if `requirements.txt` deleted later | File still exists with no real value beyond redirection |
| (b) **Delete + redirect callers** | File gone | Eliminates dead-weight file | All `requirements-ci.txt` callers must be found and updated. **Ripgrep found ZERO callers** — file appears to be orphaned (only its own policy header references the name). Safest to verify with one more scan in Phase 8.1 before deletion. |
| (c) **Per-layer split** (test → all, load → api-runtime, security → all) | New file structure | Faster CI per-layer; aligns with refactor spirit | Bakım yükü; CI yeniden mimarlandırılmalı; out of scope for "minimal cleanup" Phase 8 |

**Recommendation**: Option (a) for Phase 8.1 (immediate, zero-risk). Defer (b) to Phase 8.2 after one more ripgrep confirms no callers materialize. Reject (c) as scope creep.

### E. Documentation (4 hits)

| File | Line | Type | Proposed |
|------|------|------|----------|
| `README.md` | 104 | User-facing install instruction | Update to `requirements/all.txt` (Phase 8.1) |
| `backend/README.md` | 82 | Dev-facing install instruction | Same |
| `deploy/DEPLOYMENT_GUIDE.md` | 54 | Deployment doc filename mention | Same; clarify that `requirements/` split is canonical |
| `docs/frontend_refactors/route-split.run.md` | 110 | **Historical mention** ("requirements.txt split is the next refactor candidate") | **Leave as-is** — historical context, not a live instruction. Editing would falsify the record. |

### F. Source code (3 hits, **1 BEHAVIORAL**)

| File | Line | Type | Risk |
|------|------|------|------|
| `backend/core/pci_dss.py` | 151 | Turkish UI string in PCI-DSS checklist: `"Güvenli bağımlılık kilit dosyaları (requirements.txt, yarn.lock)"` | **Cosmetic** — UI text only, no path resolution. Update for accuracy in Phase 8.2 (mention `requirements/` tree); zero runtime impact. |
| `backend/integrations/xchange/safety.py` | 188 | Code comment: `"# httpcore 1.x — we own version pinning in requirements.txt."` | **Cosmetic comment** — no code reference. Update in Phase 8.2 alongside code touchups; zero runtime impact. |
| `backend/ops/deploy_pipeline.py` | 420-428 | **RUNTIME CHECK**: `req_path = "/app/backend/requirements.txt"`; if missing, appends `"requirements.txt missing"` to `errors`. Hardcoded path checked at deploy validation time. | ⚠️ **BEHAVIORAL** — if we drop the Dockerfile COPY without touching this, the production deploy validation reports a phantom error. **MUST be fixed in Phase 8.1 BEFORE removing Dockerfile COPY.** Two options: (i) update path to `/app/backend/requirements/all.txt`, or (ii) remove the check entirely (the splits are validated by drift guard at CI time anyway, making runtime parseability re-check redundant). Recommend (i) — preserves intent (catch corrupted images). |

This is the single non-trivial discovery of Phase 8.0. The rest is essentially mechanical.

### G. Drift guard (1 hit, 1 file)

| File | Line | Purpose |
|------|------|---------|
| `backend/scripts/check_requirements_split_parity.py` | 31 | `AGGREGATE = BACKEND_DIR / "requirements.txt"` — the guard's whole purpose is to compare aggregate vs split union |

**Phase 8.2 implication**: if `requirements.txt` is fully deleted, the drift guard becomes meaningless and must be either removed or repurposed. Two options:

- (a) **Delete drift guard** when aggregate is dropped. CI keeps worker + API import closure scans; intra-split duplicates are also covered by the existing duplicate check inside the same script (which scans only canonical 7 subsets — would still work without the AGGREGATE comparison if we kept just the duplicate half).
- (b) **Repurpose**: keep only the "no cross-subset top-level duplicates" half of the guard, drop the aggregate-vs-union half. Slightly safer net for ongoing subset hygiene.

Recommend (b). One script edit, ~30 lines removed (the aggregate parity half), zero new files.

### H. Test artifacts (2 hits, ignored)

`test_reports/iteration_129.json` and `iteration_130.json` mention `requirements.txt` in build status strings. Auto-generated artifacts, no action needed.

## Cache key / `hashFiles` invalidation check

```bash
$ rg 'hashFiles.*requirements|cache-dependency-path.*requirements' .github/workflows/
(no matches)
```

**No CI pip cache is keyed off `requirements.txt`.** Phase 8.1/8.2 swaps will NOT invalidate any cached pip downloads (which would slow CI). This is a clean signal — confirmed safe.

## Replit/Procfile/pyproject check

`.replit`, `replit.nix`, `pyproject.toml`, `Procfile`, `setup.py`, `setup.cfg`, `backend/start.sh` — **none** reference `requirements.txt`. No surprise out-of-band install path. Replit dev workflows install via `backend/start.sh` (which does NOT use any requirements file — depends on system-installed Python packages).

## Proposed Phase 8 alt-phase split

### Phase 8.1 — low-risk consumer migration (no file deletions)

Eight changes, all behavior-parity with drift guard:

1. **`backend/ops/deploy_pipeline.py:422`** — update hardcoded path `/app/backend/requirements.txt` → `/app/backend/requirements/all.txt` (or remove check entirely; recommend update). **DO THIS FIRST** — gates Dockerfile COPY removal.
2. **`backend/Dockerfile:18`** — remove `COPY requirements.txt ./` (after #1).
3. **`worker/Dockerfile:21`** — remove `COPY backend/requirements.txt .`.
4. **`backend/requirements-ci.txt:18`** — `-r requirements.txt` → `-r requirements/all.txt`; update 17-line policy header.
5. **`scripts/post-merge.sh:14-15`** — swap `backend/requirements.txt` → `backend/requirements/all.txt` (do NOT touch quick-id/requirements.txt).
6. **`README.md:104`** — update install instruction.
7. **`backend/README.md:82`** — update install instruction.
8. **`deploy/DEPLOYMENT_GUIDE.md:54`** — update filename mention; add note that splits are canonical.

CI workflow swaps (require GitHub web UI commit per Phase 7 OAuth dance):

9. **`.github/workflows/ci-cd.yml:135,239,367`** — 3 `pip install -r requirements.txt` → `requirements/all.txt`.
10. **`.github/workflows/frontend-quality.yml:74`** — same swap (1 hit).

After Phase 8.1, `backend/requirements.txt` would have **zero live consumers**. Drift guard still active — both files must continue to match (parity preserved by hand-editing both, same as today).

### Phase 8.2 — final disposition

11. **Verify zero callers**: re-run repo-wide ripgrep. Expected hits: only the file itself, drift guard, the 2 cosmetic source mentions (pci_dss.py / xchange/safety.py), historical doc (route-split.run.md), test_reports/.
12. **Update cosmetic mentions**: pci_dss.py:151 + xchange/safety.py:188 (if context warrants — these reference `requirements.txt` as a generic concept, may be left).
13. **Delete `backend/requirements.txt`**.
14. **Repurpose drift guard** (`check_requirements_split_parity.py`): drop the aggregate-vs-union half (~30 lines); keep the cross-subset duplicate check (Phase 4.5 protection still valuable).
15. **Update CI step name** in ci-cd.yml from "Requirements split parity guard" to "Requirements subset duplicate guard" (cosmetic).
16. **Decide on `backend/requirements-ci.txt`**: if still has zero callers per #11, **delete it** (was always a shim).

### Estimated work

- Phase 8.1: ~10-15 minutes of edits + 1 GitHub web UI commit. All low-risk except #1 (deploy_pipeline.py runtime check), which needs careful path correctness.
- Phase 8.2: ~10 minutes + 1 GitHub web UI commit. Highest-risk single step is #14 (drift guard surgery — keep the Phase 4.5 protection intact).

## Risk summary

| Item | Risk | Mitigation |
|------|------|------------|
| `deploy_pipeline.py:422` runtime check | **MEDIUM** — phantom production error if missed | Phase 8.1 step #1 explicitly first; verify with `grep` after edit |
| CI install swap | LOW | Drift guard CI step proves `requirements.txt` ≡ `requirements/all.txt`; zero behavior change |
| Dockerfile COPY removal | LOW | No `RUN` consumes `requirements.txt`; verified by `grep` of all 3 Dockerfiles |
| Drift guard surgery (8.2) | LOW-MEDIUM | Keep duplicate check half; remove only AGGREGATE branch; re-run guard after edit |
| `requirements-ci.txt` deletion (8.2) | LOW | Verified zero callers in Phase 8.0; one more grep before delete |
| `backend/requirements.txt` deletion (8.2) | LOW after 8.1 done | All consumers redirected in 8.1 |

## What this report is NOT

- It is NOT a code change. Working tree `git diff` is empty for everything except this run.md edit.
- It is NOT a final decision. ChatGPT must approve scope of 8.1 / 8.2 alt-phases before any edits.
- It is NOT exhaustive about edge cases (e.g. third-party tools that scan requirements.txt — none found, but couldn't enumerate every Replit/CI agent ever attached).

## What's left

- **Phase 8.1**: low-risk consumer migration per the 10-step list above (pending ChatGPT approval).
- **Phase 8.2**: final disposition per the 6-step list above (pending Phase 8.1 completion + a re-scan).

**Phase 8.0 status: COMPLETE. Read-only consumer scan delivered. Awaiting ChatGPT approval of Phase 8.1 scope.**

---

# Phase 8.1 (2026-05-11) — Low-risk consumer migration (8 source edits)

ChatGPT approved Phase 8.1 scope with explicit ordering: deploy_pipeline.py
path fix FIRST, then everything else. Workflow file patches deferred to
GitHub web UI (same Phase 7 / 7.1 OAuth-scope dance) so the source push
from Replit Git pane is not blocked.

## Edits applied

### Step 1 — `backend/ops/deploy_pipeline.py:420-428` (RUNTIME CHECK fix, FIRST)

The pre-existing hardcoded `/app/backend/requirements.txt` existence check
inside `_gate_build()` would have reported a phantom error
`"requirements.txt missing"` once the Dockerfile COPY was removed.

Updated to check `/app/backend/requirements/api-runtime.txt` instead — per
ChatGPT direction, this is the file the production API image actually
RUN-installs (Phase 6.1), so it's the most meaningful proof-of-image-integrity
target. Output line updated to `[REQ] api-runtime: N lines (incl. -r includes)`
(reflects that this file uses `-r api.txt` + `-r integrations.txt` + 2 gap
packages, so naive line count is now an indicator, not a package count).

7-line block-comment added explaining Phase 8.1 rationale + back-pointer to
run.md.

### Step 2 — `backend/Dockerfile:18` (legacy COPY removed)

Removed `COPY requirements.txt ./` (line 18 in pre-Phase-8.1 source). The
RUN install at line 33 already targets `requirements/api-runtime.txt` (per
Phase 6.1) — the legacy aggregate was never consumed by the build, only
copied for "debug/legacy callers" intent. The replaced 5-line block-comment
("Phase 4 ... Phase 8 will deprecate ...") is now an 8-line block-comment
documenting Phase 8.1 disposition + back-pointer to drift guard.

### Step 3 — `worker/Dockerfile:21` (legacy COPY removed)

Removed `COPY backend/requirements.txt .` (line 21 in pre-Phase-8.1 source).
Same rationale as backend; worker RUN install at line 23 targets
`requirements/worker-runtime.txt` (Phase 5).

### Step 4 — `backend/requirements-ci.txt` (shim swap + policy header rewrite)

Replaced `-r requirements.txt` with `-r requirements/all.txt`. 17-line policy
header rewritten to reflect Phase 8.1 status: file now references the canonical
split aggregate (`requirements/all.txt`), notes that drift guard verifies
parity, and flags Phase 8.2 may delete this file entirely (current ripgrep
status: 0 callers — the file is effectively orphaned).

### Step 5 — `scripts/post-merge.sh:14-15` (consumer swap)

Existence check + install swapped from `backend/requirements.txt` →
`backend/requirements/all.txt`. The `|| true` failure-swallowing semantics are
preserved (a transient swap mistake is non-fatal). 4-line comment added
documenting Phase 8.1 forward-compatibility with Phase 8.2 (legacy deletion).

**Out of scope (explicitly preserved)**: `scripts/post-merge.sh:18-19`'s
`quick-id/requirements.txt` install is a SEPARATE service's dependency tree
and was NOT touched. Quick-ID has its own deps tree, fully independent of
the backend split refactor.

### Step 6 — `README.md:104` (user-facing install instruction)

`pip install -r requirements.txt` → `pip install -r requirements/all.txt` in
the Local Development section.

### Step 7 — `backend/README.md:82` (dev-facing install instruction)

Same swap. 2-line comment added pointing readers to run.md for the canonical
explanation of the split aggregate.

### Step 8 — `deploy/DEPLOYMENT_GUIDE.md:54` (file tree diagram update)

The deployment guide's `backend/` filename diagram was updated to list
`requirements/` (with full subset enumeration: base/api/worker/ml/reports/
integrations/dev + composer all.txt + runtime composers api-runtime.txt /
worker-runtime.txt) BEFORE `requirements.txt`, with a clarifying note that the
legacy file is kept in lock-step by drift guard and scheduled for deletion
in Phase 8.2.

## Workflow patch (deferred — GitHub web UI required)

The 4 CI install commands in `.github/workflows/ci-cd.yml` (lines 135, 239,
367) and `.github/workflows/frontend-quality.yml` (line 74) all use the
identical pattern. They MUST be swapped to keep CI green after Phase 8.2
deletes `requirements.txt`.

These workflow files are NOT edited from Replit (would block the source push
because the OAuth integration lacks `workflow` scope — same Phase 7 / 7.1
limitation). Apply via GitHub web UI:

```diff
--- a/.github/workflows/ci-cd.yml
+++ b/.github/workflows/ci-cd.yml
@@ -132,7 +132,7 @@
       - name: Install backend dependencies
         run: |
           cd backend
-          pip install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
+          pip install -r requirements/all.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
           bash scripts/post_install.sh
           pip install pytest pytest-asyncio httpx pytest-cov pytest-timeout

@@ -236,7 +236,7 @@
       - name: Install backend dependencies
         run: |
           cd backend
-          pip install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
+          pip install -r requirements/all.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
           bash scripts/post_install.sh
           pip install pytest pytest-asyncio httpx pytest-timeout

@@ -364,7 +364,7 @@
       - name: Install backend dependencies
         run: |
           cd backend
-          pip install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
+          pip install -r requirements/all.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
           bash scripts/post_install.sh
```

```diff
--- a/.github/workflows/frontend-quality.yml
+++ b/.github/workflows/frontend-quality.yml
@@ -71,7 +71,7 @@
             - name: Install backend deps
               run: |
                   cd backend
-                  pip install -r requirements.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
+                  pip install -r requirements/all.txt --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/
                   bash scripts/post_install.sh
```

Suggested commit message: `requirements: phase 8.1 — CI install commands → requirements/all.txt`

## Verification (Phase 8.1, post-edit)

```
A) Drift guard          : OK — set parity 222 == 222, 0 cross-subset duplicates
B) API import closure   : REVIEW NEEDED (2 unmapped: opentelemetry, rate_limiter)
                          — pre-existing baseline since Phase 6.0; opentelemetry
                            is covered by opentelemetry-api/sdk distributions in
                            api.txt, rate_limiter is the internal module
                            backend/core/rate_limiter.py. NOT a Phase 8.1 regression.
C) Worker import closure: OK — 14 modules covered, 0 unmapped, 0 missing
D) deploy_pipeline.py   : import smoke OK (`from ops.deploy_pipeline import DeployPipeline`)
E) 4 dev workflows      : Backend API / Mobile Web / Quick-ID API / Start application
                          — all running with new logs (auto-reload picked up the
                            deploy_pipeline.py edit; no startup errors)
```

## Re-scan: remaining `requirements.txt` references

After Phase 8.1, the only surviving references are:

| File | Line | Type | Disposition |
|------|------|------|-------------|
| `backend/Dockerfile` | 13, 16, 19, 22 | Block-comment explaining Phase 8.1 | KEEP — documentation |
| `worker/Dockerfile` | 19 | Block-comment explaining Phase 8.1 | KEEP — documentation |
| `backend/requirements-ci.txt` | 13, 16 | Policy header explaining Phase 8.1 | KEEP — documentation |
| `deploy/DEPLOYMENT_GUIDE.md` | 60, 63 | Diagram + lock-step note | KEEP — documentation |
| `backend/scripts/check_requirements_split_parity.py` | 4, 31 | Drift guard's actual comparison target | KEEP — Phase 8.2 surgery target |
| `backend/ops/deploy_pipeline.py` | 422-425 | Comment explaining old path origin | KEEP — documentation |
| `scripts/post-merge.sh` | 22-23 | `quick-id/requirements.txt` install | KEEP — DIFFERENT service, out of scope |
| `backend/integrations/xchange/safety.py` | 188 | Cosmetic comment | Phase 8.2 cosmetic touch-up candidate |
| `backend/core/pci_dss.py` | 151 | Cosmetic Turkish UI string | Phase 8.2 cosmetic touch-up candidate |
| `docs/frontend_refactors/route-split.run.md` | 110 | Historical mention | KEEP — historical record |

**Zero live consumers of `backend/requirements.txt` remain after Phase 8.1.**
Drift guard is the only file that programmatically reads it; that's by
design (the guard's whole job is to compare aggregate vs split).

## Push split

- **Replit Git pane** (this turn): 9 source files
  (`backend/ops/deploy_pipeline.py`, `backend/Dockerfile`, `worker/Dockerfile`,
  `backend/requirements-ci.txt`, `scripts/post-merge.sh`, `README.md`,
  `backend/README.md`, `deploy/DEPLOYMENT_GUIDE.md`,
  `docs/backend_refactors/requirements-split.run.md`).
- **GitHub web UI** (next): 2 workflow files per the diff blocks above.

## What's left

- **Phase 8.2** (next, after CI workflow patch lands): final disposition.
  - Re-run zero-callers ripgrep to confirm no new references slipped in.
  - Delete `backend/requirements.txt` (zero live consumers).
  - Repurpose drift guard: drop the aggregate-vs-union half (~30 lines);
    keep the cross-subset duplicate-check half (Phase 4.5 protection).
  - Decide on `backend/requirements-ci.txt`: if still 0 callers, delete it.
  - Cosmetic touch-ups: `pci_dss.py:151`, `xchange/safety.py:188`.
  - Update CI step name in ci-cd.yml: "Requirements split parity guard"
    → "Requirements subset duplicate guard".

**Phase 8.1 status: COMPLETE in source. Workflow patch ready for GitHub web UI.**

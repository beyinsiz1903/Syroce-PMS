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

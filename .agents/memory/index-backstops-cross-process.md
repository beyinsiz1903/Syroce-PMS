---
name: index_backstops registry is per-process
description: Why a Celery/worker monitor of unique-index backstop status must attempt the builds itself before reading status
---

# Monitoring index_backstops from a separate process

`shared_kernel/index_backstops.py` keeps backstop status in an **in-memory
`_registry` dict** (active/deferred/unknown), updated as a side-effect of the
lazy index builders being called. The Celery worker is a **separate process**
from the FastAPI API, so the worker's registry starts empty/unknown.

**Rule:** any worker/cron job that wants real backstop status must first call the
same lazy builders the ops endpoint uses — `routers.mice._ensure_indexes()` and
`domains.revenue.rms_router.sales._ensure_contract_indexes()` — to populate (and
self-heal) the registry in that process, then read `index_backstops.list_status()`.

**Why:** reading `list_status()` cold in a worker returns "unknown" for every
backstop, so a monitor would never see a real deferral. The ops endpoint
`/api/production-golive/uniqueness-backstops` already does this touch-then-read.

**How to apply:** to track *duration* of a deferral (alert "off longer than
threshold") you also can't rely on the registry — it has `last_attempt`/
`deferred_count` but no "first deferred at". Persist per-backstop state in Mongo
(stamp `first_deferred_at` on first sighting, clear it when the backstop reports
active again so a self-heal resets the grace window + suppression). This is the
pattern used by the Task #242 `unique_backstop_deferral_check_task` monitor.

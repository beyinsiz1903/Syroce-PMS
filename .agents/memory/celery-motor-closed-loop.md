---
name: Celery + module-level Motor = "Event loop is closed"
description: Why Celery async tasks must build a fresh Motor client per call, and how to run the night-audit engine (which uses module-level db) under Celery.
---

# Celery async tasks and the closed-loop trap

A module-level Motor client (e.g. `core.database.client`/`db`, motor 3.3.x) binds
to the **first** event loop it touches. Celery runs each task body via
`asyncio.run()`, which creates a fresh loop and **closes it** afterwards. So the
second task that reuses the module-level client raises
`RuntimeError: Event loop is closed`. Proven empirically: run1 ok, run2/run3 fail,
even with a live Mongo connection.

**Rule:** a Celery task must build its own Motor client bound to the current loop
(the booking/archival tasks already do this via `get_db()`), not reuse the
module-level client.

**Why:** prefork workers reuse the process across tasks; the first `asyncio.run`
poisons the cached loop for every later task.

## Running an engine that captured `from core.database import client, db`

The hardened night-audit engine does a module-level `from core.database import
client, db` (104+ refs, transactions use `client`). You cannot inject a db arg
without rewriting it. The working pattern (Task #362):

1. In the task body create a fresh client + `TenantAwareDBProxy`.
2. Temporarily rebind the **engine module's** names
   (`engine.client`, `engine.db`) to the fresh client/proxy, run under
   `tenant_context(tenant_id)`, then restore in `finally`.
3. Secondary touchpoints are safe because the snapshot hook receives `db`
   explicitly and the cache decorator is only on a preview path.

**How to apply:** safe under Celery's default prefork pool (one task/process at a
time, so the process-global rebind doesn't race). Would race under
gevent/eventlet concurrency in one process.

## Per-local-day atomic claim (multi-beat safe)

A once-a-minute beat dispatcher matches each tenant's LOCAL wall-clock
(`zoneinfo`, DST-aware; unknown IANA → fail-safe UTC, never silent Istanbul) and
claims the tenant via `find_one_and_update` on `last_auto_run` with `$lt
<local-midnight-as-UTC>.isoformat()`. Both stored and boundary values carry the
same `+00:00` suffix, so lexicographic ISO compare == chronological. This makes
duplicate/overlapping beats (autoscale) enqueue at most once per tenant per local
day. On Replit the worker+beat are launched from `start.sh` (gated on `REDIS_URL`
+ `SYROCE_START_CELERY`), since there is no separate worker container.

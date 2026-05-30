---
name: Transient DB error Sentry noise in background workers
description: When a background worker's per-tick/per-tenant exception handler floods Sentry with transient Atlas hiccups, wrap it with TransientFailureTracker instead of logger.error.
---

# Transient DB error Sentry noise (background workers)

Background workers that loop over tenants/ticks and `logger.error(...)` every
exception will flood Sentry (pilot/prod) with non-actionable transient MongoDB
Atlas errors: `ServerSelectionTimeoutError` ("No primary available for writes"),
`AutoReconnect`, `NetworkTimeout`, SSL handshake timeouts. These self-heal on the
next tick.

**Rule:** route such handlers through `TransientFailureTracker`
(`core/transient_db_guard.py`). Transient errors → WARNING with a per-key streak;
streak ≥ threshold → ERROR (sustained outage stays visible); non-transient errors
→ ERROR with traceback on first occurrence.

**Why:** preserves real-bug visibility while killing recurring transient-blip
alert spam. Established pattern — already used by ~11 workers (outbox, import
retry, ARI push, pre-arrival, capx, xchange bus, agency contracts, etc.).

**How to apply:** module-level `_t = TransientFailureTracker("<NAME>")`. Outer
scheduler tick uses `TransientFailureTracker.OUTER_LOOP_KEY`, inner per-tenant
loop keys by tenant id. Call `reset(key)` on success (and on intentional skips
like no-creds `continue`, so a stale streak doesn't escalate early), and
`prune(active_keys)` after the loop for memory hygiene (OUTER_LOOP_KEY auto-kept).
`try/except/else/finally`: `else` does NOT run on `continue` — reset explicitly
before `continue` if that path should clear the streak.

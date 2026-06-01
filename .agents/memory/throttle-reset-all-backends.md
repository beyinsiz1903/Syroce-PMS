---
name: always_on throttle reset must clear every backend
description: A multi-backend rate-limiter's reset()/drain must delete from whichever store check() actually wrote to, or the drain is a silent no-op.
---

# always_on throttle reset() must clear ALL backends it writes to

A `SlidingWindowThrottle` (or any rate limiter) that chooses its counter store
at runtime — Mongo for `always_on` (cross-instance), Redis when available,
in-memory deque as last resort — MUST mirror that same backend selection in
`reset()` / the success-drain path. If `check()` records a hit in one store but
`reset()` only clears a different store, the drain is a silent no-op against the
authoritative counter.

**Why:** `always_on` throttles (peer-login: AGENCY_LOGIN_*/VENDOR_LOGIN_*, and
the core LOGIN_* family) record hits in the shared Mongo `throttle_hits`
collection so the cap holds across autoscale instances. The success-path
`reset()` originally cleared only Redis + the in-memory deque, never Mongo — so
a legitimate user who mistyped before authenticating stayed at the cap and the
(cap+1)th post-success attempt tripped 429 immediately. The live stress spec
caught it as `trip_index=0`; in-process pytest passed because it exercised only
the in-memory path. This is fail-SAFE (over-blocking) but a real UX/correctness
bug, and a stress finding here is REAL, not env noise.

**How to apply:**
- Compute the key namespace once (`rkey = self._rkey(key)`); Mongo + Redis use
  `rkey`, the in-memory deque uses the RAW `key` — preserve that distinction.
- In `reset()`, when `self.always_on`, also
  `await _raw_db.throttle_hits.delete_many({"key": rkey})`, wrapped best-effort
  with a structured log (`throttle_mongo_reset_failed`). A Mongo hiccup must
  NEVER make a successful auth raise.
- Doctrine-safe: `reset()` is only ever called after successful credential
  verify, so making the designed drain actually work adds no brute-force vector.
- Cover the Mongo path in unit tests with a fake `_raw_db` (pin
  `_ensure_mongo_throttle_indexes`→True and `_get_redis`→None) — the in-memory
  test path will not catch a Mongo-backend reset regression.

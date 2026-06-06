---
name: SPA stale-chunk MIME error + autoscale cold-start login 503
description: Two durable deploy-time failure modes of a backend-served SPA + mobile client on Replit autoscale, and the heuristics that fix them.
---

# "'text/html' is not a valid JavaScript MIME type" after a redeploy

A lazy JS/CSS chunk request got an HTML body. Two compounding root causes,
both fixable as heuristics:

1. **A cacheable index.html outlives a redeploy.** If `index.html` is served
   cacheable, a browser keeps the OLD index, which references hashed chunk
   filenames that the new build deleted. **Heuristic:** serve index.html
   `no-store` from EVERY surface that emits it (root + SPA fallback); keep only
   the content-hashed asset mounts immutably cacheable.
2. **A SPA catch-all that serves index.html for ANY unmatched path** returns
   HTML (200) for a missing chunk, so the module loader throws the MIME error
   instead of seeing a clean 404. **Heuristic:** in the catch-all, a path WITH a
   file extension must get a real 404; only extension-less paths fall through to
   index.html for client routing.

**Why it matters:** the MIME error is misleading (looks like a bundler bug); the
real cause is cache + wrong 404 shape. After the fix, already-open browsers need
ONE hard refresh to drop the cached old index; then it self-heals.

# Mobile login timeout on the deployed app is NOT always CORS

Replit autoscale scales to zero. A freshly-hit cold instance answers `/api/*`
with a warm-up `503` (body `{"status":"starting"}`, Retry-After) until the
deferred bootstrap marks routes ready (~30-60s). A client that doesn't retry
`503` fails the first login → a Playwright `waitForURL` times out for all roles.

**Heuristics:**
- Make the mobile client retry the warm-up `503` — but gate the retry to the
  warm-up body SIGNATURE, not all `503`s, so a genuine handler-level `503` is
  never replayed (duplicate side effects for POST/PATCH/DELETE). Warm-up 503 is
  produced before any handler, so replaying it is side-effect-free.
- Make any retry backoff abort-aware (race the sleep against the AbortSignal) so
  a cancelled/unmounted request terminates immediately.
- A 30s `waitForURL` can still lose to a 60s cold start, so ALSO pre-warm the
  backend in CI (poll `/api/health` until 200 before the suite). Client retry
  covers real users; CI pre-warm guarantees the test starts warm.

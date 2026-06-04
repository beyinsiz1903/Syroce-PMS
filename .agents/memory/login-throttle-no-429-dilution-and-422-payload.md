---
name: Login throttle never trips 429 — dilution + 422-before-handler
description: Two non-obvious reasons a wrong-cred login burst observes zero 429s, neither of which is "limiter runs after auth".
---

A stress finding "login burst → 0 throttled / no 429" has two real root causes that are easy to misattribute to rate-limit-before-auth ordering. Verify BOTH before touching ordering.

**Layer 1 — backend throttle dilution.** A login throttle policy may be the only brute-force-critical login surface still NON-`always_on` while all its peers (agency/vendor/cashier/2FA/reset login) were already promoted to `always_on=True` (Mongo-backed, cross-instance) in earlier hardening waves. Under Replit autoscale a burst fans out across instances/processes (~burst/N < cap) so a per-instance (Redis→in-memory) counter never reaches the cap. Fix = set `always_on=True` + a stable `name=` mirroring the peers. This is NOT auth weakening: the login route ordering stays verify-first → record-on-fail → drain-on-success (Task-137); `always_on` only makes the counter cross-instance and ignores the `DISABLE_AUTH_THROTTLE` escape. `reset()` deletes from the Mongo backend for always_on, so drain-on-success still clears legit users.

**Layer 2 — payload 422s before the handler (vacuous probe).** A stress login burst that sends `email: ...@stress.invalid` is rejected by Pydantic `EmailStr` (the `.invalid` TLD is RFC 6761 special-use) with a **422 at request validation, before the login handler / `enforce` ever runs**. So `throttled=0` is guaranteed regardless of backend — the finding is vacuous, not evidence of a missing limit. Fix the TEST DATA, not the validator: use `@example.com` (RFC 2606 doc domain — syntactically valid, non-existent account → still wrong-cred 401 → reaches the throttle). Same family as a negative test that 422s for the wrong reason.

**Why:** in #204 the auth_login P2 ("no 429 on public burst") had BOTH layers; the original hypothesis (limiter-before-auth) was disproved by live inspection — ordering was already correct.

**How to apply:** to prove a login throttle live, send a HANDLER-REACHING wrong-cred payload (valid-format non-existent email, or hotel_id+username) in a >cap burst against localhost backend; always_on ignores DISABLE so you see real 429s (e.g. 10×401 + 15×429 for a 25-burst with account cap=10). `.invalid`/`.test`/`.localhost`/`.example` TLDs will 422 and tell you nothing.

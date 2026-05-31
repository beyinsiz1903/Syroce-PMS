---
name: Public burst 5xx from unprotected side-effect DB writes
description: Why a DoS-sentinel "5xx under burst" on a public auth/QR surface is often an audit-write hiccup, and the safe vs unsafe ways to harden it.
---

A public, burst-tested surface that asserts "no 5xx under burst" (DoS sentinel)
can fail not because of the auth logic but because of an *unprotected
side-effect DB write* on the failure path — most commonly an audit-log
`insert_one`. Under a cold/saturated DB (e.g. freshly republished deployment,
warmup health 503->200), that write raises and converts an already-determined
4xx into a 500.

**Rule:** wrap side-effect writes (audit logs, mirrors, WS emits) on public
failure paths in best-effort try/except so a transient DB error cannot mask the
determined outcome. Do this AFTER the auth decision and throttle are decided.

**Why:** the auth outcome (401/200) and the brute-force throttle are settled
before the audit row is written; the audit insert is pure bookkeeping, so its
failure must never page as a 5xx. This mirrors patterns already in the codebase
(QR complaint mirror, active-booking lookup).

**How to apply / hard limits:**
- NEVER swallow the auth-decision READ (user/tenant lookup). Returning a fake
  401 would be a semantic lie and "allow on error" would be fail-open — a
  security hole. The correct response to a true read outage is 5xx/503; that is
  not a code defect the sentinel should mask.
- Throttle backends should already fall through (Mongo->Redis->in-memory) and
  only raise 429, never 5xx — verify that before blaming the throttle.
- First narrow which surface 5xx'd: a garbage-token QR submit short-circuits 403
  before any DB, so it can't be the source; the auth login failure path (read +
  audit write) is the usual culprit.
- If code is unchanged vs the last green baseline, treat the 5xx as a latent
  robustness gap exposed by infra transient — harden the avoidable write, keep
  the verdict NO-GO until a warmed re-run confirms; do not claim green.

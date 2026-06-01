---
name: Stress folio void-charge closed-folio guard
description: Why a void-charge stress batch s400 is usually a legitimate closed-folio guard, not a backend regression
---

# Folio void/refund/void-payment 400 == closed-folio guard, not a bug

`void_charge` / `void_payment` (and refund) reject the operation with HTTP 400
**"Folio is {status}, cannot void charge"** whenever the parent folio's status is
not `open`. This is the documented production-hardening **closed-folio
refund/void guard**, not a failure path.

So for a stress void/refund batch, once the charge id resolves (non-voided,
has id) and a reason is supplied, the ONLY remaining 400 cause is the
closed-folio guard. Do not loosen the validator or seed — the guard is correct.

**Why it bites stress specs:** an earlier spec in the serial suite (e.g. day-turnover
force-checkout) closes a subset of folios. Critically, the folio LIST endpoint
ordering is independent of the checkout ordering, so closed folios scatter to
ANY index — a fixed `slice(N, N+k)` window routinely lands entirely on closed
folios and the test counts the legitimate guard-400 as FAIL.

**How to apply:** in the void/refund spec, fetch `folio.status` from the detail
endpoint and SKIP non-open folios (a data-state skip, never POSTed → emits no
s4xx), scanning a larger pool for OPEN voidable folios up to a small target.
Classify: void error on an OPEN folio → FAIL (preserved); voided>=1 → PASS;
voided==0 with only closed-guard/empty skips → honest REVIEW (not FAIL);
charges present on open folios but no resolvable id → serializer drift → FAIL.
This proves the success path when possible and degrades to REVIEW only on pure
data-state — no fake-green, no validator loosening.

---
name: Stress seed perf-budget recalibration vs loosening
description: When a seed-timing assertion fails marginally after the seed payload grew, recompute the budget; this is recalibration, not doctrine-banned loosening
---

# Seed perf-budget recalibration (not "loosening")

A hard `expect(seed total_ms).toBeLessThan(N)` perf assertion on the stress
seed is a budget for a SPECIFIC payload size. When the deterministic seed
payload grows (aging adds room_night_locks/payments/charges, an HR staff pool
is added, mice entities, etc.), the single-worker Atlas insert does strictly
MORE work (~4ms/doc is normal Atlas write latency, NOT a regression), so the
old budget becomes stale and the assertion fails marginally (e.g. 30.7s vs a
30s cap set when the payload was smaller).

**Rule:** recompute the budget to reflect the grown payload + Atlas variance,
keeping margin that still catches a GROSS blowup (a real perf regression).
Always keep recording the actual `total_ms` in the rec() note — never hide it.

**Why this is NOT the doctrine-banned "assertion gevşetme":** the doctrine
bans loosening to mask a REAL product/security/correctness failure or to
fake-green a regression. A perf budget on TEST-HARNESS seeding that the payload
legitimately outgrew is the timing analogue of the deterministic seed-count
drift rule (recompute the constant when the factory formula changes, don't
loosen blindly). Confirm it's a genuine cost increase (more docs inserted),
not a slowdown per doc, before recalibrating.

**How to apply:** before changing the number, (1) git blame the assertion to
see when the budget was set, (2) confirm the seed payload grew since then,
(3) confirm per-doc latency is normal (total/doc_count), (4) set the new budget
with a comment stating the growth drivers + that gross blowups still fail, and
(5) get the operator's sign-off — this touches the explicit "no assertion
loosening" doctrine line, so it's a judgment call, not a silent edit.

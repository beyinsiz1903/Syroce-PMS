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

**Cold-start variance is a SEPARATE failure mode from payload growth — don't
conflate them.** The stress seed (`/admin/stress/seed` in `stress.py`) inserts
~50 collections SEQUENTIALLY, each via chunked `insert_many(ordered=False)` at
`INSERT_CHUNK_SIZE=100`. `timing_ms.insert` measures the whole serial loop, so
the seed wall-time is ROUND-TRIP-bound (≈ batch_count × per-batch latency), not
CPU/factory-bound (factory is ~100ms, negligible). When the CI autoscale backend
cold-starts (warmup shows a long `/health/ready`+`/api/health` 503 storm, e.g.
~300s), the seed is the first heavy DB workload against a cold Mongo/Atlas
connection pool → per-batch latency inflates (~500ms/batch vs ~50-150ms warm)
and can push the gate ~5-10% over budget. Tell-tale: per-batch = insert_ms /
(total_docs / 100) is the discriminator — warm-normal per-batch + long warmup
503s = cold-start variance (re-run on a warm backend lands under budget, as
prior green runs did); elevated per-batch on a WARM run = a real regression
worth investigating. The insert path is already optimal — do NOT "fix" it by
switching to insert_one or adding hooks; if you must kill the flake durably,
the only structural lever is parallelising independent collection inserts with
asyncio.gather (raises concurrent Atlas shared-tier load — bigger, riskier
change), otherwise re-run or recalibrate with sign-off.

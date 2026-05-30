---
name: Serial stress specs self-deplete shared sample windows
description: Why a stress data-state REVIEW/SKIP may be a vacuous self-inflicted artifact, and the safe fix (offset the sample window, do not seed).
---

# Serial stress specs that share a slice(0,N) sample can self-deplete each other's data

In the web/backend Full Stress Suite, specs that run `test.describe.configure({ mode: 'serial' })`
often harvest a shared list (folios, bookings) once in Setup and then each sub-test
does `list.slice(0, N)`. When earlier sub-tests are *destructive* (split, refund,
void, checkout) and later sub-tests sample the **same** leading slice, the later
tests find their targets already consumed → they emit a vacuous data-state finding
(e.g. "charges[] empty" / "no payment found") and the path they were meant to cover
**never actually executes**. This looks like a seed gap but is self-inflicted overlap.

**Why:** the depletion is caused by the serial ordering + overlapping `slice(0,N)`,
not by missing seed data. Test A/B typically create the data over a wide range
(e.g. folios[0..99]); only the leading folios[0..9] get destroyed by the
split/refund batches.

**How to apply:** before "fixing" such a finding with a seed, check whether an
earlier destructive sub-test consumed the same sample window. The safe fix is to
offset the later test's window PAST the destructive range but INSIDE the creation
range (e.g. `slice(10,15)`), with a fallback to the original slice when the pool is
too small. This is by-construction safe ONLY if the status ladder is preserved
byte-for-byte (no new FAIL class, no assertion loosening) — do NOT pair it with
self-creating a fresh target, because then a non-5xx rejection of the fresh target
forces either a new FAIL class or a loosened assertion (both prohibited). Prefer this
harvest re-targeting over adding a factory seed (blind-seed prohibition). Caveat: a
genuinely-executed destructive path can now surface a *real* backend bug as FAIL —
that is intended detection, not a regression.

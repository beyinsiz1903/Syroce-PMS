---
name: Harvest helper override defeats the safety-net
description: A stress spec passing an explicit maxPages/window override re-introduces the truncation the helper default was added to prevent.
---

# Harvest helper override defeats the safety-net

A shared harvest helper (`fetchAllByPrefix` in `frontend/e2e-stress/fixtures/
stress-helpers.js`) carries a deliberately large `maxPages` default (60) whose
comment documents it was bumped 8→60 so a bloated tenant fails LOUDLY (hits the
page cap) instead of SILENTLY losing prefix-matched rows past the window.

A spec that passes its OWN `{ maxPages: 8 }` override re-introduces exactly the
1600-row truncation the default was meant to fix. Symptom: a late-running spec
(e.g. `99-full-24h`) harvests the shared 500-seed prefix and finds <30 rows →
false "data scarcity" SKIP — even though the seed rows still exist. The seed rows
are the OLDEST (`created_at` desc puts them last); accumulated walk-ins from the
~90 earlier specs push them past the small window.

**Why:** the truncation is silent — the harvest returns a short list, not an
error, so it reads as "data gone" rather than "window too small."

**How to apply:** when a stress data-state SKIP says "scarcity / empty pool" but
the foundation seed should still exist, grep the spec for an explicit harvest
override (`maxPages`/`pageSize`) before suspecting depletion or seeding. The fix
is to drop the override (or align it to the helper default), NOT to re-seed
(blind-seed) or loosen the count gate (skip-as-pass). Rooms usually survive a
small window (not inflated by walk-ins); bookings are the ones that fall out.

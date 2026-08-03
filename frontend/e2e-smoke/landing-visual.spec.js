// ─────────────────────────────────────────────────────────────────────────
// Landing page MOBILE VISUAL baseline — locks in the elegant mobile look
// established by Task #127.
// ─────────────────────────────────────────────────────────────────────────
// Task #129. `landing.spec.js` only catches horizontal overflow + CTA
// visibility. It would NOT catch:
//   - The hero collapsing back into a ~680px empty void,
//   - `whitespace-nowrap` returning on the eyebrow pill,
//   - Hero typography ballooning out of proportion again.
//
// This spec takes a Playwright visual snapshot of `/landing` at four common
// mobile widths (360 / 375 / 393 / 412 px) and fails if the rendered pixels
// drift beyond a small threshold from the committed baseline.
//
// Baselines live next to this file under:
//   frontend/e2e-smoke/landing-visual.spec.js-snapshots/
// and are committed to git so any unintended visual change shows up as a
// failing CI snapshot diff with a side-by-side report.
//
// ─── Refreshing the baseline ─────────────────────────────────────────────
// When an intentional landing-page change ships and the diff is expected:
//
//   1) Run the smoke suite normally and confirm the ONLY failing tests are
//      the landing visual ones in this spec, and that the diff in the HTML
//      report matches what you intentionally changed:
//
//        E2E_BASE_URL=https://your-pilot.example.com \
//          yarn --cwd frontend test:e2e:smoke
//        # → open frontend/playwright-smoke-report/index.html
//
//   2) Re-record the baselines (only this spec, all four projects):
//
//        E2E_BASE_URL=https://your-pilot.example.com \
//          yarn --cwd frontend test:e2e:smoke \
//          --update-snapshots \
//          landing-visual.spec.js
//
//   3) Commit the updated PNGs under
//      `frontend/e2e-smoke/landing-visual.spec.js-snapshots/`. Reviewers can
//      eyeball the new baseline images in the diff. DO NOT pass
//      `--update-snapshots` to "make red tests green" — that defeats the
//      whole point of this spec.
// ─────────────────────────────────────────────────────────────────────────

import { test, expect } from '@playwright/test';

const LANDING_PATH = '/landing';

// Target mobile widths. Covers the most common phone viewports we ship to:
// 360 (Galaxy A-series / older Android), 375 (iPhone SE / iPhone 13 mini),
// 393 (Pixel 7 / iPhone 14 Pro), 412 (Pixel 7 Pro / large Android).
const MOBILE_WIDTHS = [360, 375, 393, 412];

// Pixel-diff budget. A handful of sub-pixel font-AA differences across
// runs are normal; anything bigger is a real visual regression.
//   - `threshold` is per-pixel color sensitivity (0..1, lower = stricter).
//   - `maxDiffPixelRatio` caps the % of pixels allowed to differ at all.
const SNAPSHOT_OPTS = {
    threshold: 0.2,
    maxDiffPixelRatio: 0.01, // ≤ 1% of pixels may differ
    animations: 'disabled',
    fullPage: false, // hero/landing area only — below-the-fold is content, not layout, baseline
    caret: 'hide',
    scale: 'css',
};

for (const width of MOBILE_WIDTHS) {
    test(`Landing page mobile visual baseline @ ${width}px`, async ({ page }, testInfo) => {
        // Snapshots are width-specific; if a future config adds a non-mobile
        // project (e.g. tablet/desktop), don't pollute this baseline.
        test.skip(
            testInfo.project.name !== 'mobile',
            `Visual baseline is mobile-only (project=${testInfo.project.name})`,
        );

        // Match the height of the default Pixel 7 device to keep parity with
        // the rest of the mobile smoke project; only the width varies here.
        await page.setViewportSize({ width, height: 915 });

        // Kill framer-motion animations + parallax oscillations so the
        // snapshot is deterministic across runs. `reduce` is honored by the
        // landing page (`useReducedMotion`) and gates its motion variants.
        await page.emulateMedia({ reducedMotion: 'reduce' });

        const resp = await page.goto(LANDING_PATH, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        expect(resp, `${LANDING_PATH} did not return a response`).not.toBeNull();
        expect(resp.status(), `Unexpected HTTP status for ${LANDING_PATH}`).toBeLessThan(400);

        // Wait for the hero <h1> + hero image so the snapshot isn't taken
        // mid-load with a blank image placeholder.
        await expect(page.locator('h1').first()).toBeVisible({ timeout: 15_000 });
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});

        // Give framer-motion entrance transitions one frame to settle even
        // under reduced-motion (some `initial`/`animate` deltas still tween
        // a tiny amount before snapping).
        await page.waitForTimeout(400);

        // Snapshot the in-viewport hero area. We deliberately do NOT
        // fullPage-snapshot the whole landing page because:
        //   - It includes lazy-loaded sections / animated counters,
        //   - It would be ~6000px tall and dominated by content text that
        //     legitimately changes more often than layout does.
        // The mobile landing regressions we care about (empty void above the
        // fold, nowrap pill, ballooning typography) all live in the hero.
        await expect(page).toHaveScreenshot(
            `landing-mobile-${width}.png`,
            SNAPSHOT_OPTS,
        );
    });
}

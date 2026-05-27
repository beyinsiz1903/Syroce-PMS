// ─────────────────────────────────────────────────────────────────────────
// Landing page layout smoke — catches mobile horizontal overflow regressions.
// ─────────────────────────────────────────────────────────────────────────
// Task #122. The public landing route (`/landing`) previously shipped a
// hero block that overflowed horizontally on common phone widths and was
// only noticed visually. This spec runs the page at a representative mobile
// width (~375px) and a desktop width (~1280px) and asserts:
//   1) `document.documentElement.scrollWidth <= window.innerWidth` (no
//      horizontal scroll / overflow).
//   2) The hero `<h1>` is visible inside the viewport.
//   3) The primary CTA buttons ("Giriş Yap", "Tedarikçi Girişi",
//      "Demo Talep Et") are visible inside the viewport.
//
// No login required — `/landing` is a public route. Spec is intentionally
// tiny (one navigate per viewport) and runs in both `desktop` and `mobile`
// playwright projects without touching auth/state.
// ─────────────────────────────────────────────────────────────────────────

import { test, expect } from '@playwright/test';

const LANDING_PATH = '/landing';

// Allowed slack (px) for scrollWidth vs innerWidth. Sub-pixel rounding and
// scrollbar gutter on some engines can produce a 1–2 px diff that is NOT a
// real overflow bug. Anything larger is a regression.
const OVERFLOW_TOLERANCE_PX = 2;

const VIEWPORTS = [
    { name: 'mobile',  width: 375,  height: 812 },
    { name: 'desktop', width: 1280, height: 800 },
];

// CTA buttons / links rendered in the landing hero. Matched by accessible
// name so a copy tweak in the JSX surfaces here loudly instead of silently
// skipping the assertion.
const HERO_CTA_NAMES = [
    /giriş yap/i,
    /tedarikçi girişi/i,
    /demo talep et/i,
];

for (const vp of VIEWPORTS) {
    test(`Landing page renders without horizontal overflow @ ${vp.name} (${vp.width}px)`, async ({ page }) => {
        await page.setViewportSize({ width: vp.width, height: vp.height });

        const resp = await page.goto(LANDING_PATH, { waitUntil: 'domcontentloaded', timeout: 30_000 });
        expect(resp, `${LANDING_PATH} did not return a response`).not.toBeNull();
        // SPA — usually 200/304. Anything ≥400 means the route is broken upstream.
        expect(resp.status(), `Unexpected HTTP status for ${LANDING_PATH}`).toBeLessThan(400);

        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});

        // 1) No horizontal overflow.
        const { scrollWidth, innerWidth } = await page.evaluate(() => ({
            scrollWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
        }));
        test.info().annotations.push({
            type: 'landing-overflow',
            description: `viewport=${vp.width} scrollWidth=${scrollWidth} innerWidth=${innerWidth}`,
        });
        expect(
            scrollWidth,
            `Landing page horizontal overflow at ${vp.width}px: scrollWidth=${scrollWidth} > innerWidth=${innerWidth}`,
        ).toBeLessThanOrEqual(innerWidth + OVERFLOW_TOLERANCE_PX);

        // 2) Hero <h1> visible inside the viewport.
        const h1 = page.locator('h1').first();
        await expect(h1, 'Hero <h1> not visible on landing page').toBeVisible({ timeout: 15_000 });
        const h1Box = await h1.boundingBox();
        expect(h1Box, 'Hero <h1> has no bounding box').not.toBeNull();
        expect(h1Box.x, `Hero <h1> overflows left edge (x=${h1Box?.x})`).toBeGreaterThanOrEqual(-OVERFLOW_TOLERANCE_PX);
        expect(
            h1Box.x + h1Box.width,
            `Hero <h1> overflows right edge at ${vp.width}px (right=${h1Box.x + h1Box.width})`,
        ).toBeLessThanOrEqual(vp.width + OVERFLOW_TOLERANCE_PX);

        // 3) Hero CTAs visible inside the viewport.
        for (const ctaName of HERO_CTA_NAMES) {
            const cta = page.getByRole('button', { name: ctaName }).or(page.getByRole('link', { name: ctaName })).first();
            await expect(cta, `CTA ${ctaName} not visible on landing page`).toBeVisible({ timeout: 10_000 });
            const box = await cta.boundingBox();
            expect(box, `CTA ${ctaName} has no bounding box`).not.toBeNull();
            expect(
                box.x,
                `CTA ${ctaName} overflows left edge at ${vp.width}px (x=${box?.x})`,
            ).toBeGreaterThanOrEqual(-OVERFLOW_TOLERANCE_PX);
            expect(
                box.x + box.width,
                `CTA ${ctaName} overflows right edge at ${vp.width}px (right=${box.x + box.width})`,
            ).toBeLessThanOrEqual(vp.width + OVERFLOW_TOLERANCE_PX);
        }
    });
}

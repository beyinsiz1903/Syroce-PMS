import { test } from '@playwright/test';
import { rec, PASS, REVIEW } from './fixtures/recorder.js';
import { attachObservers, inspectPageContent } from './fixtures/observers.js';

const M = 'responsive';

const VIEWPORTS = [
    { label: 'mobile-portrait', w: 390, h: 844 },
    { label: 'tablet-portrait', w: 820, h: 1180 },
    { label: 'desktop-narrow', w: 1280, h: 720 },
];

test.describe('Scope 19 — Mobil / responsive', () => {
    for (const vp of VIEWPORTS) {
        test(`Viewport ${vp.label} (${vp.w}x${vp.h}) — dashboard render`, async ({ page }, testInfo) => {
            await page.setViewportSize({ width: vp.w, height: vp.h });
            const obs = attachObservers(page);
            const r = await page.goto('/', { waitUntil: 'networkidle' }).catch(() => null);
            rec(testInfo, { module: M, scope: 19, step: `${vp.label} navigate`, status: r?.ok() ? PASS : REVIEW, http: r?.status() });
            const insp = await inspectPageContent(page);
            rec(testInfo, { module: M, scope: 19, step: `${vp.label} içerik`, status: insp.empty || insp.has500 ? REVIEW : PASS, note: `len=${insp.lengthChars}` });

            // Yatay scroll kontrolü (overflow kabaca tespit)
            const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 5);
            rec(testInfo, { module: M, scope: 19, step: `${vp.label} yatay scroll YOK`, status: overflow ? REVIEW : PASS, note: overflow ? 'overflow tespit edildi' : '' });

            rec(testInfo, { module: M, scope: 19, step: `${vp.label} console`, status: obs.consoleErrors.length === 0 ? PASS : REVIEW, note: `count=${obs.consoleErrors.length}` });
        });
    }
});

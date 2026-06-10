// ─────────────────────────────────────────────────────────────────────────
// F10A — Mobile smoke matrix (render-only).
// ─────────────────────────────────────────────────────────────────────────
// Per role (frontdesk / gm / housekeeping / guest):
//   1) Login once via UI
//   2) Visit every screen for that role (sequential, same page context)
//   3) Per screen: inspect content, scan console errors, scan PII/tokens
//
// Acceptance (F10_MOBILE_COVERAGE_ROADMAP.md §5 F10A):
//   - All screens render (no empty / error UI)
//   - Runtime errors = 0 (allowlist-filtered)
//   - No JWT / PAN / bearer pattern in DOM source
// ─────────────────────────────────────────────────────────────────────────

import { test, expect } from '@playwright/test';
import { SCREENS, type Role } from './routes';
import { attachObservers, inspectPageContent, loginAsRole } from './fixtures';

const ROLES: Role[] = ['frontdesk', 'gm', 'housekeeping', 'guest'];

// ─────────────────────────────────────────────────────────────────────────
// F10A — Front-desk Reservations + Availability interactive flow.
// ─────────────────────────────────────────────────────────────────────────
// The render-only matrix above proves both tabs mount. This block goes one
// step further (Task #263) and exercises the two new front-desk surfaces the
// way staff actually use them, so regressions in navigation, search input, or
// the availability grid surface here rather than silently in production:
//   1) Reservations tab renders its search box + list, and tapping a
//      reservation row opens the detail view.
//   2) Availability tab renders its start-date input + occupancy grid.
//
// Both screens depend on live pilot data. We assert the chrome (search box /
// grid input) unconditionally — that proves the screen mounted — and the
// tap-through is gated on a real reservation row existing. When the pilot has
// zero reservations we record an annotation and assert the by-design empty
// state instead of faking a green tap (no skip-as-pass).
test.describe.serial('Mobile smoke · frontdesk · reservations + availability', () => {
    test('[frontdesk] reservations search renders → tap opens detail', async ({ page }) => {
        const obs = attachObservers(page);
        await loginAsRole(page, 'frontdesk');

        await page.goto('/reservations', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});

        const searchBox = page.locator('[data-testid="smoke-reservations-search"]').first();
        await expect(searchBox, 'Reservations search box render olmadı').toBeVisible({
            timeout: 20_000,
        });

        // Wait for the list query to settle into rows OR the by-design empty
        // state before deciding whether a tap-through is exercisable.
        const rows = page.locator('[data-testid="smoke-reservation-row"]');
        await rows
            .first()
            .waitFor({ state: 'visible', timeout: 15_000 })
            .catch(() => {});
        const rowCount = await rows.count();
        test.info().annotations.push({
            type: 'reservation-rows',
            description: String(rowCount),
        });

        if (rowCount > 0) {
            await rows.first().click();
            await page.waitForURL(/\/reservation(\?|$)/, { timeout: 20_000 });
            const inspect = await inspectPageContent(page);
            expect(
                inspect.ok,
                `Rezervasyon detayı boş/hata ekranı: ${inspect.reason}`,
            ).toBeTruthy();
            // Detail-only chrome: the stay card heading is unique to the
            // detail view and absent from the list, so its presence proves
            // the navigation landed on the detail screen.
            await expect(
                page.getByText('Konaklama', { exact: true }).first(),
                'Rezervasyon detayı (Konaklama) görünmüyor',
            ).toBeVisible({ timeout: 15_000 });
            expect(inspect.pii_findings ?? [], 'Detayda PII leak').toHaveLength(0);
        } else {
            // Honest empty-state assertion — the screen mounted and rendered
            // its own "no reservations" copy; we do NOT pass a tap we never
            // performed.
            await expect(
                page.getByText('Rezervasyon bulunamadı').first(),
                'Boş liste durumu render olmadı',
            ).toBeVisible({ timeout: 15_000 });
        }

        const { consoleErrors } = obs.flush();
        expect(
            consoleErrors,
            `Reservations console error: ${JSON.stringify(consoleErrors.slice(0, 3))}`,
        ).toHaveLength(0);
    });

    test('[frontdesk] availability grid renders', async ({ page }) => {
        const obs = attachObservers(page);
        await loginAsRole(page, 'frontdesk');

        await page.goto('/availability', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});

        const startInput = page.locator('[data-testid="smoke-availability-start"]').first();
        await expect(startInput, 'Availability başlangıç input render olmadı').toBeVisible({
            timeout: 20_000,
        });

        const inspect = await inspectPageContent(page);
        expect(inspect.ok, `Müsaitlik boş/hata ekranı: ${inspect.reason}`).toBeTruthy();
        expect(inspect.pii_findings ?? [], 'Müsaitlikte PII leak').toHaveLength(0);

        const { consoleErrors } = obs.flush();
        expect(
            consoleErrors,
            `Availability console error: ${JSON.stringify(consoleErrors.slice(0, 3))}`,
        ).toHaveLength(0);
    });
});

for (const role of ROLES) {
    const screens = SCREENS.filter((s) => s.role === role);

    test.describe.serial(`Mobile smoke · ${role}`, () => {
        test(`[${role}] login → group root`, async ({ page }) => {
            const obs = attachObservers(page);
            await loginAsRole(page, role);
            await page.waitForLoadState('networkidle', { timeout: 20_000 }).catch(() => {});
            const inspect = await inspectPageContent(page);
            const { consoleErrors, networkErrors } = obs.flush();

            expect(inspect.ok, `Post-login boş/hata ekranı (${role}): ${inspect.reason}`).toBeTruthy();
            expect(consoleErrors, `Login sonrası console error (${role}): ${JSON.stringify(consoleErrors.slice(0, 3))}`).toHaveLength(0);
            expect(inspect.pii_findings ?? [], `Login sonrası PII leak (${role})`).toHaveLength(0);

            if (networkErrors.length) {
                test.info().annotations.push({
                    type: 'network-errors',
                    description: JSON.stringify(networkErrors.slice(0, 5)),
                });
            }
        });

        for (const s of screens) {
            test(`[${role}] ${s.crit} ${s.label} (${s.path})`, async ({ page }) => {
                const obs = attachObservers(page);
                await loginAsRole(page, role);

                const navStart = Date.now();
                const navResp = await page
                    .goto(s.path, { waitUntil: 'domcontentloaded', timeout: 30_000 })
                    .catch(() => null);
                await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});
                const navDurationMs = Date.now() - navStart;
                const httpStatus = navResp?.status() ?? 0;

                const inspect = await inspectPageContent(page);
                const { consoleErrors, networkErrors } = obs.flush();

                test.info().annotations.push({ type: 'screen-key', description: s.key });
                test.info().annotations.push({ type: 'screen-path', description: s.path });
                test.info().annotations.push({ type: 'screen-crit', description: s.crit });
                test.info().annotations.push({ type: 'http-status', description: String(httpStatus) });
                test.info().annotations.push({ type: 'nav-ms', description: String(navDurationMs) });
                test.info().annotations.push({ type: 'inspect', description: JSON.stringify(inspect) });
                test.info().annotations.push({
                    type: 'console-errors-count',
                    description: String(consoleErrors.length),
                });
                test.info().annotations.push({
                    type: 'network-errors-count',
                    description: String(networkErrors.length),
                });

                // Acceptance — render-only smoke is strict on these three.
                expect(inspect.ok, `Empty/error UI (${s.key}): ${inspect.reason}`).toBeTruthy();
                expect(
                    consoleErrors,
                    `Console error (${s.key}): ${JSON.stringify(consoleErrors.slice(0, 3))}`,
                ).toHaveLength(0);

                // PII/token findings are P0 — render-only smoke must not
                // surface any JWT / PAN / bearer string in the DOM.
                const findings = inspect.pii_findings ?? [];
                if (findings.length) {
                    test.info().annotations.push({
                        type: 'finding',
                        description: JSON.stringify({
                            severity: 'P0',
                            module: 'mobile_smoke_pii_scan',
                            screen: s.key,
                            findings,
                        }),
                    });
                }
                expect(findings, `PII/token leak in DOM (${s.key}): ${findings.join(',')}`).toHaveLength(0);

                // Surface — but don't hard-fail — network 4xx/5xx so a
                // misconfigured backend is visible in the report without
                // masking the render-only acceptance.
                if (networkErrors.length) {
                    test.info().annotations.push({
                        type: 'network-errors',
                        description: JSON.stringify(networkErrors.slice(0, 5)),
                    });
                }
            });
        }
    });
}

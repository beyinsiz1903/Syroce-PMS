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

// Mirrors of the Turkish labels in mobile/src/i18n/tr.ts. Kept as literals
// here because the e2e project's tsconfig is scoped to mobile/e2e/ and does
// not include src/. If those copy strings change, update them here too.
const tr_clearFilters = 'Filtreleri temizle'; // reservations.clearFilters
const tr_clear = 'Temizle'; // datePicker.clear
const tr_today = 'Bugün'; // datePicker.today
const tr_close = 'Kapat'; // datePicker.close

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

    // ─────────────────────────────────────────────────────────────────
    // F10A — Reservations date-range picker (Task #287).
    // ─────────────────────────────────────────────────────────────────
    // The two former check-in / check-out single pickers were merged into
    // one range picker (smoke-reservations-daterange). This step proves
    // the range actually drives the list filter end-to-end:
    //   1) Open the picker, pick a start day then an end day in the same
    //      (current) month — days 10 and 20 always exist and the picker
    //      opens on today's month, so this is deterministic without month
    //      navigation. We don't pass minimumDate here so both are tappable.
    //   2) Assert the SEARCH request actually carries check_in & check_out
    //      query params for the picked ISO days — that is honest proof the
    //      list is filtered (row counts depend on live pilot data and are
    //      not asserted; the request contract is the deterministic signal).
    //   3) Re-open and assert both endpoints are aria-selected — the range
    //      state (start + end + highlighted span) round-trips.
    //   4) allowClear: tap "Temizle" and assert the next search request
    //      drops check_in/check_out (filter cleared, no fake-green).
    //   5) "Bugün": tap Today and assert today's cell becomes selected and
    //      the picker stays open to pick the end (range-mode semantics).
    test('[frontdesk] reservations date-range picker filters + clears', async ({ page }) => {
        const obs = attachObservers(page);
        await loginAsRole(page, 'frontdesk');

        await page.goto('/reservations', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});

        const trigger = page.locator('[data-testid="smoke-reservations-daterange"]').first();
        await expect(trigger, 'Tarih aralığı seçici render olmadı').toBeVisible({
            timeout: 20_000,
        });

        // Deterministic in-month days: the picker opens on today's month and
        // the reservations picker sets no minimumDate, so 10 and 20 always
        // exist and are tappable regardless of the current date.
        const now = new Date();
        const pad = (n: number) => String(n).padStart(2, '0');
        const monthPrefix = `${now.getFullYear()}-${pad(now.getMonth() + 1)}`;
        const startISO = `${monthPrefix}-10`;
        const endISO = `${monthPrefix}-20`;
        const todayISO = `${monthPrefix}-${pad(now.getDate())}`;

        const SEARCH = '/api/reservations/search';
        const dayCell = (iso: string) => page.locator(`[aria-label="${iso}"]`).first();

        // 1) Open picker → calendar grid visible.
        await trigger.click();
        await expect(dayCell(startISO), 'Takvim açılmadı / başlangıç günü yok').toBeVisible({
            timeout: 15_000,
        });

        // 2) Pick start, then end — the both-bounds search request is the
        //    deterministic "list is filtered" proof.
        await dayCell(startISO).click();
        const rangeReq = page.waitForRequest(
            (req) =>
                req.url().includes(SEARCH) &&
                req.url().includes(`check_in=${startISO}`) &&
                req.url().includes(`check_out=${endISO}`),
            { timeout: 15_000 },
        );
        await dayCell(endISO).click();
        await rangeReq;

        // Range complete → modal closes, trigger shows the range, and the
        // "clear filters" affordance appears (hasFilters became true).
        await expect(dayCell(startISO), 'Aralık seçimi sonrası modal kapanmadı').toBeHidden({
            timeout: 10_000,
        });
        await expect(trigger, 'Seçili aralık tetikleyicide görünmüyor').toContainText('→', {
            timeout: 10_000,
        });
        await expect(
            page.getByText(tr_clearFilters).first(),
            'Filtre temizleme bağlantısı çıkmadı',
        ).toBeVisible({ timeout: 10_000 });

        // 3) Re-open → both endpoints round-trip as selected (range state +
        //    in-between highlighting are driven by these same bounds).
        await trigger.click();
        await expect(
            dayCell(startISO),
            'Yeniden açılışta başlangıç günü seçili değil',
        ).toHaveAttribute('aria-selected', 'true', { timeout: 10_000 });
        await expect(
            dayCell(endISO),
            'Yeniden açılışta bitiş günü seçili değil',
        ).toHaveAttribute('aria-selected', 'true', { timeout: 10_000 });

        // 4) allowClear → "Temizle" wipes the range; the next search request
        //    must drop both date params (no skip-as-pass on the clear path).
        const clearedReq = page.waitForRequest(
            (req) =>
                req.url().includes(SEARCH) &&
                !req.url().includes('check_in=') &&
                !req.url().includes('check_out='),
            { timeout: 15_000 },
        );
        await page.getByText(tr_clear, { exact: true }).first().click();
        await clearedReq;
        await expect(dayCell(startISO), 'Temizle sonrası modal kapanmadı').toBeHidden({
            timeout: 10_000,
        });
        await expect(trigger, 'Temizle sonrası aralık hâlâ görünüyor').not.toContainText('→', {
            timeout: 10_000,
        });

        // 5) "Bugün" → starts a fresh range at today and KEEPS the picker
        //    open (range mode picks the end next), unlike single mode which
        //    would close. Assert today is selected and the grid is still up.
        await trigger.click();
        await expect(dayCell(todayISO), 'Bugün öncesi takvim açılmadı').toBeVisible({
            timeout: 15_000,
        });
        await page.getByText(tr_today, { exact: true }).first().click();
        await expect(
            dayCell(todayISO),
            '"Bugün" sonrası bugünün günü seçili değil',
        ).toHaveAttribute('aria-selected', 'true', { timeout: 10_000 });
        // Still open (range mode) → close the modal cleanly via "Kapat".
        await page.getByText(tr_close, { exact: true }).first().click();
        await expect(dayCell(todayISO), '"Kapat" modalı kapatmadı').toBeHidden({
            timeout: 10_000,
        });

        const inspect = await inspectPageContent(page);
        expect(inspect.ok, `Rezervasyon ekranı boş/hata: ${inspect.reason}`).toBeTruthy();
        expect(inspect.pii_findings ?? [], 'Tarih aralığı akışında PII leak').toHaveLength(0);

        const { consoleErrors } = obs.flush();
        expect(
            consoleErrors,
            `Date-range console error: ${JSON.stringify(consoleErrors.slice(0, 3))}`,
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

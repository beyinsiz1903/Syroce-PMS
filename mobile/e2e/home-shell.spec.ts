// ─────────────────────────────────────────────────────────────────────────
// F10A — Mobile smoke · common shell `(home)` (Task #334 / Faz 0 backbone).
// ─────────────────────────────────────────────────────────────────────────
// Task #327 introduced the unified Tier-1 common shell every STAFF role lands
// in (the role-specific Tier-2 groups stay reachable from inside it, guests
// keep their own experience). The bottom-tab backbone is:
//   Bildirimler (index) · Bugün (today) · Görevlerim (tasks) ·
//   Mesajlar (messages) · Onaylarım (approvals, permission-gated) ·
//   Arama (search) · Profil (profile)
//
// The F10A render-only matrix in smoke.spec.ts predates this shell and does
// not cover its tabs. This spec closes that gap with three honest checks:
//
//   1) Every visible tab mounts on a real tab PRESS (not a URL hop, which
//      would dodge the `/messages` group collision with (guest)) and the
//      data-backed tabs actually round-trip their hub endpoint (2xx). The
//      correct screen is confirmed by a per-screen testID, so a mis-routed
//      collision FAILS instead of false-passing.
//   2) The permission-gated "Onaylarım" tab is HIDDEN in the tab bar for a
//      role without approval visibility (entitlement gating), while the
//      screen itself still mounts render-only when reached by its own URL.
//   3) Profile Tier-2 module visibility differs BY ROLE entitlement — the
//      same screen surfaces a different module set for front-desk vs
//      housekeeping (deterministic, keyed on the normalized role that the
//      group routing already proves), so a regression that ignores the
//      entitlement flags surfaces here.
//
// Sessions are restored from auth.setup.ts storageState (one UI login per
// role) exactly like smoke.spec.ts — no per-screen re-login, so the matrix
// never fans out enough logins to trip the backend auth rate limit from the
// single CI runner IP. Operator runs the suite via MOBILE_E2E_* secrets +
// GH Actions dispatch; the agent does not dispatch the full mobile suite.
// ─────────────────────────────────────────────────────────────────────────

import { test, expect, type Page } from '@playwright/test';
import { attachObservers, authFile, inspectPageContent } from './fixtures';

// Hub endpoints backing the data-driven tabs (mirror src/api/hub.ts). Visiting
// the tab mounts its screen which fires the matching React Query — proving the
// shell is wired to live data, not just rendering chrome.
const HUB_FEED = '/api/mobile/hub/feed';
const HUB_TODAY = '/api/mobile/hub/today';
const HUB_TASKS = '/api/mobile/hub/my-tasks';

// Per-screen root testIDs (added to mobile/app/(home)/*.tsx). Selecting on
// these — not on the Turkish heading copy, which collides with the bottom-tab
// labels — is what makes a mis-routed `/messages` collision fail loudly.
const ROOT = {
    notifications: '[data-testid="smoke-home-notifications"]',
    today: '[data-testid="smoke-home-today"]',
    tasks: '[data-testid="smoke-home-tasks"]',
    messages: '[data-testid="smoke-home-messages"]',
    approvals: '[data-testid="smoke-home-approvals"]',
    search: '[data-testid="smoke-home-search"]',
    profile: '[data-testid="smoke-home-profile"]',
} as const;

const TAB = {
    today: '[data-testid="smoke-tab-today"]',
    tasks: '[data-testid="smoke-tab-tasks"]',
    messages: '[data-testid="smoke-tab-messages"]',
    approvals: '[data-testid="smoke-tab-approvals"]',
    search: '[data-testid="smoke-tab-search"]',
    profile: '[data-testid="smoke-tab-profile"]',
} as const;

// Assert the active home screen rendered cleanly: not empty / not an error
// screen, zero (allowlist-filtered) console errors, and no JWT / PAN / bearer
// string anywhere in the DOM. Returns nothing — throws via expect on failure.
async function assertScreenHealthy(
    page: Page,
    obs: ReturnType<typeof attachObservers>,
    label: string,
): Promise<void> {
    const inspect = await inspectPageContent(page);
    const { consoleErrors } = obs.flush();
    expect(inspect.ok, `Boş/hata ekranı (${label}): ${inspect.reason}`).toBeTruthy();
    expect(
        consoleErrors,
        `Console error (${label}): ${JSON.stringify(consoleErrors.slice(0, 3))}`,
    ).toHaveLength(0);
    const findings = inspect.pii_findings ?? [];
    if (findings.length) {
        test.info().annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0',
                module: 'mobile_home_shell_pii_scan',
                screen: label,
                findings,
            }),
        });
    }
    expect(findings, `PII/token leak in DOM (${label}): ${findings.join(',')}`).toHaveLength(0);
}

// ─────────────────────────────────────────────────────────────────────────
// front_desk — a staff role that lands in the common shell (not all-access,
// not guest). Holds NO approval visibility, so its tab bar omits "Onaylarım".
// ─────────────────────────────────────────────────────────────────────────
test.describe.serial('Mobile smoke · home shell · frontdesk', () => {
    test.use({ storageState: authFile('frontdesk') });

    test('[frontdesk] tüm görünür (home) sekmeleri mount olur + veri çeker', async ({ page }) => {
        const obs = attachObservers(page);

        // Landing: a staff session redirected to (home)/index (Bildirimler).
        // The feed query fires as the screen mounts — wait for the round-trip
        // and prove it is healthy (2xx), i.e. the shell pulls live data.
        const feedResp = page.waitForResponse((r) => r.url().includes(HUB_FEED), {
            timeout: 30_000,
        });
        await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await expect(
            page.locator(ROOT.notifications).first(),
            'Bildirimler sekmesi (giriş ekranı) mount olmadı',
        ).toBeVisible({ timeout: 30_000 });
        const feed = await feedResp;
        test.info().annotations.push({ type: 'hub-feed-status', description: String(feed.status()) });
        expect(feed.status(), `hub/feed beklenmeyen durum: ${feed.status()}`).toBeLessThan(400);
        await assertScreenHealthy(page, obs, 'notifications');

        // Bugün — KPI digest. Press the tab; the screen mounts and getToday
        // fires. Both the screen testID and a 2xx round-trip are required.
        const todayResp = page.waitForResponse((r) => r.url().includes(HUB_TODAY), {
            timeout: 30_000,
        });
        await page.locator(TAB.today).first().click();
        await expect(
            page.locator(ROOT.today).first(),
            'Bugün sekmesi mount olmadı',
        ).toBeVisible({ timeout: 20_000 });
        const today = await todayResp;
        test.info().annotations.push({ type: 'hub-today-status', description: String(today.status()) });
        expect(today.status(), `hub/today beklenmeyen durum: ${today.status()}`).toBeLessThan(400);
        await assertScreenHealthy(page, obs, 'today');

        // Görevlerim — my-tasks list. Same contract.
        const tasksResp = page.waitForResponse((r) => r.url().includes(HUB_TASKS), {
            timeout: 30_000,
        });
        await page.locator(TAB.tasks).first().click();
        await expect(
            page.locator(ROOT.tasks).first(),
            'Görevlerim sekmesi mount olmadı',
        ).toBeVisible({ timeout: 20_000 });
        const tasks = await tasksResp;
        test.info().annotations.push({ type: 'hub-tasks-status', description: String(tasks.status()) });
        expect(tasks.status(), `hub/my-tasks beklenmeyen durum: ${tasks.status()}`).toBeLessThan(400);
        await assertScreenHealthy(page, obs, 'tasks');

        // Mesajlar — Faz 0 placeholder (no fetch). Reaching it via the tab press
        // (not a `/messages` URL hop) is exactly what proves the (home)/messages
        // vs (guest)/messages collision is resolved within the active group: the
        // home-only testID confirms we landed on the staff messages screen.
        await page.locator(TAB.messages).first().click();
        await expect(
            page.locator(ROOT.messages).first(),
            'Mesajlar sekmesi mount olmadı (olası (guest) collision)',
        ).toBeVisible({ timeout: 20_000 });
        await assertScreenHealthy(page, obs, 'messages');

        // Arama — Faz 0 placeholder (no fetch).
        await page.locator(TAB.search).first().click();
        await expect(
            page.locator(ROOT.search).first(),
            'Arama sekmesi mount olmadı',
        ).toBeVisible({ timeout: 20_000 });
        await assertScreenHealthy(page, obs, 'search');

        // Profil — no fetch; reads the auth store. Module visibility is asserted
        // separately below; here we only confirm a clean mount.
        await page.locator(TAB.profile).first().click();
        await expect(
            page.locator(ROOT.profile).first(),
            'Profil sekmesi mount olmadı',
        ).toBeVisible({ timeout: 20_000 });
        await assertScreenHealthy(page, obs, 'profile');
    });

    test('[frontdesk] "Onaylarım" sekmesi gizli, ekran yine de mount olur', async ({ page }) => {
        const obs = attachObservers(page);

        await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await expect(
            page.locator(ROOT.notifications).first(),
            'Giriş ekranı mount olmadı',
        ).toBeVisible({ timeout: 30_000 });

        // Entitlement gating: front_desk holds neither finance nor HR approval
        // visibility, so the layout sets `href: null` for the approvals tab and
        // it must not render in the bottom bar. This is a cosmetic affordance —
        // the backend still enforces every approval action.
        await expect(
            page.locator(TAB.approvals),
            '"Onaylarım" sekmesi yetkisiz rolde görünmemeli',
        ).toHaveCount(0);

        // The hidden tab does NOT mean the route is gone — navigating to its
        // own (collision-free) URL must still render the screen render-only.
        await page.goto('/approvals', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await expect(
            page.locator(ROOT.approvals).first(),
            'Onaylarım ekranı URL ile açıldığında mount olmadı',
        ).toBeVisible({ timeout: 20_000 });
        await assertScreenHealthy(page, obs, 'approvals');
    });

    test('[frontdesk] Profil Tier-2 modül görünürlüğü role göre filtrelenir', async ({ page }) => {
        const obs = attachObservers(page);

        await page.goto('/profile', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await expect(
            page.locator(ROOT.profile).first(),
            'Profil ekranı mount olmadı',
        ).toBeVisible({ timeout: 30_000 });
        await expect(
            page.locator('[data-testid="smoke-profile-modules"]').first(),
            'Modüller kartı render olmadı',
        ).toBeVisible({ timeout: 15_000 });

        // front_desk → its OWN Tier-2 module is offered; cross-role modules are
        // not. These two are keyed on the normalized role (role === 'front_desk'
        // / role === 'housekeeping' / role === 'gm'), which the group routing
        // already proves, so the contrast is deterministic regardless of the
        // exact backend role string.
        await expect(
            page.locator('[data-testid="smoke-module-frontdesk"]').first(),
            'Ön Büro modülü front_desk için görünmeli',
        ).toBeVisible({ timeout: 15_000 });
        await expect(
            page.locator('[data-testid="smoke-module-housekeeping"]'),
            'Kat Hizmetleri modülü front_desk için görünmemeli',
        ).toHaveCount(0);
        await expect(
            page.locator('[data-testid="smoke-module-manager"]'),
            'Yönetici modülü front_desk için görünmemeli',
        ).toHaveCount(0);

        await assertScreenHealthy(page, obs, 'profile-modules-frontdesk');
    });
});

// ─────────────────────────────────────────────────────────────────────────
// housekeeping — a DIFFERENT staff role in the same shell. The contrast with
// front_desk above is the honest proof that Profile module visibility tracks
// entitlement: the very same screen exposes a different module set.
// ─────────────────────────────────────────────────────────────────────────
test.describe.serial('Mobile smoke · home shell · housekeeping', () => {
    test.use({ storageState: authFile('housekeeping') });

    test('[housekeeping] Profil Tier-2 modül görünürlüğü front_desk’ten farklı', async ({ page }) => {
        const obs = attachObservers(page);

        await page.goto('/profile', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await expect(
            page.locator(ROOT.profile).first(),
            'Profil ekranı mount olmadı',
        ).toBeVisible({ timeout: 30_000 });
        await expect(
            page.locator('[data-testid="smoke-profile-modules"]').first(),
            'Modüller kartı render olmadı',
        ).toBeVisible({ timeout: 15_000 });

        // Mirror-image of the front_desk assertion: housekeeping sees its own
        // module and NOT the front-desk one — proving the list is entitlement-
        // driven, not static.
        await expect(
            page.locator('[data-testid="smoke-module-housekeeping"]').first(),
            'Kat Hizmetleri modülü housekeeping için görünmeli',
        ).toBeVisible({ timeout: 15_000 });
        await expect(
            page.locator('[data-testid="smoke-module-frontdesk"]'),
            'Ön Büro modülü housekeeping için görünmemeli',
        ).toHaveCount(0);
        await expect(
            page.locator('[data-testid="smoke-module-manager"]'),
            'Yönetici modülü housekeeping için görünmemeli',
        ).toHaveCount(0);

        await assertScreenHealthy(page, obs, 'profile-modules-housekeeping');
    });
});

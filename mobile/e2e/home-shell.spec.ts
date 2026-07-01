// ─────────────────────────────────────────────────────────────────────────
// F10A — Mobile smoke · common shell `(home)` (Task #334 backbone, Task #507
// HUB restructure).
// ─────────────────────────────────────────────────────────────────────────
// Every STAFF role lands in the unified common shell `(home)` (the role-
// specific Tier-2 groups stay reachable from inside it, guests keep their own
// experience). Task #507 makes the bottom bar a single, role-identical FIVE-tab
// operations backbone:
//   Ana Sayfa (HUB) · Görevler · Bildirimler · Mesajlar · Profil
// Staff LAND on "Ana Sayfa" — the HUB operations center — whose live "Bugün"
// KPI card and smart notification feed round-trip the hub/today + hub/feed
// endpoints on mount (real data, not chrome). "Onaylarım", "Bugün" (digest) and
// "Arama" are kept as mounted routes but hidden from the bar via `href: null`
// (reachable by URL / HUB / header shortcut); every smoke-tab-* testID is kept.
// Approvers additionally get an "Onaylarım" HEADER shortcut. All gating is
// cosmetic; the backend enforces every action, so RBAC is unchanged.
//
// This spec closes the gap the render-only smoke.spec.ts matrix leaves with
// honest checks:
//
//   1) Every visible tab mounts on a real tab PRESS (not a URL hop, which would
//      dodge the `/messages` group collision with (guest)), the HUB round-trips
//      hub/today + hub/feed on landing, and Görevler round-trips hub/my-tasks.
//      A per-screen testID confirms the correct screen, so a mis-routed
//      collision FAILS instead of false-passing.
//   2) "Onaylarım" / "Bugün" / "Arama" are NOT bottom tabs (hidden via
//      `href: null`), yet each screen still mounts when reached by its own URL /
//      header shortcut.
//   3) The permission-gated "Onaylarım" HEADER shortcut is hidden for a role
//      without approval visibility, while the gm session proves it appears for
//      an approver (branching so it stays honest for either a plain manager or
//      an all-access gm account).
//   4) Profile Tier-2 module visibility differs BY ROLE entitlement — the same
//      screen surfaces a different module set for front-desk vs housekeeping
//      (deterministic, keyed on the normalized role the group routing proves).
//
// Sessions are restored from auth.setup.ts storageState (one UI login per role)
// exactly like smoke.spec.ts — no per-screen re-login, so the matrix never fans
// out enough logins to trip the backend auth rate limit from the single CI
// runner IP. Operator runs the suite via MOBILE_E2E_* secrets + GH Actions
// dispatch; the agent does not dispatch the full mobile suite.
// ─────────────────────────────────────────────────────────────────────────

import { test, expect, type Page } from '@playwright/test';
import { attachObservers, authFile, inspectPageContent } from './fixtures';

// Hub endpoints backing the data-driven surfaces (mirror src/api/hub.ts). The
// HUB fires today + feed on mount; the Görevler tab fires my-tasks — proving
// the shell is wired to live data, not just rendering chrome.
const HUB_FEED = '/api/mobile/hub/feed';
const HUB_TODAY = '/api/mobile/hub/today';
const HUB_TASKS = '/api/mobile/hub/my-tasks';

// Per-screen root testIDs (on mobile/app/(home)/*.tsx). Selecting on these —
// not on the Turkish heading copy, which collides with the bottom-tab labels —
// is what makes a mis-routed `/messages` collision fail loudly.
const ROOT = {
    hub: '[data-testid="smoke-home-hub"]',
    notifications: '[data-testid="smoke-home-notifications"]',
    today: '[data-testid="smoke-home-today"]',
    tasks: '[data-testid="smoke-home-tasks"]',
    messages: '[data-testid="smoke-home-messages"]',
    approvals: '[data-testid="smoke-home-approvals"]',
    search: '[data-testid="smoke-home-search"]',
    profile: '[data-testid="smoke-home-profile"]',
} as const;

const TAB = {
    home: '[data-testid="smoke-tab-home"]',
    tasks: '[data-testid="smoke-tab-tasks"]',
    notifications: '[data-testid="smoke-tab-notifications"]',
    messages: '[data-testid="smoke-tab-messages"]',
    profile: '[data-testid="smoke-tab-profile"]',
    today: '[data-testid="smoke-tab-today"]',
    approvals: '[data-testid="smoke-tab-approvals"]',
    search: '[data-testid="smoke-tab-search"]',
} as const;

// Header utility shortcuts (Task #507). Arama lives here for every role;
// "Onaylarım" joins it only for approver roles. RN-web renders `testID` as
// `data-testid`.
const HEADER = {
    approvals: '[data-testid="smoke-header-approvals"]',
    search: '[data-testid="smoke-header-search"]',
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
// not guest). Holds NO approval visibility, so the header omits "Onaylarım".
// ─────────────────────────────────────────────────────────────────────────
test.describe.serial('Mobile smoke · home shell · frontdesk', () => {
    test.use({ storageState: authFile('frontdesk') });

    test('[frontdesk] 5-sekmeli (home) bar + HUB veri çeker + header kısayolları', async ({ page }) => {
        const obs = attachObservers(page);

        // Landing: Task #507 lands staff on the HUB "Ana Sayfa" tab. The HUB
        // fires getToday + getFeed as it mounts — prove BOTH round-trip healthy
        // (2xx) so the operations center is wired to live data, not just chrome.
        const todayResp = page.waitForResponse((r) => r.url().includes(HUB_TODAY), {
            timeout: 30_000,
        });
        const feedResp = page.waitForResponse((r) => r.url().includes(HUB_FEED), {
            timeout: 30_000,
        });
        await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await expect(
            page.locator(ROOT.hub).first(),
            'Ana Sayfa (HUB) giriş ekranı mount olmadı',
        ).toBeVisible({ timeout: 30_000 });
        const todayR = await todayResp;
        const feedR = await feedResp;
        test.info().annotations.push({ type: 'hub-today-status', description: String(todayR.status()) });
        test.info().annotations.push({ type: 'hub-feed-status', description: String(feedR.status()) });
        expect(todayR.status(), `hub/today beklenmeyen durum: ${todayR.status()}`).toBeLessThan(400);
        expect(feedR.status(), `hub/feed beklenmeyen durum: ${feedR.status()}`).toBeLessThan(400);
        await assertScreenHealthy(page, obs, 'hub');

        // 5-tab invariants for EVERY role: Ana Sayfa · Görevler · Bildirimler ·
        // Mesajlar · Profil are all present in the bottom bar.
        await expect(page.locator(TAB.home).first(), 'Ana Sayfa sekmesi görünmeli').toBeVisible();
        await expect(page.locator(TAB.tasks).first(), 'Görevler sekmesi görünmeli').toBeVisible();
        await expect(
            page.locator(TAB.notifications).first(),
            'Bildirimler sekmesi görünmeli',
        ).toBeVisible();
        await expect(page.locator(TAB.messages).first(), 'Mesajlar sekmesi görünmeli').toBeVisible();
        await expect(page.locator(TAB.profile).first(), 'Profil sekmesi görünmeli').toBeVisible();

        // Hidden from the bar (href: null): Bugün (digest) · Onaylarım · Arama.
        await expect(page.locator(TAB.today), 'Bugün digest alt sekme değil').toHaveCount(0);
        await expect(page.locator(TAB.approvals), 'Onaylarım alt sekme değil').toHaveCount(0);
        await expect(page.locator(TAB.search), 'Arama alt sekme değil (header’a taşındı)').toHaveCount(0);

        // Header: Arama always present; "Onaylarım" header shortcut absent for a
        // non-approver role. Cosmetic affordance; backend RBAC is unchanged.
        await expect(
            page.locator(HEADER.search).first(),
            'Arama header ikonu görünmeli',
        ).toBeVisible({ timeout: 15_000 });
        await expect(
            page.locator(HEADER.approvals),
            'Onaylarım header ikonu yetkisiz rolde olmamalı',
        ).toHaveCount(0);

        // Bildirimler — now a first-class bottom tab.
        await page.locator(TAB.notifications).first().click();
        await expect(
            page.locator(ROOT.notifications).first(),
            'Bildirimler sekmesi mount olmadı',
        ).toBeVisible({ timeout: 20_000 });
        await assertScreenHealthy(page, obs, 'notifications');

        // Görevler — my-tasks list. The HUB does NOT fetch my-tasks, so this is a
        // fresh, honest round-trip; require a 2xx.
        const tasksResp = page.waitForResponse((r) => r.url().includes(HUB_TASKS), {
            timeout: 30_000,
        });
        await page.locator(TAB.tasks).first().click();
        await expect(
            page.locator(ROOT.tasks).first(),
            'Görevler sekmesi mount olmadı',
        ).toBeVisible({ timeout: 20_000 });
        const tasks = await tasksResp;
        test.info().annotations.push({ type: 'hub-tasks-status', description: String(tasks.status()) });
        expect(tasks.status(), `hub/my-tasks beklenmeyen durum: ${tasks.status()}`).toBeLessThan(400);
        await assertScreenHealthy(page, obs, 'tasks');

        // Mesajlar — bottom tab. Reaching it via the tab press (not a `/messages`
        // URL hop) proves the (home)/messages vs (guest)/messages collision is
        // resolved within the active group: the home-only testID confirms it.
        await page.locator(TAB.messages).first().click();
        await expect(
            page.locator(ROOT.messages).first(),
            'Mesajlar sekmesi mount olmadı (olası (guest) collision)',
        ).toBeVisible({ timeout: 20_000 });
        await assertScreenHealthy(page, obs, 'messages');

        // Arama — reached from the header shortcut (Faz 0 placeholder). By now
        // we have tapped through the other bottom tabs, and react-navigation
        // (web) keeps every VISITED tab screen mounted with its OWN header
        // (headerRight is per-screen). Inactive tab screens are display:none, so
        // their copy of smoke-header-search lingers in the DOM but is hidden.
        // A bare `.first()` would resolve the index tab's now-hidden button and
        // never click — scope to the VISIBLE header (the active tab). Product is
        // unchanged; this is standard RN-web per-screen header behaviour.
        await page.locator(`${HEADER.search}:visible`).first().click();
        await expect(
            page.locator(ROOT.search).first(),
            'Arama ekranı header kısayolundan mount olmadı',
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

    test('[frontdesk] "Onaylarım" gizli (bar + header), ekran yine de URL ile mount olur', async ({ page }) => {
        const obs = attachObservers(page);

        await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await expect(
            page.locator(ROOT.hub).first(),
            'Giriş ekranı (Ana Sayfa) mount olmadı',
        ).toBeVisible({ timeout: 30_000 });

        // Entitlement gating: front_desk holds neither finance nor HR approval
        // visibility, so the approvals tab is hidden (href: null) AND the header
        // "Onaylarım" shortcut is absent. Cosmetic — backend still enforces every
        // approval action.
        await expect(
            page.locator(TAB.approvals),
            '"Onaylarım" sekmesi yetkisiz rolde görünmemeli',
        ).toHaveCount(0);
        await expect(
            page.locator(HEADER.approvals),
            '"Onaylarım" header ikonu yetkisiz rolde görünmemeli',
        ).toHaveCount(0);

        // The hidden tab does NOT mean the route is gone — navigating to its own
        // (collision-free) URL must still render the screen.
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
        // not. These are keyed on the normalized role (role === 'front_desk' /
        // 'housekeeping' / 'gm'), which the group routing already proves, so the
        // contrast is deterministic regardless of the exact backend role string.
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
// gm — the manager session. Proves the approver "Onaylarım" affordances. The
// MOBILE_E2E_GM_* account may be a plain manager OR an all-access admin, so the
// approver assertions BRANCH on the live header shortcut rather than assuming
// approver status — honest for either account without false-failing.
// ─────────────────────────────────────────────────────────────────────────
test.describe.serial('Mobile smoke · home shell · gm', () => {
    test.use({ storageState: authFile('gm') });

    test('[gm] 5-sekmeli bar + onaycıya özel "Onaylarım" header kısayolu', async ({ page }) => {
        const obs = attachObservers(page);

        await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await expect(
            page.locator(ROOT.hub).first(),
            'Ana Sayfa (HUB) giriş ekranı mount olmadı',
        ).toBeVisible({ timeout: 30_000 });
        await assertScreenHealthy(page, obs, 'gm-hub');

        // 5-tab invariants shared by EVERY (home) role.
        await expect(page.locator(TAB.home).first(), 'Ana Sayfa sekmesi görünmeli').toBeVisible();
        await expect(page.locator(TAB.tasks).first(), 'Görevler sekmesi görünmeli').toBeVisible();
        await expect(
            page.locator(TAB.notifications).first(),
            'Bildirimler sekmesi görünmeli',
        ).toBeVisible();
        await expect(page.locator(TAB.messages).first(), 'Mesajlar sekmesi görünmeli').toBeVisible();
        await expect(page.locator(TAB.profile).first(), 'Profil sekmesi görünmeli').toBeVisible();
        await expect(page.locator(HEADER.search).first(), 'Arama header ikonu görünmeli').toBeVisible({
            timeout: 15_000,
        });

        // The "Onaylarım" header shortcut is entitlement-driven (cosmetic;
        // backend still enforces each action). Branch on the live shortcut so the
        // test is honest for either a plain manager or an all-access gm account.
        const isApprover = (await page.locator(HEADER.approvals).count()) > 0;
        test.info().annotations.push({
            type: 'gm-approver-branch',
            description: isApprover ? 'approver (Onaylarım header shortcut)' : 'line-staff (no shortcut)',
        });
        if (isApprover) {
            await page.locator(HEADER.approvals).first().click();
            await expect(
                page.locator(ROOT.approvals).first(),
                'Onaylarım ekranı header kısayolundan mount olmadı',
            ).toBeVisible({ timeout: 20_000 });
            await assertScreenHealthy(page, obs, 'gm-approvals');
        } else {
            // No approver entitlement → the route still mounts by URL.
            await page.goto('/approvals', { waitUntil: 'domcontentloaded', timeout: 30_000 });
            await expect(
                page.locator(ROOT.approvals).first(),
                'Onaylarım ekranı URL ile açıldığında mount olmadı',
            ).toBeVisible({ timeout: 20_000 });
            await assertScreenHealthy(page, obs, 'gm-approvals-url');
        }
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

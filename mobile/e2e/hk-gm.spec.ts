// ─────────────────────────────────────────────────────────────────────────
// F10A — Mobile smoke · HK task assignment + GM KPI panel (Task #339).
// ─────────────────────────────────────────────────────────────────────────
// Two surfaces shipped this phase had no e2e coverage (manual / type-check
// only), so a regression in either would surface silently in production:
//
//   1) Housekeeping task assignment — open the assign sheet from a room,
//      pick staff → task type → priority → submit. The room card's
//      long-press action menu uses the native Alert, which is a NO-OP on
//      Expo Web (react-native-web Alert.alert() does nothing), so the spec
//      drives the dedicated tap affordance (testID hk-room-assign) instead.
//      The deterministic success signal is the POST /quick-task round-trip
//      (2xx) + the modal closing — NOT a toast (the success Alert is also a
//      web no-op). When the assignee roster is empty (data-state), we assert
//      the by-design "no staff" empty state and the disabled submit instead
//      of faking a submit we never performed (no skip-as-pass).
//
//   2) GM live KPI panel — the new KPI cards (ADR, RevPAR, Açık Arıza) and
//      the new sections (Kat Hizmetleri Durumu, Kanal Performansı) render
//      and the snapshot endpoint round-trips (2xx). Row/section CONTENTS are
//      live pilot data and not asserted; the deterministic signals are the
//      KPI/section testIDs mounting + the snapshot request succeeding.
//
// Sessions are restored from auth.setup.ts storageState (one UI login per
// role) exactly like smoke.spec.ts — no per-screen re-login, so the matrix
// never fans out enough logins to trip the backend auth rate limit from the
// single CI runner IP. Operator runs the suite via MOBILE_E2E_* secrets +
// GH Actions dispatch against the deployed base_url; the agent does not
// dispatch the full mobile suite.
// ─────────────────────────────────────────────────────────────────────────

import { test, expect } from '@playwright/test';
import { attachObservers, authFile, inspectPageContent } from './fixtures';

// Endpoints backing the two surfaces (mirror src/api/rooms.ts & src/api/gm.ts).
const HK_STAFF = '/api/housekeeping/mobile/staff';
const HK_QUICK_TASK = '/api/housekeeping/mobile/quick-task';
const GM_SNAPSHOT = '/api/gm/snapshot-enhanced';

// ─────────────────────────────────────────────────────────────────────────
// housekeeping — task assignment flow.
// ─────────────────────────────────────────────────────────────────────────
test.describe.serial('Mobile smoke · housekeeping · görev atama', () => {
    test.use({ storageState: authFile('housekeeping') });

    test('[housekeeping] oda → görev atama akışı (personel → tür → öncelik → ata)', async ({
        page,
    }) => {
        const obs = attachObservers(page);

        await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        await page.waitForLoadState('networkidle', { timeout: 15_000 }).catch(() => {});

        // The rooms list query (listRooms) settles into either room cards (each
        // carrying the assign affordance) or the by-design empty state. Wait for
        // a real assign button before deciding whether the flow is exercisable.
        const assignBtn = page.locator('[data-testid="hk-room-assign"]').first();
        await assignBtn.waitFor({ state: 'visible', timeout: 20_000 }).catch(() => {});
        const roomCount = await page.locator('[data-testid="hk-room-assign"]').count();
        test.info().annotations.push({ type: 'hk-room-count', description: String(roomCount) });

        if (roomCount === 0) {
            // Honest data-state assertion: no rooms means there is nothing to
            // assign. We assert the screen mounted with its empty copy rather
            // than passing a flow we never reached (no skip-as-pass).
            await expect(
                page.getByText('Kayıt bulunamadı').first(),
                'Oda yokken boş liste durumu render olmadı',
            ).toBeVisible({ timeout: 15_000 });
            const inspect = await inspectPageContent(page);
            expect(inspect.ok, `HK ekranı boş/hata: ${inspect.reason}`).toBeTruthy();
            const { consoleErrors } = obs.flush();
            expect(
                consoleErrors,
                `HK console error: ${JSON.stringify(consoleErrors.slice(0, 3))}`,
            ).toHaveLength(0);
            return;
        }

        // 1) Open the assign sheet — the staff roster query fires on open.
        const staffResp = page.waitForResponse((r) => r.url().includes(HK_STAFF), {
            timeout: 30_000,
        });
        await assignBtn.click();
        await expect(
            page.locator('[data-testid="hk-assign-modal"]').first(),
            'Görev atama modalı açılmadı',
        ).toBeVisible({ timeout: 15_000 });
        const staff = await staffResp;
        test.info().annotations.push({
            type: 'hk-staff-status',
            description: String(staff.status()),
        });
        expect(staff.status(), `staff beklenmeyen durum: ${staff.status()}`).toBeLessThan(400);

        // 2) Branch on roster availability. Empty roster is a legitimate data
        //    state — we assert the by-design "no staff" card + disabled submit
        //    instead of faking an assignment.
        const staffOptions = page.locator('[data-testid="hk-staff-option"]');
        await staffOptions
            .first()
            .waitFor({ state: 'visible', timeout: 10_000 })
            .catch(() => {});
        const staffCount = await staffOptions.count();
        test.info().annotations.push({
            type: 'hk-staff-count',
            description: String(staffCount),
        });

        const submit = page.locator('[data-testid="hk-assign-submit"]').first();

        if (staffCount === 0) {
            await expect(
                page.locator('[data-testid="hk-no-staff"]').first(),
                'Personel yokken "Personel bulunamadı" durumu render olmadı',
            ).toBeVisible({ timeout: 10_000 });
            // Submit must stay disabled with no staff selected — guard against a
            // fake assignment with no assignee.
            await expect(submit, 'Personel yokken Ata butonu pasif olmalı').toBeDisabled();
        } else {
            // 3) Select staff → task type → priority. The submit button is
            //    disabled until a staff member is chosen, which is itself the
            //    proof selection is required.
            await expect(submit, 'Personel seçilmeden Ata butonu pasif olmalı').toBeDisabled();
            await staffOptions.first().click();
            await page.locator('[data-testid="hk-task-type-inspection"]').first().click();
            await page.locator('[data-testid="hk-priority-high"]').first().click();
            await expect(submit, 'Personel seçilince Ata butonu aktif olmalı').toBeEnabled({
                timeout: 10_000,
            });

            // 4) Submit → the POST /quick-task round-trip (2xx) is the
            //    deterministic "assignment created" signal; the success Alert is
            //    a web no-op so we do NOT key on a toast. The modal closing
            //    confirms the success path ran (setAssignRoom(null)).
            const taskResp = page.waitForResponse((r) => r.url().includes(HK_QUICK_TASK), {
                timeout: 30_000,
            });
            await submit.click();
            const created = await taskResp;
            test.info().annotations.push({
                type: 'hk-quick-task-status',
                description: String(created.status()),
            });
            expect(
                created.status(),
                `quick-task beklenmeyen durum: ${created.status()}`,
            ).toBeLessThan(400);
            await expect(
                page.locator('[data-testid="hk-assign-modal"]'),
                'Atama sonrası modal kapanmadı',
            ).toHaveCount(0, { timeout: 15_000 });
        }

        const inspect = await inspectPageContent(page);
        expect(inspect.ok, `HK ekranı boş/hata: ${inspect.reason}`).toBeTruthy();
        expect(inspect.pii_findings ?? [], 'HK atama akışında PII leak').toHaveLength(0);

        const { consoleErrors } = obs.flush();
        expect(
            consoleErrors,
            `HK atama console error: ${JSON.stringify(consoleErrors.slice(0, 3))}`,
        ).toHaveLength(0);
    });
});

// ─────────────────────────────────────────────────────────────────────────
// gm — live KPI panel: new KPIs + new sections render.
// ─────────────────────────────────────────────────────────────────────────
test.describe.serial('Mobile smoke · gm · KPI paneli', () => {
    test.use({ storageState: authFile('gm') });

    test('[gm] yeni KPI kartları + bölümler render olur + snapshot çeker', async ({ page }) => {
        const obs = attachObservers(page);

        // The snapshot query fires as the dashboard mounts — wait for the
        // round-trip and prove it is healthy (2xx), i.e. the KPIs are backed by
        // live data, not just rendered chrome.
        const snapResp = page.waitForResponse((r) => r.url().includes(GM_SNAPSHOT), {
            timeout: 30_000,
        });
        await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 30_000 });
        const snap = await snapResp;
        test.info().annotations.push({
            type: 'gm-snapshot-status',
            description: String(snap.status()),
        });
        expect(snap.status(), `snapshot beklenmeyen durum: ${snap.status()}`).toBeLessThan(400);

        // New KPI cards added this phase.
        for (const id of ['kpi-adr', 'kpi-revpar', 'kpi-open-faults']) {
            await expect(
                page.locator(`[data-testid="${id}"]`).first(),
                `${id} KPI kartı render olmadı`,
            ).toBeVisible({ timeout: 20_000 });
        }

        // New sections: housekeeping-status breakdown + channel performance.
        // Both render whenever the snapshot resolved (housekeeping is always in
        // the payload; channels renders an empty-state card when there is no
        // channel data), so the section mounting is a deterministic signal.
        await expect(
            page.locator('[data-testid="gm-hk-status"]').first(),
            'Kat Hizmetleri Durumu bölümü render olmadı',
        ).toBeVisible({ timeout: 20_000 });
        await expect(
            page.locator('[data-testid="gm-channels"]').first(),
            'Kanal Performansı bölümü render olmadı',
        ).toBeVisible({ timeout: 20_000 });

        const inspect = await inspectPageContent(page);
        expect(inspect.ok, `GM paneli boş/hata: ${inspect.reason}`).toBeTruthy();
        expect(inspect.pii_findings ?? [], 'GM panelinde PII leak').toHaveLength(0);

        const { consoleErrors } = obs.flush();
        expect(
            consoleErrors,
            `GM panel console error: ${JSON.stringify(consoleErrors.slice(0, 3))}`,
        ).toHaveLength(0);
    });
});

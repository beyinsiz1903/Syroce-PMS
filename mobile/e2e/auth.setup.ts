// ─────────────────────────────────────────────────────────────────────────
// F10A — Mobile smoke auth setup (Playwright "setup" project).
// ─────────────────────────────────────────────────────────────────────────
// Logs in ONCE per role through the real UI and persists the authenticated
// session (Playwright storageState → e2e/.auth/<role>.json). The smoke specs
// depend on this project and restore the saved session instead of logging in
// per screen.
//
// Why: the previous per-screen UI-login fan-out issued one POST /api/auth/login
// for every screen of every role. From the single CI runner IP that blew past
// the backend's auth-category rate limit (15 req / 60s / IP, see
// apm_middleware.py). The resulting raw 429 — emitted by the limiter, which sat
// inside the CORS layer — reached the Expo-Web client without CORS headers and
// surfaced as a network failure (status 0), cascading the matrix to red. One
// login per role (4 total) stays far under the cap.
//
// This file is ALSO the per-role login validation: loginAsRole only returns
// after the AuthGate redirect off /login (a genuine successful login) and
// throws with the real reason on a rejected/inactive credential.
// ─────────────────────────────────────────────────────────────────────────

import * as fs from 'node:fs';
import { test as setup, expect } from '@playwright/test';
import type { Role } from './routes';
import { AUTH_DIR, authFile, loginAsRole } from './fixtures';

const ROLES: Role[] = ['frontdesk', 'gm', 'housekeeping', 'guest'];

setup.beforeAll(() => {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
});

for (const role of ROLES) {
    setup(`authenticate ${role}`, async ({ page }) => {
        await loginAsRole(page, role);

        // loginAsRole returns only after the redirect off /login. Re-assert it
        // here so a half-open state can never be persisted as a valid session.
        expect(
            /\/login(\?|$)/.test(new URL(page.url()).pathname),
            `Login sonrası hâlâ /login ekranındayız (${role}) — oturum kaydedilmedi`,
        ).toBeFalsy();

        await page.context().storageState({ path: authFile(role) });
    });
}

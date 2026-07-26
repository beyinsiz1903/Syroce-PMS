// F7 global-teardown — prefix cleanup + idempotent verify + pilot diff
import { request } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const AUTH_DIR = path.join(process.cwd(), 'e2e-stress', '.auth');
const STATE_FILE = path.join(AUTH_DIR, 'stress-state.json');
const TOKEN_FILE = path.join(AUTH_DIR, 'stress-token.json');
const TEARDOWN_LOG = path.join(AUTH_DIR, 'teardown.json');

async function snapshot(api, token) {
    const headers = { Authorization: `Bearer ${token}` };
    const out = {};
    const r = await api.get('/api/pms/bookings', { headers, failOnStatusCode: false, timeout: 15_000 });
    if (r.ok()) {
        const j = await r.json();
        const list = Array.isArray(j) ? j : (j?.bookings || j?.items || []);
        out.bookings = list.length;
    } else { out.bookings_status = r.status(); }
    return out;
}

export default async function globalTeardown() {
    const isFullWipe = (process.env.STRESS_FULL_WIPE || '').toLowerCase() === 'true';
    let state = {};
    let tokens = {};
    let fallbackPilotToken = null;

    if (!fs.existsSync(STATE_FILE) || !fs.existsSync(TOKEN_FILE)) {
        console.warn('[stress-teardown] state/token file not found.');
        if (!isFullWipe) {
            console.warn('[stress-teardown] STRESS_FULL_WIPE=false — nothing to clean up.');
            return;
        }
        console.log('[stress-teardown] STRESS_FULL_WIPE=true, falling back to direct login...');
        
        // Manual login for full wipe fallback
        const baseUrl = process.env.E2E_BASE_URL;
        const tenantId = process.env.E2E_STRESS_TENANT_ID;
        const api = await request.newContext({ baseURL: baseUrl, ignoreHTTPSErrors: true });
        
        // Login as super admin (assuming the provided stress admin is super admin)
        const loginR = await api.post('/api/auth/login', {
            data: { email: process.env.E2E_STRESS_ADMIN_EMAIL, password: process.env.E2E_STRESS_ADMIN_PASSWORD }
        });
        if (!loginR.ok()) {
            console.error('[stress-teardown] Fallback login failed:', loginR.status());
            return;
        }
        const authData = await loginR.json();
        
        // Assume pilot tenant is 3
        const tokenR = await api.post('/api/auth/token', {
            headers: { Authorization: `Bearer ${authData.access_token}` },
            data: { tenant_id: 3 }
        });
        if (!tokenR.ok()) {
            console.error('[stress-teardown] Fallback token request failed:', tokenR.status());
            return;
        }
        fallbackPilotToken = (await tokenR.json()).access_token;
        
        state = { base_url: baseUrl, data_prefix: "", stress_tid: parseInt(tenantId, 10) };
        tokens = { pilot_token: fallbackPilotToken };
        await api.dispose();
    } else {
        state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
        tokens = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf-8'));
    }

    // CI-observed: cleanup sweeps ~30 collections by prefix and takes ~54s on the
    // deploy Atlas tier (cost is index-less per-collection scans, not delete I/O).
    // The old 60s budget left no margin, so the idempotent cleanup#2 verify
    // intermittently timed out and reddened CI even though all tests passed. Give
    // both cleanup posts ample headroom — the idempotency invariant is still
    // asserted below, it just no longer races a too-tight clock.
    const api = await request.newContext({ baseURL: state.base_url, ignoreHTTPSErrors: true, timeout: 200_000 });
    const prefix = isFullWipe ? "" : state.data_prefix;
    const log = { started_at: new Date().toISOString(), data_prefix: prefix, is_full_wipe: isFullWipe, steps: [] };

    // NOTE: /api/admin/stress/* require_super_admin → pilot bearer kullanılır.
    // 1) cleanup #1
    const c1 = await api.post('/api/admin/stress/cleanup', {
        headers: { Authorization: `Bearer ${tokens.pilot_token}` },
        data: { target_tenant_id: state.stress_tid, data_prefix: prefix, confirm_full_wipe: isFullWipe },
        failOnStatusCode: false,
        timeout: 180_000,
    });
    const c1body = c1.ok() ? await c1.json() : { error: await c1.text().catch(() => '') };
    log.steps.push({ name: 'cleanup#1', status: c1.status(), body: c1body });
    if (!c1.ok()) {
        console.error('[stress-teardown] ❌ P1: cleanup#1 failed:', c1.status());
    } else {
        const total = Object.values(c1body.deleted_counts || {}).reduce((a, b) => a + b, 0);
        console.log(`[stress-teardown] ✅ cleanup#1 deleted_total=${total} ms=${c1body?.timing_ms?.cleanup}`);
    }

    // 2) cleanup #2 (idempotent — must return all-zero)
    const c2 = await api.post('/api/admin/stress/cleanup', {
        headers: { Authorization: `Bearer ${tokens.pilot_token}` },
        data: { target_tenant_id: state.stress_tid, data_prefix: prefix, confirm_full_wipe: isFullWipe },
        failOnStatusCode: false,
        timeout: 180_000,
    });
    const c2body = c2.ok() ? await c2.json() : { error: await c2.text().catch(() => '') };
    // Idempotency must be POSITIVELY proven: a response that omits `deleted_counts`
    // would make `every(...)` vacuously true (fake-green). Require a non-empty
    // counts object AND every value === 0.
    const c2counts = (c2body && typeof c2body.deleted_counts === 'object' && c2body.deleted_counts) || null;
    const idempotent = c2.ok()
        && c2counts !== null
        && Object.keys(c2counts).length > 0
        && Object.values(c2counts).every((v) => v === 0);
    log.steps.push({ name: 'cleanup#2_idempotent', status: c2.status(), idempotent, body: c2body });
    console.log(`[stress-teardown] ${idempotent ? '✅' : '❌ P1:'} cleanup#2 idempotent=${idempotent}`);

    // 3) Pilot diff (varsa)
    if (tokens.pilot_token && state.pilot_baseline) {
        const after = await snapshot(api, tokens.pilot_token);
        const drift = (after.bookings ?? -1) - (state.pilot_baseline.bookings ?? -1);
        log.steps.push({ name: 'pilot_diff', baseline: state.pilot_baseline, after, drift });
        console.log(`[stress-teardown] pilot bookings baseline=${state.pilot_baseline.bookings} after=${after.bookings} drift=${drift}`);
        if (drift !== 0) console.error(`[stress-teardown] ❌ P1: pilot drift=${drift} (must be 0)`);
    }

    log.finished_at = new Date().toISOString();
    fs.writeFileSync(TEARDOWN_LOG, JSON.stringify(log, null, 2));
    await api.dispose();

    // Hard-fail (non-zero exit via thrown error) on defense invariant violations.
    // Architect feedback: invariants must be enforced, not just reported.
    const violations = [];
    if (!c1.ok()) violations.push(`cleanup#1 status=${c1.status()}`);
    if (!idempotent) violations.push(`cleanup#2 NOT idempotent (status=${c2.status()} body=${JSON.stringify(c2body).slice(0, 300)})`);
    const driftStep = log.steps.find((s) => s.name === 'pilot_diff');
    if (driftStep && driftStep.drift !== 0) violations.push(`pilot_drift=${driftStep.drift} (must be 0)`);
    if (violations.length) {
        throw new Error(`[stress-teardown] ❌ Defense invariant violation(s): ${violations.join('; ')}`);
    }
}

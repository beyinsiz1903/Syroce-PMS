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
    if (!fs.existsSync(STATE_FILE)) {
        console.warn('[stress-teardown] state file not found — nothing to clean up.');
        return;
    }
    const state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf-8'));
    const tokens = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf-8'));

    const api = await request.newContext({ baseURL: state.base_url, ignoreHTTPSErrors: true, timeout: 60_000 });
    const log = { started_at: new Date().toISOString(), data_prefix: state.data_prefix, steps: [] };

    // NOTE: /api/admin/stress/* require_super_admin → pilot bearer kullanılır.
    // 1) cleanup #1
    const c1 = await api.post('/api/admin/stress/cleanup', {
        headers: { Authorization: `Bearer ${tokens.pilot_token}` },
        data: { target_tenant_id: state.stress_tid, data_prefix: state.data_prefix },
        failOnStatusCode: false,
        timeout: 60_000,
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
        data: { target_tenant_id: state.stress_tid, data_prefix: state.data_prefix },
        failOnStatusCode: false,
        timeout: 60_000,
    });
    const c2body = c2.ok() ? await c2.json() : { error: await c2.text().catch(() => '') };
    const idempotent = c2.ok() && Object.values(c2body.deleted_counts || {}).every((v) => v === 0);
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
    if (!idempotent) violations.push(`cleanup#2 NOT idempotent (deleted_counts=${JSON.stringify(c2body?.deleted_counts ?? {})})`);
    const driftStep = log.steps.find((s) => s.name === 'pilot_diff');
    if (driftStep && driftStep.drift !== 0) violations.push(`pilot_drift=${driftStep.drift} (must be 0)`);
    if (violations.length) {
        throw new Error(`[stress-teardown] ❌ Defense invariant violation(s): ${violations.join('; ')}`);
    }
}

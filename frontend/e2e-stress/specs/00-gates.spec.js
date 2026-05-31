// F7 — Stress Gates spec. API-only sanity gate'leri.
import { test, expect, rec } from '../fixtures/stress-context.js';

test.describe('F7 § Stress Gates', () => {

    test('Login: stress admin token cache hazır', async ({ stressTokens }, testInfo) => {
        expect(stressTokens.stress_token, 'stress_token cache yok').toBeTruthy();
        expect(typeof stressTokens.stress_token).toBe('string');
        rec(testInfo, { module: 'gates', step: 'stress_admin_login', status: 'PASS', endpoint: 'POST /api/auth/login', http: 200 });
    });

    test('Tenant: stress tenant id env eşleşiyor', async ({ stressState }, testInfo) => {
        const envTid = process.env.E2E_STRESS_TENANT_ID;
        expect(stressState.stress_tid).toBe(envTid);
        expect(stressState.stress_tid).not.toBe(stressState.pilot_tid || '__nope__');
        rec(testInfo, { module: 'gates', step: 'stress_tid_match_and_isolated', status: 'PASS', note: stressState.stress_tid });
    });

    test('Flag: E2E_ALLOW_DESTRUCTIVE_STRESS=true', async ({}, testInfo) => {
        expect((process.env.E2E_ALLOW_DESTRUCTIVE_STRESS || '').toLowerCase()).toBe('true');
        rec(testInfo, { module: 'gates', step: 'allow_destructive_flag_on', status: 'PASS' });
    });

    test('Flag: E2E_EXTERNAL_DRY_RUN=true', async ({}, testInfo) => {
        expect((process.env.E2E_EXTERNAL_DRY_RUN || '').toLowerCase()).toBe('true');
        rec(testInfo, { module: 'gates', step: 'external_dry_run_on', status: 'PASS' });
    });

    test('Pilot: pilot tenant hedeflenmiyor (config & runtime)', async ({ stressState }, testInfo) => {
        // 1) state.gates.stress_tid_isolated true
        expect(stressState.gates.stress_tid_isolated).toBe(true);
        // 2) seed_response.target_tenant_id === stress_tid
        expect(stressState.seed_response.target_tenant_id).toBe(stressState.stress_tid);
        rec(testInfo, { module: 'gates', step: 'pilot_not_targeted', status: 'PASS' });
    });

    test('Seed response: external_calls_made boş', async ({ stressState }, testInfo) => {
        const ext = stressState.seed_response.external_calls_made;
        expect(Array.isArray(ext)).toBe(true);
        expect(ext.length).toBe(0);
        rec(testInfo, { module: 'gates', step: 'no_external_calls', status: 'PASS', note: 'payment/OTA/SMS/email/KVKK = []' });
    });

    test('Seed response: tenant_context kullanıldı', async ({ stressState }, testInfo) => {
        expect(stressState.seed_response.tenant_context_used).toBe(true);
        rec(testInfo, { module: 'gates', step: 'tenant_context_used', status: 'PASS' });
    });

    test('Seed response: gates dict tüm kapı PASS', async ({ stressState }, testInfo) => {
        const g = stressState.seed_response.gates || {};
        for (const k of ['env_stress_tid_present', 'target_matches_stress_tid', 'pilot_tid_not_targeted', 'destructive_stress_allowed']) {
            expect(g[k], `gate ${k}`).toBe(true);
        }
        rec(testInfo, { module: 'gates', step: 'backend_gates_all_pass', status: 'PASS', note: JSON.stringify(g) });
    });

    test('System health: en az REVIEW seviyesinde (best-effort)', async ({ request, stressTokens }, testInfo) => {
        const candidates = ['/api/health', '/api/system-health', '/api/admin/system/status', '/api/admin/health'];
        let last = null;
        for (const p of candidates) {
            const r = await request.get(p, {
                headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                failOnStatusCode: false, timeout: 10_000,
            }).catch((e) => ({ ok: () => false, status: () => 0, _err: e.message }));
            last = { p, status: r.status?.() ?? 0 };
            if (r.ok && r.ok()) {
                const j = await r.json().catch(() => ({}));
                rec(testInfo, { module: 'gates', step: 'system_health', status: 'PASS', endpoint: p, http: 200, note: JSON.stringify(j).slice(0, 200) });
                return;
            }
        }
        rec(testInfo, { module: 'gates', step: 'system_health', status: 'REVIEW', note: `Hiç health endpoint cevap vermedi (last=${JSON.stringify(last)}); pilot için manuel doğrula.` });
    });

    // Task #172: real ops backlog endpoint = routers.outbox_admin GET
    // /api/outbox/status (require_super_admin). Stress admin is a tenant admin,
    // NOT a global super_admin → 404; pilot_token IS super_admin. Hard-assert
    // the health-metric shape (numeric pending/retry/failed) instead of a
    // best-effort scan over non-existent /api/admin/cm/* paths.
    test('CM outbox backlog: /api/outbox/status health metrics (super_admin)', async ({ request, stressTokens }, testInfo) => {
        const r = await request.get('/api/outbox/status', {
            headers: { Authorization: `Bearer ${stressTokens.pilot_token}` },
            failOnStatusCode: false, timeout: 10_000,
        });
        expect(r.status(), '/api/outbox/status super_admin ile 200 dönmeli').toBe(200);
        const j = await r.json();
        expect(typeof j.pending, 'pending numeric').toBe('number');
        expect(typeof j.retry, 'retry numeric').toBe('number');
        expect(typeof j.failed, 'failed numeric').toBe('number');
        rec(testInfo, {
            module: 'gates', step: 'cm_outbox_backlog', status: 'PASS',
            endpoint: '/api/outbox/status', http: 200,
            note: `pending=${j.pending} retry=${j.retry} failed=${j.failed} processed_24h=${j.processed_24h} worker=${JSON.stringify(j.worker)}`.slice(0, 200),
        });
    });

    // Task #172: real CM circuit-breaker / runtime snapshot = runtime
    // enforcement cockpit GET /api/lockdown/runtime/cockpit (get_current_user).
    // Any authenticated principal works → use stress_token. Hard-assert the
    // golden-metric blocks are present.
    test('Circuit breaker: /api/lockdown/runtime/cockpit snapshot', async ({ request, stressTokens }, testInfo) => {
        const r = await request.get('/api/lockdown/runtime/cockpit', {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false, timeout: 10_000,
        });
        expect(r.status(), 'runtime cockpit authenticated ile 200 dönmeli').toBe(200);
        const j = await r.json();
        expect(j.health, 'health bloğu var').toBeTruthy();
        expect(j.flow, 'flow bloğu var').toBeTruthy();
        expect(j.reliability, 'reliability bloğu var').toBeTruthy();
        rec(testInfo, {
            module: 'gates', step: 'circuit_breaker_snapshot', status: 'PASS',
            endpoint: '/api/lockdown/runtime/cockpit', http: 200,
            note: `health=${JSON.stringify(j.health)} flow=${JSON.stringify(j.flow)}`.slice(0, 200),
        });
    });

    // Task #172: webhook delivery backlog = routers.webhook_admin GET
    // /api/webhooks/status (require_super_admin) → pilot_token. Hard-assert
    // numeric delivery/DLQ health metrics.
    test('Webhooks status: /api/webhooks/status health metrics (super_admin)', async ({ request, stressTokens }, testInfo) => {
        const r = await request.get('/api/webhooks/status', {
            headers: { Authorization: `Bearer ${stressTokens.pilot_token}` },
            failOnStatusCode: false, timeout: 10_000,
        });
        expect(r.status(), '/api/webhooks/status super_admin ile 200 dönmeli').toBe(200);
        const j = await r.json();
        expect(typeof j.deliveries_pending, 'deliveries_pending numeric').toBe('number');
        expect(typeof j.dlq_pending, 'dlq_pending numeric').toBe('number');
        expect(typeof j.dlq_total, 'dlq_total numeric').toBe('number');
        rec(testInfo, {
            module: 'gates', step: 'webhooks_status', status: 'PASS',
            endpoint: '/api/webhooks/status', http: 200,
            note: `pending=${j.deliveries_pending} succeeded_24h=${j.deliveries_succeeded_24h} dlq_pending=${j.dlq_pending} dlq_total=${j.dlq_total}`.slice(0, 200),
        });
    });
});

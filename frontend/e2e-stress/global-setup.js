// F7 global-setup — stress admin login + gate verify + 500-room seed
import { request } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const AUTH_DIR = path.join(process.cwd(), 'e2e-stress', '.auth');
const TOKEN_FILE = path.join(AUTH_DIR, 'stress-token.json');
const STATE_FILE = path.join(AUTH_DIR, 'stress-state.json');

const ROOM_COUNT = parseInt(process.env.E2E_ROOM_COUNT || '500', 10);
const STRESS_TID = process.env.E2E_STRESS_TENANT_ID;
const PILOT_TID = process.env.PILOT_TENANT_ID || '';

async function login(api, email, password) {
    const resp = await api.post('/api/auth/login', { data: { email, password }, failOnStatusCode: false });
    if (!resp.ok()) {
        const txt = await resp.text().catch(() => '');
        throw new Error(`[stress-setup] login failed (${resp.status()}): ${txt.slice(0, 200)}`);
    }
    const body = await resp.json();
    return body?.access_token || body?.token;
}

async function safeJson(p) { try { return await p; } catch { return null; } }

async function snapshot(api, token, tag) {
    const headers = { Authorization: `Bearer ${token}` };
    const out = { tag, ts: new Date().toISOString() };
    try {
        const r = await api.get('/api/pms/bookings', { headers, failOnStatusCode: false, timeout: 15_000 });
        if (r.ok()) {
            const j = await r.json();
            const list = Array.isArray(j) ? j : (j?.bookings || j?.items || []);
            out.bookings = list.length;
        } else { out.bookings_status = r.status(); }
    } catch (e) { out.bookings_err = e.message; }
    try {
        const r = await api.get('/api/pms/rooms', { headers, failOnStatusCode: false, timeout: 15_000 });
        if (r.ok()) {
            const j = await r.json();
            const list = Array.isArray(j) ? j : (j?.rooms || j?.items || []);
            out.rooms = list.length;
        } else { out.rooms_status = r.status(); }
    } catch (e) { out.rooms_err = e.message; }
    return out;
}

export default async function globalSetup() {
    fs.mkdirSync(AUTH_DIR, { recursive: true });
    const baseURL = process.env.E2E_BASE_URL;
    const api = await request.newContext({ baseURL, ignoreHTTPSErrors: true, timeout: 60_000 });

    // 1) Stress admin login
    const stressEmail = process.env.E2E_STRESS_ADMIN_EMAIL;
    const stressPass = process.env.E2E_STRESS_ADMIN_PASSWORD;
    const stressToken = await login(api, stressEmail, stressPass);
    if (!stressToken) throw new Error('[stress-setup] stress admin token boş geldi.');
    console.log('[stress-setup] ✅ Stress admin login OK');

    // 2) Pilot super_admin login — ZORUNLU: /api/admin/stress/* require_super_admin'a tabi.
    //    Stress tenant admin super_admin değil → 404 "Not found" döner. Pilot bearer ile çağrılır,
    //    target_tenant_id="<stress_tid>" parametresi izolasyon kapısı sağlar (gates dict).
    if (!process.env.E2E_ADMIN_EMAIL || !process.env.E2E_ADMIN_PASSWORD) {
        throw new Error('[stress-setup] NO-GO: E2E_ADMIN_EMAIL/PASSWORD (pilot super_admin) gerekli — stress admin endpoint require_super_admin.');
    }
    const pilotToken = await login(api, process.env.E2E_ADMIN_EMAIL, process.env.E2E_ADMIN_PASSWORD);
    console.log('[stress-setup] ✅ Pilot super_admin login OK (admin/stress için)');

    // 3) Gate self-check (server gates 403 verirse globalSetup burada NO-GO ile patlar)
    if ((process.env.E2E_ALLOW_DESTRUCTIVE_STRESS || '').toLowerCase() !== 'true') {
        throw new Error('[stress-setup] NO-GO: E2E_ALLOW_DESTRUCTIVE_STRESS != "true" (fail-closed).');
    }
    if ((process.env.E2E_EXTERNAL_DRY_RUN || '').toLowerCase() !== 'true') {
        throw new Error('[stress-setup] NO-GO: E2E_EXTERNAL_DRY_RUN != "true" (fail-closed; harici servisler dry-run olmalı).');
    }
    if (PILOT_TID && STRESS_TID === PILOT_TID) {
        throw new Error('[stress-setup] NO-GO: STRESS_TENANT_ID eşittir PILOT_TENANT_ID — kesinlikle reddedildi.');
    }
    console.log('[stress-setup] ✅ Local gates PASS');

    // 4) Pilot baseline (varsa)
    let pilotBaseline = null;
    if (pilotToken) pilotBaseline = await snapshot(api, pilotToken, 'pilot-baseline');

    // 5) Stress baseline (seed öncesi — ideali tüm sayımlar 0 veya çok küçük)
    const stressBaseline = await snapshot(api, stressToken, 'stress-baseline');

    // 6) Seed 500 rooms
    const dataPrefix = `E2E_STRESS_F7_${Date.now()}_`;
    const seedResp = await api.post('/api/admin/stress/seed', {
        headers: { Authorization: `Bearer ${pilotToken}` },
        data: { target_tenant_id: STRESS_TID, room_count: ROOM_COUNT, data_prefix: dataPrefix },
        failOnStatusCode: false,
        timeout: 120_000,
    });
    if (!seedResp.ok()) {
        const txt = await seedResp.text().catch(() => '');
        throw new Error(`[stress-setup] NO-GO: seed failed (${seedResp.status()}): ${txt.slice(0, 400)}`);
    }
    const seedBody = await seedResp.json();
    if (!Array.isArray(seedBody.external_calls_made) || seedBody.external_calls_made.length !== 0) {
        throw new Error(`[stress-setup] NO-GO: external_calls_made not empty: ${JSON.stringify(seedBody.external_calls_made)}`);
    }
    console.log(`[stress-setup] ✅ Seed OK n=${ROOM_COUNT} prefix=${dataPrefix} timing_ms=${JSON.stringify(seedBody.timing_ms)}`);
    console.log(`[stress-setup]    counts: ${JSON.stringify(seedBody.seeded_counts)}`);

    // 7) Stress snapshot after seed
    const stressAfterSeed = await snapshot(api, stressToken, 'stress-after-seed');

    // 8) Persist
    fs.writeFileSync(TOKEN_FILE, JSON.stringify({
        stress_token: stressToken,
        pilot_token: pilotToken,
        captured_at: Date.now(),
    }, null, 2));
    fs.writeFileSync(STATE_FILE, JSON.stringify({
        base_url: baseURL,
        stress_tid: STRESS_TID,
        pilot_tid: PILOT_TID,
        room_count: ROOM_COUNT,
        data_prefix: dataPrefix,
        seed_response: seedBody,
        pilot_baseline: pilotBaseline,
        stress_baseline: stressBaseline,
        stress_after_seed: stressAfterSeed,
        gates: {
            destructive_flag: true,
            external_dry_run: true,
            stress_tid_isolated: STRESS_TID !== PILOT_TID,
        },
    }, null, 2));
    console.log(`[stress-setup] ✅ State yazıldı: ${STATE_FILE}`);

    await api.dispose();
}

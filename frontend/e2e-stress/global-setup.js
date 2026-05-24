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
    const resp = await api.post('/api/auth/login', { data: { email, password }, failOnStatusCode: false, timeout: 120_000 });
    if (!resp.ok()) {
        const txt = await resp.text().catch(() => '');
        throw new Error(`[stress-setup] login failed (${resp.status()}): ${txt.slice(0, 200)}`);
    }
    const body = await resp.json();
    return body?.access_token || body?.token;
}

// Replit Autoscale (1 Max instance) idle olunca soğuk başlar; CI'dan ilk POST
// 60s timeout'a takılabiliyor (Mongo Atlas + Redis init + bootstrap phases A-G).
// Fresh deploy bootstrap'ı 90-120s'yi bulabiliyor; warm-up gate /api/* yollarına
// 503 dönerken /health her zaman 200 verir, /health/ready ise bootstrap tamamen
// bitince 200 döner (aksi halde 503). 60 deneme × 5s = 5 dakika ceiling.
async function warmup(api) {
    const started = Date.now();
    let lastErr = null;
    // Phase 1: instance/port up check via /health (warm-up gate izin verir)
    for (let attempt = 1; attempt <= 60; attempt++) {
        try {
            const r = await api.get('/health', { failOnStatusCode: false, timeout: 30_000 });
            const ms = Date.now() - started;
            console.log(`[stress-setup] warmup /health attempt=${attempt} status=${r.status()} elapsed=${ms}ms`);
            if (r.status() === 200) break;
        } catch (e) {
            lastErr = e;
            console.log(`[stress-setup] warmup /health attempt=${attempt} err=${e.message}`);
        }
        if (attempt === 60) {
            console.log(`[stress-setup] warmup /health gave up after 60 attempts (lastErr=${lastErr?.message})`);
            return;
        }
        await new Promise((res) => setTimeout(res, 5000));
    }
    // Phase 2: bootstrap-complete check via /health/ready (BOOT_READY flag).
    // CI #48 NO-GO root cause (20260521): Replit Autoscale fresh deploy'da
    // bootstrap phase D (Mongo Atlas conn pool + Redis init + cache_warmer
    // first cycle + index build) 6+ dakikayı bulabildi. Önceki ceiling
    // 60×5s=5min idi → 503 "warming up" boyunca exhausted, login 503 patladı.
    // Budget 120×5s=10min'a çıkarıldı (Mongo Atlas serverless cold-start
    // worst-case + cache warmer + index init için marj).
    for (let attempt = 1; attempt <= 120; attempt++) {
        try {
            const r = await api.get('/health/ready', { failOnStatusCode: false, timeout: 30_000 });
            const ms = Date.now() - started;
            console.log(`[stress-setup] warmup /health/ready attempt=${attempt} status=${r.status()} elapsed=${ms}ms`);
            if (r.status() === 200) break;
        } catch (e) {
            lastErr = e;
            console.log(`[stress-setup] warmup /health/ready attempt=${attempt} err=${e.message}`);
        }
        if (attempt === 120) {
            console.log(`[stress-setup] warmup /health/ready gave up after 120 attempts (lastErr=${lastErr?.message})`);
            return;
        }
        await new Promise((res) => setTimeout(res, 5000));
    }
    // Phase 3: routes mounted check via /api/health (warm-up gate kapısı).
    // BOOT_READY (phase D) ve routes_ready (tüm router'lar mount edildi) ayrı
    // flag'ler — /health/ready 200 dönmesi /api/* path'lerinin 200 döneceği
    // anlamına gelmez. Warm-up gate aktifken /api/health 503 döner; routes
    // mount edilince 200 döner. 30 deneme × 5s = 2.5 dakika ekstra ceiling.
    for (let attempt = 1; attempt <= 30; attempt++) {
        try {
            const r = await api.get('/api/health', { failOnStatusCode: false, timeout: 30_000 });
            const ms = Date.now() - started;
            console.log(`[stress-setup] warmup /api/health attempt=${attempt} status=${r.status()} elapsed=${ms}ms`);
            if (r.status() === 200) return;
        } catch (e) {
            lastErr = e;
            console.log(`[stress-setup] warmup /api/health attempt=${attempt} err=${e.message}`);
        }
        if (attempt < 30) await new Promise((res) => setTimeout(res, 5000));
    }
    console.log(`[stress-setup] warmup /api/health gave up after 30 attempts (lastErr=${lastErr?.message}) — login deneyecek`);
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
    const api = await request.newContext({ baseURL, ignoreHTTPSErrors: true, timeout: 120_000 });

    // 0) Warmup — Replit Autoscale cold-start guard (idle instance ilk POST'ta 60s'yi aşabiliyor)
    await warmup(api);

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
        // F8L v2 (Task #25) — seed_pending_bookings: 2 synthetic pending_assignment
        // bookings for spec 52B's real-succeeded bulk-resolve coverage (1 consumed
        // by test G, 1 spare for re-runs / future expansion).
        data: { target_tenant_id: STRESS_TID, room_count: ROOM_COUNT, data_prefix: dataPrefix, seed_pending_bookings: 2 },
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
    // Backend gates müşterek kontratını da burada hard-assert et (architect feedback):
    // env-only flag'a güvenmek yerine sunucudan dönen 5 gate de true olmalı.
    const backendGates = seedBody.gates || {};
    const requiredGates = ['env_stress_tid_present','target_matches_stress_tid','pilot_tid_not_targeted','destructive_stress_allowed','external_dry_run'];
    const failedGates = requiredGates.filter((g) => backendGates[g] !== true);
    if (failedGates.length) {
        throw new Error(`[stress-setup] NO-GO: backend gates not all-true: failed=${failedGates.join(',')} gates=${JSON.stringify(backendGates)}`);
    }
    console.log(`[stress-setup] ✅ Seed OK n=${ROOM_COUNT} prefix=${dataPrefix} timing_ms=${JSON.stringify(seedBody.timing_ms)}`);
    console.log(`[stress-setup]    counts: ${JSON.stringify(seedBody.seeded_counts)}`);
    if (seedBody.post_insert_verification) {
        console.log(`[stress-setup]    post_insert_verification: ${JSON.stringify(seedBody.post_insert_verification)}`);
    }
    if (seedBody.orphan_cleanup) {
        const totalOrphans = Object.values(seedBody.orphan_cleanup)
            .filter((v) => typeof v === 'number')
            .reduce((a, b) => a + b, 0);
        console.log(`[stress-setup]    orphan_cleanup: total=${totalOrphans} ${JSON.stringify(seedBody.orphan_cleanup)}`);
    }

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

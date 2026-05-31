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

// Task #160 — fail-soft login: rol-spesifik principal'lar için. Hata fırlatmaz,
// başarısızlıkta null döner (downstream spec'ler eksik token'ı honest SKIP eder,
// fake-green YOK). `loginPath` agency-portal gibi alternatif login surface'leri
// için override edilebilir. Hem access_token hem token (agency login `token`
// döndürür) shape'lerini kabul eder.
async function tryLogin(api, email, password, loginPath = '/api/auth/login') {
    try {
        const resp = await api.post(loginPath, { data: { email, password }, failOnStatusCode: false, timeout: 60_000 });
        if (!resp.ok()) return { token: null, status: resp.status() };
        const body = await resp.json().catch(() => ({}));
        return { token: body?.access_token || body?.token || null, status: resp.status() };
    } catch (e) {
        return { token: null, status: 0, error: String(e?.message || e).slice(0, 120) };
    }
}

// Task #160 — rol-spesifik authenticated principal provisioning.
// Doktrin: server-side auth/RBAC ASLA gevşetilmez; principal'lar GERÇEK
// create endpoint'leri üzerinden, STRESS tenant'ında üretilir (pilot mutation
// YOK). Idempotent: sabit sentinel email + sabit parola → re-run'larda mevcut
// kullanıcıyı yeniden kullanır (create 4xx "already exists" ise direkt login).
// Fail-soft: endpoint deploy değil / tier rolü desteklemiyor → null token +
// uyarı log; globalSetup NO-GO'ya DÜŞMEZ (mevcut GREEN baseline korunur).
//
// Üretilen principal'lar:
//   - staff_lowtrust: düşük-güven (non-admin) `front_desk` staff (tüm tier'larda
//     izinli). RBAC-deny / privilege-escalation spec'leri için.
//   - agency_admin: acente-portal `agency_admin` (B2B IDOR / cross-tenant spec).
const ROLE_PASSWORD = process.env.E2E_STRESS_ROLE_PASSWORD || 'Str3ss-R0le!2026#fixed';
const STAFF_LOWTRUST_EMAIL = 'e2e-stress-lowtrust@syroce-stress.local';
const AGENCY_NAME = 'E2E Stress Harness Agency';
const AGENCY_ADMIN_EMAIL = 'e2e-stress-agency-admin@syroce-stress.local';

async function provisionLowTrustStaff(api, stressAdminToken) {
    const out = { role: 'front_desk', email: STAFF_LOWTRUST_EMAIL, token: null, created: false };
    const createResp = await api.post('/api/hotel/team', {
        headers: { Authorization: `Bearer ${stressAdminToken}` },
        data: { email: STAFF_LOWTRUST_EMAIL, name: 'E2E Stress LowTrust', role: 'front_desk', password: ROLE_PASSWORD },
        failOnStatusCode: false, timeout: 60_000,
    }).catch(() => null);
    const createStatus = createResp?.status?.() ?? 0;
    // 2xx = yeni oluşturuldu; 400 "already registered" = mevcut → login dene.
    out.created = createStatus >= 200 && createStatus < 300;
    out.create_status = createStatus;
    const { token, status } = await tryLogin(api, STAFF_LOWTRUST_EMAIL, ROLE_PASSWORD);
    out.token = token;
    out.login_status = status;
    return out;
}

// Task #166 — Spa add-on entitlement provisioning for the stress tenant.
// Spec 98 (spa-wellness-operational) hits /api/spa/* which is entitlement-gated
// by the `spa` add-on module (default OFF; core/entitlement.py ROUTE_MODULE_MAP).
// A stress-tenant ADMIN principal is NOT a global super_admin, so the entitlement
// middleware returns 403 ENTITLEMENT_DENIED on GET /api/spa/{services,therapists,
// rooms} → the spec's catalog_probe flags moduleBlocked → A/B/C/D/E all SKIP
// (green baseline, zero real spa coverage).
//
// Fix: actively grant the `spa` module to the stress tenant via the super-admin
// module-management endpoint (PATCH /api/admin/tenants/{tid}/modules). This is a
// REAL entitlement grant on a throwaway test tenant — NOT an RBAC/auth weakening:
// the spa routers still enforce require_catalog / require_spa_ops / require_finance
// + require_op("manage_sales") server-side, and the stress ADMIN role legitimately
// satisfies them. The current module map is read first and merged so no other
// add-on (e.g. `mice`) is clobbered. PATCH replaces the whole `modules` dict, so
// merge-then-write is mandatory. Pilot guard: refuse to touch the pilot tenant.
async function ensureSpaEntitlement(api, pilotToken, stressTid, stressToken) {
    const out = { module: 'spa', already_on: false, patched: false, probe_status: null };
    if (!stressTid) { out.skipped = 'no_stress_tid'; return out; }
    if (PILOT_TID && stressTid === PILOT_TID) {
        throw new Error('[stress-setup] NO-GO: refusing to enable spa add-on — STRESS_TENANT_ID equals PILOT_TENANT_ID.');
    }

    // 1) Read current modules for the stress tenant (super-admin only endpoint).
    let currentModules = {};
    const listResp = await api.get('/api/admin/tenants?limit=2000', {
        headers: { Authorization: `Bearer ${pilotToken}` },
        failOnStatusCode: false, timeout: 30_000,
    }).catch(() => null);
    if (listResp && listResp.ok()) {
        const body = await listResp.json().catch(() => null);
        const tenants = Array.isArray(body) ? body : (body?.tenants || []);
        const match = tenants.find((t) => t?.id === stressTid);
        if (match && match.modules && typeof match.modules === 'object') {
            currentModules = match.modules;
        }
        out.found_tenant = !!match;
    } else {
        out.list_status = listResp?.status?.() ?? 0;
    }

    out.already_on = currentModules.spa === true;

    // 2) Grant `spa` (merge — PATCH overwrites the entire modules map).
    if (!out.already_on) {
        const merged = { ...currentModules, spa: true };
        const patchResp = await api.patch(`/api/admin/tenants/${stressTid}/modules`, {
            headers: { Authorization: `Bearer ${pilotToken}` },
            data: { modules: merged },
            failOnStatusCode: false, timeout: 30_000,
        }).catch(() => null);
        out.patch_status = patchResp?.status?.() ?? 0;
        out.patched = out.patch_status >= 200 && out.patch_status < 300;
        if (!out.patched) {
            throw new Error(
                `[stress-setup] NO-GO: failed to enable \`spa\` add-on for stress tenant ` +
                `(PATCH /api/admin/tenants/${stressTid}/modules → ${out.patch_status}). ` +
                `Spec 98 would silently SKIP. ` +
                `Manual fix: cd backend && STRESS_ENABLE_MODULES=spa python -m scripts.enable_mice_for_stress`,
            );
        }
    }

    // 3) Probe the gated surface with the STRESS principal — fail-fast if it
    //    still 403s so a silent SKIP can never masquerade as a real PASS.
    const probe = await api.get('/api/spa/services', {
        headers: { Authorization: `Bearer ${stressToken}` },
        failOnStatusCode: false, timeout: 30_000,
    }).catch(() => null);
    out.probe_status = probe?.status?.() ?? 0;
    if (out.probe_status === 403) {
        const txt = probe ? await probe.text().catch(() => '') : '';
        throw new Error(
            `[stress-setup] NO-GO: stress tenant STILL entitlement-blocked on /api/spa/services ` +
            `after enabling \`spa\` (HTTP 403). body=${txt.slice(0, 200)}. ` +
            `Manual fix: cd backend && STRESS_ENABLE_MODULES=spa python -m scripts.enable_mice_for_stress`,
        );
    }
    return out;
}

async function provisionAgencyAdmin(api, stressAdminToken) {
    const out = { role: 'agency_admin', email: AGENCY_ADMIN_EMAIL, token: null, agency_id: null, created: false };
    // 1) Idempotent agency: önce ara, yoksa oluştur (POST /agencies her zaman
    //    insert ettiği için kör create cross-round bloat üretir).
    let agencyId = null;
    const listResp = await api.get(`/api/agencies?q=${encodeURIComponent(AGENCY_NAME)}&page_size=50`, {
        headers: { Authorization: `Bearer ${stressAdminToken}` },
        failOnStatusCode: false, timeout: 30_000,
    }).catch(() => null);
    if (listResp && listResp.ok()) {
        const body = await listResp.json().catch(() => null);
        const items = Array.isArray(body) ? body : (body?.items || []);
        const match = items.find((a) => a?.name === AGENCY_NAME);
        if (match?.id) agencyId = match.id;
    }
    if (!agencyId) {
        const createAgencyResp = await api.post('/api/agencies', {
            headers: { Authorization: `Bearer ${stressAdminToken}` },
            data: { name: AGENCY_NAME, contact_name: 'E2E Stress', contact_email: 'e2e-stress-agency@syroce-stress.local' },
            failOnStatusCode: false, timeout: 30_000,
        }).catch(() => null);
        if (createAgencyResp && createAgencyResp.ok()) {
            const body = await createAgencyResp.json().catch(() => null);
            agencyId = body?.id || null;
        }
        out.agency_create_status = createAgencyResp?.status?.() ?? 0;
    }
    out.agency_id = agencyId;
    if (!agencyId) return out; // agency yoksa user da yok — fail-soft.

    // 2) Idempotent agency user: create 409 "zaten kayitli" → login dene.
    const createUserResp = await api.post(`/api/agencies/${agencyId}/users`, {
        headers: { Authorization: `Bearer ${stressAdminToken}` },
        data: { name: 'E2E Stress Agency Admin', email: AGENCY_ADMIN_EMAIL, password: ROLE_PASSWORD, role: 'agency_admin' },
        failOnStatusCode: false, timeout: 30_000,
    }).catch(() => null);
    const createStatus = createUserResp?.status?.() ?? 0;
    out.created = createStatus >= 200 && createStatus < 300;
    out.create_status = createStatus;

    // 3) Agency-portal login surface (NOT /api/auth/login).
    const { token, status } = await tryLogin(api, AGENCY_ADMIN_EMAIL, ROLE_PASSWORD, '/api/agency-portal/auth/login');
    out.token = token;
    out.login_status = status;
    return out;
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
    // Task #178 — aged-booking (check_in > 24h ago) + deposit-payment coverage
    // report. 24h-dependent specs (full-24h sim, night-audit aging, harvest-
    // window depletion) rely on older-than-threshold data existing in the seed.
    // Fail-soft warn (not NO-GO): a count of 0 against a non-trivial booking set
    // means the backend ran a pre-aged seed; surface it loudly so a silent
    // all-today dataset can't masquerade as 24h-flow coverage.
    {
        const aged = seedBody.seeded_counts?.aged_bookings;
        const payments = seedBody.seeded_counts?.payments;
        const baseBookings = seedBody.seeded_counts?.bookings;
        console.log(`[stress-setup]    aged_bookings=${aged ?? 'n/a'} payments=${payments ?? 'n/a'} (check_in > 24h ago + deposit coverage)`);
        if (typeof aged === 'number' && aged === 0 && typeof baseBookings === 'number' && baseBookings >= 30) {
            console.warn(`[stress-setup] ⚠️ aged_bookings=0 with bookings=${baseBookings} — 24h-dependent specs (99 full-24h sim / 06 night-audit / harvest) will lack older-than-24h data. Verify backend seed aging (Task #178).`);
        }
    }
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

    // 7a) Stress add-on entitlement assertion — Task #58.
    // Specs 14 / 15 / 18 / 98 all touch `/api/mice/*` which is gated by the
    // `mice` add-on module (default OFF). When the stress tenant is missing
    // the add-on every BEO/MICE spec falls into the "module-blocked SKIP"
    // branch — green baseline, zero real coverage. Fail fast here instead
    // of swallowing four specs' worth of SKIPs further down the run.
    // Remediation when this trips: `cd backend && python -m scripts.enable_mice_for_stress`.
    {
        const probe = await api.get('/api/mice/events?limit=1', {
            headers: { Authorization: `Bearer ${stressToken}` },
            failOnStatusCode: false,
            timeout: 30_000,
        });
        if (probe.status() === 403) {
            const txt = await probe.text().catch(() => '');
            let code = '';
            try { code = JSON.parse(txt)?.detail?.error_code || JSON.parse(txt)?.error_code || ''; } catch { /* noop */ }
            if (code === 'ENTITLEMENT_DENIED' || /mice/i.test(txt)) {
                throw new Error(
                    `[stress-setup] NO-GO: stress tenant is missing the \`mice\` add-on module ` +
                    `(GET /api/mice/events → 403 ENTITLEMENT_DENIED). ` +
                    `Specs 14/15/18/98 would silently SKIP. ` +
                    `Fix: cd backend && python -m scripts.enable_mice_for_stress`,
                );
            }
        }
        console.log(`[stress-setup] ✅ mice add-on entitlement probe status=${probe.status()}`);
    }

    // 7a-bis) Spa add-on entitlement provisioning — Task #166.
    // Self-heal the `spa` add-on so spec 98 (spa-wellness-operational) runs with
    // real data instead of catalog_probe SKIP. Real entitlement grant on the
    // throwaway stress tenant (NOT an RBAC weakening); fail-fast if still blocked.
    let spaEntitlement = null;
    try {
        spaEntitlement = await ensureSpaEntitlement(api, pilotToken, STRESS_TID, stressToken);
        console.log(`[stress-setup] ✅ spa add-on entitlement ready: ${JSON.stringify(spaEntitlement)}`);
    } catch (e) {
        // Hard NO-GO — mirrors the mice gate: a missing/blocked spa add-on must
        // surface loudly, never degrade spec 98 into a silent green SKIP.
        throw e;
    }

    // 7b) Pilot read-only fixtures — Task #13 (F8M v2 § 41B B2B IDOR matrix)
    // + Task #67 (F9C § 98 sales-lifecycle step J). Idempotently ensures the
    // pilot tenant carries one `room_blocks` doc, one `kbs_reports` doc and
    // one sales lead (company_name `IDOR_PROBE_SEED`, `pilot_fixture=true`)
    // so the cross-tenant IDOR rows for `groups`, `kbs`, and `sales/leads`
    // exercise real pilot ids (not BOGUS_UUID). Fail-soft: endpoint not
    // deployed yet → specs fall back to existing sampling probes +
    // sample-gap REVIEW (current behaviour preserved).
    let pilotFixtures = null;
    if (PILOT_TID) {
        const pf = await api.post('/api/admin/pilot-fixtures/ensure', {
            headers: { Authorization: `Bearer ${pilotToken}` },
            data: { pilot_tenant_id: PILOT_TID },
            failOnStatusCode: false,
            timeout: 30_000,
        });
        if (pf.ok()) {
            pilotFixtures = await pf.json().catch(() => null);
            console.log(`[stress-setup] ✅ Pilot fixtures ensured: block=${pilotFixtures?.block_id?.slice(0,8)} kbs_report=${pilotFixtures?.kbs_report_id?.slice(0,8)} sales_lead=${pilotFixtures?.sales_lead_id?.slice(0,8)} created=${JSON.stringify(pilotFixtures?.created)}`);
        } else {
            const txt = await pf.text().catch(() => '');
            console.log(`[stress-setup] ⚠️ Pilot fixtures ensure non-2xx (${pf.status()}) — matrix spec will fall back to sampling. body=${txt.slice(0, 200)}`);
        }
    }

    // 7c) Rol-spesifik authenticated principal provisioning — Task #160.
    // GERÇEK create endpoint'leri üzerinden stress tenant'ında düşük-güven
    // staff + agency_admin principal üret. Fail-soft: başarısızlık globalSetup'ı
    // NO-GO'ya düşürmez, token=null kalır (downstream spec honest SKIP eder).
    let roleProvisioning = { staff_lowtrust: null, agency_admin: null };
    try {
        const staff = await provisionLowTrustStaff(api, stressToken);
        const agency = await provisionAgencyAdmin(api, stressToken);
        roleProvisioning = { staff_lowtrust: staff, agency_admin: agency };
        if (staff.token) console.log(`[stress-setup] ✅ low-trust staff principal hazır (role=front_desk created=${staff.created} login=${staff.login_status})`);
        else console.log(`[stress-setup] ⚠️ low-trust staff principal token alınamadı (create=${staff.create_status} login=${staff.login_status}) — RBAC spec'leri SKIP edebilir.`);
        if (agency.token) console.log(`[stress-setup] ✅ agency_admin principal hazır (agency_id=${String(agency.agency_id).slice(0, 8)} created=${agency.created} login=${agency.login_status})`);
        else console.log(`[stress-setup] ⚠️ agency_admin principal token alınamadı (agency_id=${agency.agency_id} create=${agency.create_status} login=${agency.login_status}) — B2B/cross-tenant spec'leri SKIP edebilir.`);
    } catch (e) {
        console.log(`[stress-setup] ⚠️ rol provisioning hatası (fail-soft): ${String(e?.message || e).slice(0, 160)}`);
    }

    // 7d) Seed yeterlilik doğrulaması — Task #160. Seed gerçek backend endpoint
    // üzerinden booking/folio/charge/payment/rooms/staff üretti; eşikleri
    // burada gözle (staff pool >= 5, rooms ve booking present). Fail-soft:
    // eşik karşılanmazsa uyarı log (NO-GO değil), seeded_counts state'e yazılır.
    const seededCounts = seedBody?.seeded_counts || {};
    const staffSeeded = seededCounts.staff_members ?? seededCounts.staff ?? 0;
    const seedSummary = {
        rooms: seededCounts.rooms ?? seededCounts.total_rooms ?? stressAfterSeed?.rooms ?? 0,
        bookings: seededCounts.bookings ?? stressAfterSeed?.bookings ?? 0,
        folios: seededCounts.folios ?? 0,
        charges: seededCounts.folio_charges ?? seededCounts.charges ?? 0,
        payments: seededCounts.payments ?? 0,
        staff: staffSeeded,
        staff_pool_ok: staffSeeded >= 5,
    };
    console.log(`[stress-setup] seed_summary: ${JSON.stringify(seedSummary)}`);
    if (!seedSummary.staff_pool_ok) {
        console.log(`[stress-setup] ⚠️ staff pool < 5 (=${staffSeeded}) — HR/shift/RBAC spec'leri yetersiz veri görebilir.`);
    }

    // 8) Persist
    fs.writeFileSync(TOKEN_FILE, JSON.stringify({
        stress_token: stressToken,
        pilot_token: pilotToken,
        // Task #160 — rol-spesifik principal token'ları. null olabilir
        // (fail-soft); downstream spec'ler null'ı honest SKIP eder.
        role_tokens: {
            super_admin: pilotToken,          // pilot super_admin (admin/stress + cross-tenant baseline)
            stress_admin: stressToken,        // stress tenant admin (mutasyonların çoğu bununla)
            staff_lowtrust: roleProvisioning.staff_lowtrust?.token || null,
            agency_admin: roleProvisioning.agency_admin?.token || null,
        },
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
        pilot_fixtures: pilotFixtures,
        spa_entitlement: spaEntitlement,
        gates: {
            destructive_flag: true,
            external_dry_run: true,
            stress_tid_isolated: STRESS_TID !== PILOT_TID,
        },
    }, null, 2));
    console.log(`[stress-setup] ✅ State yazıldı: ${STATE_FILE}`);

    await api.dispose();
}

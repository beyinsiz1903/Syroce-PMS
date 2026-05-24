// F8M v2 § 41B — B2B Sub-Router Tenant Isolation Matrix.
//
// Threat-model surface (threat_model.md § Spoofing + Information Disclosure +
// Elevation of Privilege): backend/routers/b2b_api/ altında X-API-Key ile
// kimlik doğrulayan 11 alt-router bulunur. v1 spec (41-b2b-api-key-scope)
// API key LIFECYCLE'ını (create/info/revoke + missing/garbage key smoke +
// /folio cross-tenant probe) test eder. Bu spec her alt-router için ayrı
// satır olarak tenant isolation invariantlarını matrix-style doğrular:
//
//   (1) Stress-key collection GET → response body pilot_tid içermez.
//   (2) Stress-key + pilot-resource-id (booking/guest/block/report) →
//       id-bearing GET 4xx döner (2xx + pilot içerik → P0 IDOR).
//   (3) Missing/bogus X-API-Key → 401/403 (2xx → P0 auth bypass).
//   (4) Scope enforcement → şu an key sistemi per-subrouter scope
//       provision etmiyor (agency-scoped tek key tüm endpoint'lere
//       erişiyor). Bu yüzden P2 REVIEW informational rec; scope
//       eklenirse v3 burada P1 hard assert eder.
//
// Mutlak kurallar (her test'te try/finally veya invariant testinde):
//   - pilot mutation = 0 (assertPilotDriftZero)
//   - external_calls delta = 0 (assertNoExternalCallsPostBatch)
//   - response'larda token leak yok (assertNoTokenLeak)
//   - guests/identity/kbs/guest_journey/lost_found collection'larında PII
//     masked (assertPiiMasked) — telefon/email/TC/passport
//   - cleanup idempotent (afterAll DELETE 2xx veya 404 kabul)
//
// Read-only / validation-only: hiçbir POST/PUT/DELETE yapılmaz (key
// create/delete dışında). Real provider tetiklemesi YOK.
//
// Module-blocked pattern (v1 ile aynı doctrine):
//   - Agencies list 4xx, stress tenant agency yok, key create 4xx veya
//     2xx ama raw key yok → A/B/C/D skipped, E invariant testi bağımsız
//     çalışır.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'b2b_api';

// X-API-Key bearer wrapper — v1 spec'teki callApiKey ile aynı imza, v3'te
// stress-helpers.js'e taşınabilir (low blast-radius). Şimdilik local copy
// (v1 + v2 paralel evolve etsin diye duplicate kabul).
// TODO(F8M v3): callApiKey'ı fixtures/stress-helpers.js'e lift et;
// v1 + v2 + ileride v3 import etsin.
async function callApiKey(request, method, urlPath, body, apiKey, opts = {}) {
    const headers = { 'Content-Type': 'application/json' };
    if (apiKey !== undefined && apiKey !== null) headers['X-API-Key'] = apiKey;
    const t0 = Date.now();
    const r = await request[method](urlPath, {
        headers, data: body, failOnStatusCode: false, timeout: opts.timeout ?? 30_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    const ms = Date.now() - t0;
    let bodyJson = null;
    try { bodyJson = r.json ? await r.json() : null; } catch { /* ignore */ }
    const status = r.status?.() ?? 0;
    return { status, ms, body: bodyJson, ok: status >= 200 && status < 300 };
}

// 11 X-API-Key sub-router matrix. `collection` = id-siz read endpoint (varsa);
// `idBearing` = id-bearing GET template ({booking}/{guest}/{block}/{kbs}
// placeholder ile); `idKind` = pilot id sample kaynağı; `piiFields` = collection
// PII guard listesi (null = skip).
//
// __init__.py mount sırası (referans):
//   booking_engine, folio, groups, guest_journey, guests, housekeeping,
//   identity, kbs, lost_found, services, wake_up, webhooks, api_keys.
// webhooks + api_keys JWT-admin → kapsam dışı.
const SUBROUTERS = [
    { name: 'booking_engine', collection: '/api/b2b/hotel-info',
      idBearing: '/api/b2b/reservations/{booking_id}', idKind: 'booking', piiFields: null },
    { name: 'folio', collection: null,
      idBearing: '/api/b2b/folio/{booking_id}', idKind: 'booking', piiFields: null },
    { name: 'groups', collection: '/api/b2b/groups',
      idBearing: '/api/b2b/groups/{block_id}', idKind: 'block', piiFields: null },
    { name: 'guest_journey', collection: '/api/b2b/guest-journey/requests',
      idBearing: '/api/b2b/guest-journey/pre-arrival/{booking_id}', idKind: 'booking',
      piiFields: ['phone', 'email'] },
    { name: 'guests', collection: '/api/b2b/guests/search?q=zz&limit=5',
      idBearing: '/api/b2b/guests/{guest_id}', idKind: 'guest',
      piiFields: ['phone', 'email', 'identity_number', 'passport_no'] },
    { name: 'housekeeping', collection: '/api/b2b/housekeeping/rooms',
      idBearing: null, piiFields: null },
    { name: 'identity', collection: null,
      idBearing: '/api/b2b/identity/guest/{guest_id}', idKind: 'guest',
      piiFields: ['phone', 'email', 'identity_number', 'passport_no'] },
    { name: 'kbs', collection: '/api/b2b/kbs/guests',
      idBearing: '/api/b2b/kbs/report/{kbs_report_id}', idKind: 'kbs_report',
      piiFields: ['phone', 'email', 'identity_number', 'passport_no'] },
    { name: 'lost_found', collection: '/api/b2b/lost-found',
      idBearing: null, piiFields: ['phone', 'email'] },
    { name: 'services', collection: '/api/b2b/concierge/services',
      idBearing: null, piiFields: null },
    { name: 'wake_up', collection: '/api/b2b/wake-up-calls',
      idBearing: null, piiFields: null },
];

const BOGUS_UUID = '00000000-0000-0000-0000-000000000000';

function renderTemplate(tpl, ids) {
    return tpl
        .replace('{booking_id}', ids.booking || BOGUS_UUID)
        .replace('{guest_id}', ids.guest || BOGUS_UUID)
        .replace('{block_id}', ids.block || BOGUS_UUID)
        .replace('{kbs_report_id}', ids.kbs_report || BOGUS_UUID);
}

test.describe.configure({ mode: 'serial' });

test.describe('F8M v2 § 41B — B2B Sub-Router Matrix', () => {
    let pilotBefore = null;
    let prefix = null;
    let stressTid = null;
    let pilotTid = null;
    let stressAgencyId = null;
    let createdRawKey = null;
    let createdKeyAgencyId = null;
    let moduleBlocked = false;
    let blockedReason = null;
    // Pilot resource id sampleları — IDOR matrix'i için.
    const pilotIds = { booking: null, guest: null, block: null, kbs_report: null };

    test('Setup: pilot baseline + stress agency + create key + pilot id sampling', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Stress tenant agency probe (key create için zorunlu).
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/agencies');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `agencies_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Agencies endpoint probe non-2xx (v2 matrix)',
                `status=${probe.status} reason=${probe.reason} — matrix tests skipped, invariants still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup_v2', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        const agencies = Array.isArray(probe.body) ? probe.body
            : (probe.body?.agencies || probe.body?.items || probe.body?.data || []);
        const stressAgency = agencies.find(a => a.tenant_id === stressTid);
        if (!stressAgency) {
            moduleBlocked = true;
            blockedReason = `no_stress_agency_in_list (len=${agencies.length})`;
            recFinding(testInfo, 'P2', MOD, 'Stress tenant agency yok (v2 matrix)',
                `agencies_list_len=${agencies.length} — matrix tests skipped.`);
            rec(testInfo, { module: MOD, step: 'setup_v2', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        stressAgencyId = stressAgency.id || stressAgency._id;

        // Idempotent pre-cleanup — önceki round residue varsa revoke.
        await callTimed(request, 'delete', `/api/b2b/api-keys/${stressAgencyId}`,
            undefined, stressTokens.stress_token);

        const create = await callTimed(request, 'post',
            `/api/b2b/api-keys?agency_id=${stressAgencyId}`,
            {}, stressTokens.stress_token);
        if (!create.ok) {
            moduleBlocked = true;
            blockedReason = `key_create_non2xx_status_${create.status}`;
            recFinding(testInfo, 'P2', MOD, 'B2B API key oluşturulamadı (v2 matrix)',
                `status=${create.status} body=${JSON.stringify(create.body).slice(0, 160)} — RBAC veya deploy eksik. Matrix tests skipped.`);
            rec(testInfo, { module: MOD, step: 'setup_v2', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        if (!create.body?.api_key) {
            moduleBlocked = true;
            blockedReason = `key_create_2xx_no_api_key`;
            recFinding(testInfo, 'P0', MOD,
                'B2B API key create 2xx döndü AMA raw api_key body\'de yok (v2 matrix)',
                `status=${create.status} body=${JSON.stringify(create.body).slice(0, 160)} — POST /api/b2b/api-keys contract'ı raw key DÖNDÜRMELİ. Matrix tests skipped.`);
            rec(testInfo, { module: MOD, step: 'setup_v2', status: 'FAIL',
                note: `module_blocked=true reason=${blockedReason} severity=P0` });
            return;
        }
        createdRawKey = create.body.api_key;
        createdKeyAgencyId = stressAgencyId;

        // Pilot resource id sampling — pilot_token ile read-only. IDOR matrix'i
        // için her id kind için en az bir gerçek pilot id şart. Sample edilemezse
        // o satır BOGUS_UUID fallback'iyle koşar (existence-vs-IDOR ayrımı
        // kaybolur, ama 2xx + pilot içerik hala P0 emit eder).
        try {
            const b = await callTimed(request, 'get', '/api/pms/bookings?limit=1',
                undefined, stressTokens.pilot_token);
            if (b.ok) {
                const list = Array.isArray(b.body) ? b.body
                    : (b.body?.bookings || b.body?.items || []);
                if (list[0]) {
                    pilotIds.booking = list[0].id || list[0]._id;
                    if (!pilotIds.guest && list[0].guest_id) pilotIds.guest = list[0].guest_id;
                }
            }
        } catch (_) {}
        if (!pilotIds.guest) {
            try {
                const g = await callTimed(request, 'get', '/api/guests?limit=1',
                    undefined, stressTokens.pilot_token);
                if (g.ok) {
                    const list = Array.isArray(g.body) ? g.body
                        : (g.body?.guests || g.body?.items || []);
                    if (list[0]) pilotIds.guest = list[0].id || list[0]._id;
                }
            } catch (_) {}
        }
        // Block + KBS report id: pilot read endpoint'leri çoğu deploy'da
        // farklı path altında (group-blocks, kbs/reports). Best-effort dene;
        // yoksa BOGUS_UUID fallback (sample-gap REVIEW emit edilir).
        try {
            const gb = await callTimed(request, 'get', '/api/group-blocks?limit=1',
                undefined, stressTokens.pilot_token);
            if (gb.ok) {
                const list = Array.isArray(gb.body) ? gb.body
                    : (gb.body?.blocks || gb.body?.items || gb.body?.groups || []);
                if (list[0]) pilotIds.block = list[0].id || list[0]._id;
            }
        } catch (_) {}
        try {
            const kr = await callTimed(request, 'get', '/api/kbs/reports?limit=1',
                undefined, stressTokens.pilot_token);
            if (kr.ok) {
                const list = Array.isArray(kr.body) ? kr.body
                    : (kr.body?.reports || kr.body?.items || []);
                if (list[0]) pilotIds.kbs_report = list[0].id || list[0]._id;
            }
        } catch (_) {}

        const sampled = Object.entries(pilotIds)
            .map(([k, v]) => `${k}=${v ? v.slice(0, 8) : 'MISSING'}`).join(' ');
        rec(testInfo, { module: MOD, step: 'setup_v2', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} stress_agency=${stressAgencyId?.slice(0, 8)} key_created=true key_prefix=${create.body.key_prefix} pilot_ids[${sampled}]` });
    });

    test('A) Collection GET matrix — no pilot_tid leak in stress-key responses', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'collection_no_tid_leak', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const results = [];
        const leaks = [];
        const piiViolations = [];
        for (const sub of SUBROUTERS) {
            if (!sub.collection) {
                results.push({ sub: sub.name, status: 'N/A', note: 'no_collection_endpoint' });
                continue;
            }
            const r = await callApiKey(request, 'get', sub.collection, undefined, createdRawKey);
            const blob = r.body ? JSON.stringify(r.body) : '';
            const hasPilotTid = pilotTid && blob.includes(pilotTid);
            results.push({ sub: sub.name, ep: sub.collection, http: r.status,
                body_size: blob.length, leak: hasPilotTid });
            if (hasPilotTid) {
                leaks.push({ sub: sub.name, ep: sub.collection, http: r.status });
                recFinding(testInfo, 'P0', MOD,
                    `Cross-tenant data leak — ${sub.name} collection response pilot_tid içeriyor`,
                    `endpoint=${sub.collection} stress_key + pilot_tid=${pilotTid} found in body. Tenant filter eksik.`);
            }
            // Token leak guard her response için.
            if (r.body) assertNoTokenLeak(testInfo, MOD, r.body, `b2b_v2_collection_${sub.name}`);
            // PII guard sadece tanımlı satırlarda + 2xx + non-empty body.
            if (r.ok && sub.piiFields && r.body) {
                const piiPass = assertPiiMasked(testInfo, MOD, r.body, sub.piiFields);
                if (!piiPass) piiViolations.push(sub.name);
            }
        }
        rec(testInfo, { module: MOD, step: 'collection_no_tid_leak',
            status: leaks.length === 0 ? 'PASS' : 'FAIL',
            note: `tested=${results.filter(r => r.http != null).length} leaks=${leaks.length} pii_violations=${piiViolations.length} results=${JSON.stringify(results).slice(0, 600)}` });
        expect(leaks.length).toBe(0);
    });

    test('B) ID-bearing GET matrix — P0 cross-tenant IDOR (stress key + pilot resource id → 4xx)', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'idor_matrix', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const results = [];
        const breaches = [];
        const sampleGaps = [];
        for (const sub of SUBROUTERS) {
            if (!sub.idBearing) {
                results.push({ sub: sub.name, status: 'N/A', note: 'no_id_bearing_get' });
                continue;
            }
            const pilotId = pilotIds[sub.idKind];
            if (!pilotId) {
                // Sample gap — BOGUS_UUID ile devam ederiz; 4xx beklenir (pure
                // existence-deny), ama gerçek IDOR coverage düşer → REVIEW emit.
                sampleGaps.push({ sub: sub.name, kind: sub.idKind });
            }
            const ep = renderTemplate(sub.idBearing, pilotIds);
            const r = await callApiKey(request, 'get', ep, undefined, createdRawKey);
            const blob = r.body ? JSON.stringify(r.body) : '';
            // Threat: stress key + pilot id → 2xx + (anlamlı body VEYA pilot_tid
            // substring) ⇒ P0 IDOR. 4xx (401/403/404) PASS. 0 / 5xx → REVIEW.
            let row = { sub: sub.name, ep, http: r.status, body_size: blob.length };
            const pilotTidLeak = pilotTid && blob.includes(pilotTid);
            if (r.status >= 200 && r.status < 300) {
                // 2xx — gövde anlamlı mı? boş objeyse contract zayıflığı (P1),
                // dolu + pilot içerik varsa P0 disclosure.
                if (pilotTidLeak || blob.length > 50) {
                    breaches.push({ ...row, kind: 'P0_disclosure', pilot_tid_leak: pilotTidLeak });
                    recFinding(testInfo, 'P0', MOD,
                        `Cross-tenant IDOR — ${sub.name} stress key + pilot ${sub.idKind} id → 2xx`,
                        `endpoint=${ep} status=${r.status} body_size=${blob.length} pilot_tid_leak=${pilotTidLeak}. ` +
                        `_agency_owns_${sub.idKind}() guard eksik veya tenant filter atlanmış. Threat-model § Information Disclosure + Elevation of Privilege.`);
                } else {
                    breaches.push({ ...row, kind: 'P1_contract_2xx_empty' });
                    recFinding(testInfo, 'P1', MOD,
                        `${sub.name} stress key + pilot ${sub.idKind} id → 2xx ama gövde boş`,
                        `endpoint=${ep} status=${r.status} body=${blob.slice(0, 120)}. Beklenen 4xx; 2xx empty contract bulanık.`);
                }
            } else if (r.status === 401 || r.status === 403 || r.status === 404) {
                row.verdict = 'PASS';
            } else if (r.status === 0 || r.status >= 500) {
                row.verdict = 'REVIEW';
                recFinding(testInfo, 'P2', MOD,
                    `${sub.name} IDOR probe transient — status=${r.status}`,
                    `endpoint=${ep} body=${blob.slice(0, 120)}. Backend 5xx/network; sonraki round'da re-verify.`);
            } else {
                // 4xx başka — örn. 400 validation. PASS (deny path).
                row.verdict = 'PASS_other_4xx';
            }
            // Token leak + PII guard 2xx body için.
            if (r.body) assertNoTokenLeak(testInfo, MOD, r.body, `b2b_v2_idor_${sub.name}`);
            if (r.ok && sub.piiFields && r.body) {
                assertPiiMasked(testInfo, MOD, r.body, sub.piiFields);
            }
            results.push(row);
        }
        if (sampleGaps.length > 0) {
            recFinding(testInfo, 'P2', MOD,
                'IDOR matrix sample-gap — bazı pilot id\'leri toplanamadı',
                `gaps=${JSON.stringify(sampleGaps)}. Bu satırlar BOGUS_UUID ile koştu; cross-tenant disclosure delta gözlenemez (yalnız existence-deny). Sonraki round için pilot seed dataset genişlet.`);
        }
        rec(testInfo, { module: MOD, step: 'idor_matrix',
            status: breaches.length === 0 ? 'PASS' : 'FAIL',
            note: `tested=${results.length} breaches=${breaches.length} sample_gaps=${sampleGaps.length} details=${JSON.stringify(results).slice(0, 800)}` });
        expect(breaches.length).toBe(0);
    });

    test('C) Auth matrix — missing/bogus X-API-Key → 401/403 (P0 if 2xx)', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'auth_matrix', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const ALLOWED_DENY = new Set([401, 403]);
        const results = [];
        const bypasses = [];
        const weakDeny = [];
        for (const sub of SUBROUTERS) {
            // Auth probe için her satırda collection varsa onu, yoksa
            // id-bearing'i BOGUS_UUID ile dene (auth check route handler'dan
            // önce çalışır — id'nin gerçek olması gerekmez).
            const probeEp = sub.collection || (sub.idBearing
                ? renderTemplate(sub.idBearing, {}) : null);
            if (!probeEp) {
                results.push({ sub: sub.name, status: 'N/A', note: 'no_get_endpoint' });
                continue;
            }
            // (a) missing key — undefined → header set edilmez.
            const m = await callApiKey(request, 'get', probeEp, undefined, undefined);
            // (b) bogus key — sözdizimsel olarak benzeri ama geçersiz.
            const b = await callApiKey(request, 'get', probeEp, undefined,
                'syx_FAKE_INVALID_KEY_0000000000000000000000');
            const row = { sub: sub.name, ep: probeEp,
                missing_http: m.status, bogus_http: b.status };
            for (const [tag, r] of [['missing', m], ['bogus', b]]) {
                if (r.status >= 200 && r.status < 300) {
                    bypasses.push({ sub: sub.name, kind: tag, ep: probeEp, status: r.status });
                    recFinding(testInfo, 'P0', MOD,
                        `B2B auth bypass — ${sub.name} ${tag} X-API-Key → 2xx`,
                        `endpoint=${probeEp} ${tag}_key status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)}. ` +
                        `get_b2b_agency() dependency atlanmış veya unauthenticated path mounted. Threat-model § Spoofing + Elevation of Privilege.`);
                } else if (!ALLOWED_DENY.has(r.status) && r.status !== 404) {
                    weakDeny.push({ sub: sub.name, kind: tag, status: r.status });
                }
            }
            results.push(row);
        }
        if (weakDeny.length > 0) {
            recFinding(testInfo, 'P1', MOD,
                'B2B auth deny path zayıf — 401/403/404 dışı status',
                `Endpoints: ${JSON.stringify(weakDeny)}. Tutarlı 401 beklenir; 400/5xx leak vektörüdür.`);
        }
        rec(testInfo, { module: MOD, step: 'auth_matrix',
            status: bypasses.length === 0 ? 'PASS' : 'FAIL',
            note: `tested=${results.length} bypasses=${bypasses.length} weak_deny=${weakDeny.length} results=${JSON.stringify(results).slice(0, 700)}` });
        expect(bypasses.length).toBe(0);
    });

    test('D) Per-subrouter scope enforcement — P2 REVIEW (scope provisioning yok)', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'scope_per_subrouter', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Şu anki backend'de B2B key per-subrouter scope tutmuyor — tek key
        // agency'ye bağlı, tüm 11 alt-router'a erişiyor. POST /b2b/api-keys
        // contract'ı `scopes`/`permissions` field'ı kabul etmiyor. Bu
        // bilinçli bir tasarım kararı (Syroce Agency programı tek-key model)
        // ama threat-model § Elevation of Privilege açısından least-privilege
        // ilkesi ihlali → P2 REVIEW emit et, downstream provisioning eklenirse
        // v3 burada hard P1 assert eder.
        //
        // Doğrulama: oluşturulan key tüm collection endpoint'lerinde 2xx
        // veya 404 (deploy-eksik) döner; 403 (scope-deny) ASLA dönmez.
        const scopeResults = [];
        let any403 = false;
        for (const sub of SUBROUTERS) {
            if (!sub.collection) continue;
            const r = await callApiKey(request, 'get', sub.collection, undefined, createdRawKey);
            scopeResults.push({ sub: sub.name, http: r.status });
            if (r.status === 403) any403 = true;
        }
        if (any403) {
            // Beklenmedik — provisioning mevcut demek; v3'te P1 hard assert
            // pattern'i kur.
            recFinding(testInfo, 'P2', MOD,
                'B2B per-subrouter scope provisioning aktif görünüyor (beklenmedik 403)',
                `results=${JSON.stringify(scopeResults)} — v3 spec hard scope assert için yeniden kalibre edilmeli.`);
        } else {
            recFinding(testInfo, 'P2', MOD,
                'B2B key per-subrouter scope provisioning yok — least-privilege ihlali (REVIEW)',
                `Tek agency-key 11 alt-router'a erişiyor (403 yok). results=${JSON.stringify(scopeResults)}. ` +
                `Tasarım kararı; ileride per-subrouter scope eklenirse v3 burada P1 hard assert eder.`);
        }
        rec(testInfo, { module: MOD, step: 'scope_per_subrouter',
            status: 'REVIEW',
            note: `provisioning_missing=${!any403} probes=${JSON.stringify(scopeResults)}` });
    });

    test('E) Invariants — pilot_drift=0 + external_calls delta=0', async ({ request, stressTokens }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const stateBlob = JSON.parse(fs.readFileSync(
            path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'b2b_v2_matrix_done',
            stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done_v2',
            status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });

    // Idempotent cleanup — v1 spec ile aynı belt-and-suspenders pattern.
    // DELETE 2xx veya 404 (zaten silinmiş) kabul; diğer status'lar residue
    // dosyasına structured annotation yazar (CI bir sonraki turda görür).
    test.afterAll(async () => {
        if (!createdKeyAgencyId) return;
        const residueFile = path.join(process.cwd(), 'e2e-stress', '.auth', 'teardown-residue.json');
        const writeResidue = (entry) => {
            try {
                let cur = [];
                if (fs.existsSync(residueFile)) {
                    try { cur = JSON.parse(fs.readFileSync(residueFile, 'utf-8')) || []; } catch { cur = []; }
                }
                cur.push({ ts: new Date().toISOString(), spec: 'F8M v2 § 41B', ...entry });
                fs.writeFileSync(residueFile, JSON.stringify(cur, null, 2));
            } catch (e) {
                console.log(`[F8M v2 § 41B afterAll] residue file write failed: ${e.message}`);
            }
        };
        try {
            const tokenBlob = JSON.parse(fs.readFileSync(
                path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-token.json'), 'utf-8'));
            const { request: apiReq } = await import('@playwright/test');
            const ctx = await apiReq.newContext({ baseURL: process.env.E2E_BASE_URL });
            const r = await ctx.delete(`/api/b2b/api-keys/${createdKeyAgencyId}`, {
                headers: { Authorization: `Bearer ${tokenBlob.stress_token}` },
                failOnStatusCode: false, timeout: 30_000,
            });
            const status = r.status();
            await ctx.dispose();
            console.log(`[F8M v2 § 41B afterAll] cleanup DELETE: status=${status}`);
            const ok = (status >= 200 && status < 300) || status === 404;
            if (!ok) {
                writeResidue({
                    kind: 'cleanup_delete_non_ok',
                    agency_id: createdKeyAgencyId,
                    status,
                    severity: 'P2',
                    note: 'v2 matrix API key DELETE afterAll non-2xx/non-404 — residue may persist.',
                });
            }
        } catch (e) {
            console.log(`[F8M v2 § 41B afterAll] cleanup exception: ${e.message}`);
            writeResidue({
                kind: 'cleanup_exception',
                agency_id: createdKeyAgencyId,
                error: e?.message || String(e),
                severity: 'P2',
                note: 'v2 matrix API key DELETE afterAll threw — residue almost certainly persists.',
            });
        }
    });
});

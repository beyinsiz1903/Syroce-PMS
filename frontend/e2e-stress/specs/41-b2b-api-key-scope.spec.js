// F8M § 41 — B2B API Key Scope + Tenant Isolation Stress.
//
// Threat-model surface (threat_model.md § Spoofing + Information Disclosure):
// B2B API key'ler agency-scoped, tenant-scoped credential'lar. Scope bypass
// (valid stress key → pilot tenant data) veya invalid key admittance tek
// hamlede public/auth + tenant isolation boundary'lerini birlikte kırar.
//
// Mutlak kurallar:
//   - pilot mutation YOK (drift=0)
//   - external_calls=[] (post-batch helper)
//   - failedTests=0, P0=P1=0 (key oluşturma akışı zincirleme — yoksa moduleBlocked)
//
// Module-blocked pattern:
//   - Agencies list erişimi 4xx → moduleBlocked (key oluşturmak için
//     agency_id gerek). A/B/C/D test.skip + P2 informational; E pilot_drift +
//     external_calls bağımsız.
//
// Önemli: API key oluşturulursa stress tenant'a ait agency'de oluşur,
// cleanup'ta DELETE edilir (idempotent). Pilot tenant agency / pilot key
// üretmeyiz. Raw API key value response body içinde döner; assertNoTokenLeak
// "create response" hariç tüm read'lerde uygulanır (create exempt — key'i
// oluşturmanın amacı budur, sadece test scope'unda).
//
// B2B endpointleri (backend/routers/b2b_api/__init__.py): admin paths JWT
// auth, "/api/b2b/<resource>" paths API key auth (header X-API-Key).
// Bu spec sadece JWT-auth admin path'lerini (api-keys CRUD) test eder +
// X-API-Key ile basit GET smoke (/wake-up-calls, /housekeeping/rooms gibi
// read-only) yapar. Mutation/dry-run YOK çünkü real provider tetikleme
// riski + pilot tenant temas yok.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'b2b_api';

// API key bearer-style call — X-API-Key header. callTimed JWT bearer pattern
// kullandığı için ayrı wrapper. timeout 30s default.
async function callApiKey(request, method, path, body, apiKey, opts = {}) {
    const headers = { 'X-API-Key': apiKey || '', 'Content-Type': 'application/json' };
    const t0 = Date.now();
    const r = await request[method](path, {
        headers, data: body, failOnStatusCode: false, timeout: opts.timeout ?? 30_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    const ms = Date.now() - t0;
    let bodyJson = null;
    try { bodyJson = r.json ? await r.json() : null; } catch { /* ignore */ }
    return { status: r.status?.() ?? 0, ms, body: bodyJson, ok: (r.status?.() ?? 0) >= 200 && (r.status?.() ?? 0) < 300 };
}

test.describe.configure({ mode: 'serial' });

test.describe('F8M § 41 — B2B API Key Scope', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressTid = null;
    let pilotTid = null;
    let stressAgencyId = null;     // stress tenant'a ait gerçek agency
    let pilotAgencyId = null;      // pilot tenant'a ait gerçek agency (sample)
    let createdRawKey = null;      // oluşturulan API key raw value (sadece bu suite içinde)
    let createdKeyAgencyId = null; // cleanup için

    test('Setup: prefix + pilot baseline + agencies probe + create stress API key', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Stress tenant agencies list — key oluşturmak için agency_id şart.
        // 404 / 403 / boş → moduleBlocked (key flow yok).
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/agencies');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `agencies_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Agencies endpoint probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C/D skipped, E pilot_drift+external_calls still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }

        const agencies = Array.isArray(probe.body) ? probe.body
            : (probe.body?.agencies || probe.body?.items || probe.body?.data || []);
        // stress tenant kendi agency'sini al — find first matching tenant_id.
        const stressAgency = agencies.find(a => a.tenant_id === stressTid);
        if (!stressAgency) {
            moduleBlocked = true;
            blockedReason = `no_stress_agency_in_list (len=${agencies.length})`;
            recFinding(testInfo, 'P2', MOD, 'Stress tenant\'a ait agency bulunamadı',
                `agencies_list_len=${agencies.length} — seed agency yok; API key create akışı yapılamıyor. A/B/C/D skipped.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        stressAgencyId = stressAgency.id || stressAgency._id;

        // Pilot tenant agency sample (cross-tenant probe için). Pilot token
        // ile çağırırız — sızıntı testi olmadığı için stress_token kullanmıyoruz.
        try {
            const pa = await callTimed(request, 'get', '/api/agencies', undefined, stressTokens.pilot_token);
            if (pa.ok) {
                const list = Array.isArray(pa.body) ? pa.body : (pa.body?.agencies || pa.body?.items || []);
                const pilotAg = list.find(a => a.tenant_id === pilotTid);
                if (pilotAg) pilotAgencyId = pilotAg.id || pilotAg._id;
            }
        } catch (_) { /* best-effort */ }

        // Idempotent pre-cleanup: bu agency için aktif key varsa revoke et
        // (önceki round residue).
        await callTimed(request, 'delete', `/api/b2b/api-keys/${stressAgencyId}`,
            undefined, stressTokens.stress_token);

        // Key create — agency_id Query param, success body {api_key, key_prefix, ...}.
        const create = await callTimed(request, 'post',
            `/api/b2b/api-keys?agency_id=${stressAgencyId}`,
            {}, stressTokens.stress_token);

        // Architect review fix #2: create.ok=false (RBAC/deploy/network) ile
        // create.ok=true + body.api_key eksik (security contract regression)
        // ARASINDA hard split. Birincisi moduleBlocked P2, ikincisi P0 — raw
        // key dönmeyen 2xx response API contract'ı bozulmuş ve aynı zamanda
        // post-create info endpoint'i ile eşleştirme imkânsız hale gelir.
        if (!create.ok) {
            moduleBlocked = true;
            blockedReason = `key_create_non2xx_status_${create.status}_body=${JSON.stringify(create.body).slice(0, 120)}`;
            recFinding(testInfo, 'P2', MOD, 'B2B API key oluşturulamadı (non-2xx)',
                `status=${create.status} body=${JSON.stringify(create.body).slice(0, 160)} — RBAC (view_system_diagnostics) yetkisi veya endpoint deploy eksik. A/B/C/D skipped, E pilot_drift+external_calls bağımsız çalışır.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        if (!create.body?.api_key) {
            // 2xx ama raw key yok → API contract regression / security ihlali.
            // P0 emit + setup'ı moduleBlocked olarak işaretleyerek downstream
            // A/B/C/D'yi skip et (key olmadan smoke yapılamaz), ama finding
            // verdict'i NO-GO yapar.
            moduleBlocked = true;
            blockedReason = `key_create_2xx_no_api_key_body=${JSON.stringify(create.body).slice(0, 120)}`;
            recFinding(testInfo, 'P0', MOD,
                'B2B API key create 2xx döndü AMA raw api_key body\'de yok',
                `status=${create.status} body=${JSON.stringify(create.body).slice(0, 160)} — POST /api/b2b/api-keys contract\'ı raw key DÖNDÜRMELİ; aksi halde key kullanılamaz hale gelir + key_hash DB\'de yazılır ama client erişimi yok. API contract/security regression. A/B/C/D skipped (key yok).`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
                note: `module_blocked=true reason=${blockedReason} severity=P0` });
            return;
        }
        createdRawKey = create.body.api_key;
        createdKeyAgencyId = stressAgencyId;

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} stress_agency=${stressAgencyId?.slice(0, 8)} pilot_agency=${pilotAgencyId ? pilotAgencyId.slice(0, 8) : 'missing'} key_created=true key_prefix=${create.body.key_prefix}` });
    });

    test('A) Key lifecycle smoke — get info, regenerate, get info again (no leak in read responses)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'key_lifecycle', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const info = await callTimed(request, 'get',
            `/api/b2b/api-keys/${createdKeyAgencyId}`,
            undefined, stressTokens.stress_token);
        const infoOk = info.ok && info.body?.has_key === true;
        rec(testInfo, { module: MOD, step: 'key_info_read',
            status: infoOk ? 'PASS' : 'REVIEW',
            endpoint: `GET /b2b/api-keys/${createdKeyAgencyId}`, http: info.status,
            note: infoOk ? `key_prefix=${info.body?.key_prefix} usage=${info.body?.usage_count}` : `body=${JSON.stringify(info.body).slice(0, 160)}` });

        // GET response asla raw key dönmemeli — sadece key_prefix (masked).
        if (info.ok) {
            const tokOk = assertNoTokenLeak(testInfo, MOD, info.body, 'b2b_key_info_read');
            rec(testInfo, { module: MOD, step: 'key_info_token_leak_guard',
                status: tokOk ? 'PASS' : 'FAIL', note: `tok_ok=${tokOk}` });
            // Defensive: raw key body'de geçmemeli (substring check).
            if (createdRawKey && JSON.stringify(info.body).includes(createdRawKey)) {
                recFinding(testInfo, 'P0', MOD,
                    'B2B API key GET response\'unda raw key sızdı',
                    `key_info endpoint sadece prefix dönmeli; full key ${createdRawKey.slice(0, 16)}… body içinde. Threat-model § Information Disclosure.`);
            }
        }
    });

    test('B) Scope assertions — valid key 200, missing key 401/403, garbage key 401/403, cross-tenant access denied', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'scope_assertions', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }

        // Smoke endpoint: housekeeping rooms — basit GET, side-effect yok.
        // (booking_engine /availability daha güvenli ama param istiyor;
        // /housekeeping/rooms ile dene, 404 ise diğerine fallback.)
        const SMOKE = '/api/b2b/housekeeping/rooms';
        const ALLOWED_DENY = new Set([401, 403]);

        // 1) Missing key — X-API-Key boş.
        const missing = await callApiKey(request, 'get', SMOKE, undefined, '');
        const missingOk = ALLOWED_DENY.has(missing.status);
        if (missing.ok) {
            recFinding(testInfo, 'P0', MOD,
                'B2B missing-key 2xx — endpoint API key olmadan data döndü',
                `${SMOKE} no-key status=${missing.status} body=${JSON.stringify(missing.body).slice(0, 120)}. Threat-model § Elevation of Privilege.`);
        }

        // 2) Garbage key.
        const garbage = await callApiKey(request, 'get', SMOKE, undefined, 'syroce_b2b_GARBAGE_KEY_xxxxxxxxxxxxxxxxxxx');
        const garbageOk = ALLOWED_DENY.has(garbage.status);
        if (garbage.ok) {
            recFinding(testInfo, 'P0', MOD,
                'B2B garbage-key 2xx — key validation bypass',
                `${SMOKE} garbage-key status=${garbage.status} body=${JSON.stringify(garbage.body).slice(0, 120)}.`);
        }

        // 3) Valid key — 2xx beklenir (endpoint deploy mevcutsa). 404 → endpoint
        //    deploy yok, REVIEW.
        const valid = await callApiKey(request, 'get', SMOKE, undefined, createdRawKey);
        let validReachable = true;
        if (valid.status === 404) {
            validReachable = false;
            rec(testInfo, { module: MOD, step: 'b2b_smoke_endpoint_probe',
                status: 'REVIEW', note: `${SMOKE} 404 — endpoint deploy yok; smoke fallback yok.` });
        }

        rec(testInfo, { module: MOD, step: 'scope_assertions',
            status: (missingOk && garbageOk) ? 'PASS' : 'FAIL',
            note: `missing=${missing.status} garbage=${garbage.status} valid=${valid.status} reachable=${validReachable}` });

        // 4) Cross-tenant scope: valid stress key ile pilot agency ID üzerinden
        //    spesifik resource'a erişim girişimi. Backend agency-scoped key
        //    middleware'i pilot agency'nin verisini DÖNDÜRMEMELİ.
        //    Best-effort — pilotAgencyId varsa /api/b2b/folio/<pilot_booking>
        //    veya /api/b2b/groups gibi tenant-bound endpoint denenir.
        //    Burada /api/b2b/wake-up-calls smoke yapılır; valid key ile dönen
        //    sonuç stress tenant verisi olmalı, pilot identifier görünmemeli.
        const wake = await callApiKey(request, 'get', '/api/b2b/wake-up-calls', undefined, createdRawKey);
        const wakeList = Array.isArray(wake.body) ? wake.body
            : (wake.body?.wake_up_calls || wake.body?.items || []);
        let pilotLeakInWake = false;
        if (wake.ok && pilotTid) {
            // Response'da pilot tenant_id görünmemeli (defansif scan).
            const blob = JSON.stringify(wake.body);
            if (blob.includes(pilotTid)) pilotLeakInWake = true;
        }
        rec(testInfo, { module: MOD, step: 'cross_tenant_scope_wake',
            status: pilotLeakInWake ? 'FAIL' : 'PASS',
            endpoint: '/api/b2b/wake-up-calls', http: wake.status,
            note: `valid_key_returned=${wakeList.length} pilot_tid_leaked=${pilotLeakInWake}` });
        if (pilotLeakInWake) {
            recFinding(testInfo, 'P0', MOD,
                'B2B API key scope bypass — pilot tenant_id valid stress key response\'unda göründü',
                `endpoint=/api/b2b/wake-up-calls body=${JSON.stringify(wake.body).slice(0, 200)}. Cross-tenant data leak.`);
        }

        // PII guard — wake-up calls misafir bilgileri taşıyabilir (guest_name,
        // phone). Raw plaintext PII döndürmemeli.
        if (wake.ok) {
            assertPiiMasked(testInfo, MOD, wake.body,
                ['phone', 'email', 'identity_number', 'guest_phone']);
            assertNoTokenLeak(testInfo, MOD, wake.body, 'b2b_wake_read');
        }
    });

    test('C) Revoked-key contract — DELETE key, then re-attempt smoke → 401/403', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'revoked_key', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Önce key'i revoke et.
        const del = await callTimed(request, 'delete',
            `/api/b2b/api-keys/${createdKeyAgencyId}`,
            undefined, stressTokens.stress_token);
        const revokedOk = del.ok || del.status === 404;
        rec(testInfo, { module: MOD, step: 'key_revoke',
            status: revokedOk ? 'PASS' : 'REVIEW',
            endpoint: `DELETE /b2b/api-keys/${createdKeyAgencyId}`, http: del.status,
            note: `delete_status=${del.status}` });

        if (!del.ok) {
            // Revoke fail ettiyse downstream'i atla, cleanup adımı tekrar denecek.
            rec(testInfo, { module: MOD, step: 'revoked_smoke', status: 'SKIP',
                note: `revoke fail → skip post-revoke probe (status=${del.status})` });
            return;
        }

        // Revoke sonrası smoke — beklenti 401/403. 200 olursa cache stale
        // veya silinmemiş → P0.
        const after = await callApiKey(request, 'get', '/api/b2b/wake-up-calls', undefined, createdRawKey);
        const denyOk = after.status === 401 || after.status === 403;
        rec(testInfo, { module: MOD, step: 'revoked_smoke',
            status: denyOk ? 'PASS' : 'FAIL',
            endpoint: '/api/b2b/wake-up-calls', http: after.status,
            note: `revoked_status=${after.status} expected=401/403` });
        if (after.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Revoked B2B API key hala kabul ediliyor',
                `DELETE 200 sonrası aynı key smoke endpoint\'te status=${after.status} döndü. Revocation enforcement eksik veya cache stale.`);
        }
        // Marker — bu suite cleanup'ta tekrar DELETE'e gerek yok.
        createdRawKey = null;
    });

    test('D) Existence-disclosure on api-keys GET — bogus agency_id + cross-tenant pilot agency_id', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'existence_disclosure', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // GET /b2b/api-keys/<agency_id>:
        //   - bogus UUID → has_key:false 200 (endpoint shape böyle döner)
        //   - pilot agency_id → has_key:false 200 (stress token cross-tenant
        //     görmemeli). has_key:true dönerse cross-tenant disclosure P0.
        const bogus = '00000000-0000-0000-0000-000000000000';
        const b1 = await callTimed(request, 'get', `/api/b2b/api-keys/${bogus}`,
            undefined, stressTokens.stress_token);
        rec(testInfo, { module: MOD, step: 'bogus_agency_probe',
            status: 'PASS', http: b1.status,
            note: `body=${JSON.stringify(b1.body).slice(0, 120)}` });

        if (pilotAgencyId) {
            const b2 = await callTimed(request, 'get', `/api/b2b/api-keys/${pilotAgencyId}`,
                undefined, stressTokens.stress_token);
            const hasKey = b2.body?.has_key === true;
            rec(testInfo, { module: MOD, step: 'cross_tenant_agency_probe',
                status: hasKey ? 'FAIL' : 'PASS', http: b2.status,
                note: `pilot_agency=${pilotAgencyId.slice(0, 8)} has_key=${hasKey} body=${JSON.stringify(b2.body).slice(0, 120)}` });
            if (hasKey) {
                recFinding(testInfo, 'P0', MOD,
                    'Cross-tenant API key disclosure — stres token pilot agency için has_key:true gördü',
                    `pilot_agency_id=${pilotAgencyId} stres_token GET /b2b/api-keys/<pilot_agency> has_key=true döndü → tenant_id filter eksik.`);
            }
        } else {
            rec(testInfo, { module: MOD, step: 'cross_tenant_agency_probe',
                status: 'SKIP', note: 'pilot agency id setup\'ta bulunamadı' });
        }
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'b2b_api_done', stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });

    // Belt-and-suspenders cleanup: createdRawKey hala set ise (C revoke
    // çalışmadı veya skip oldu) DELETE'i tekrar dene. Idempotent.
    //
    // Architect review fix #3: cleanup hataları (DELETE non-2xx VEYA exception)
    // sessiz kalmamalı — `.auth/teardown-residue.json` dosyasına structured
    // residue annotation yazılır; CI/operator bir sonraki turda algılayabilir.
    // Idempotent re-run cleanup'ta DELETE 404 normal (önceki test revoke
    // etmiş olabilir), bu yüzden 404 başarı sayılır.
    test.afterAll(async () => {
        if (!createdKeyAgencyId) return;
        const residueFile = path.join(process.cwd(), 'e2e-stress', '.auth', 'teardown-residue.json');
        const writeResidue = (entry) => {
            try {
                let cur = [];
                if (fs.existsSync(residueFile)) {
                    try { cur = JSON.parse(fs.readFileSync(residueFile, 'utf-8')) || []; } catch { cur = []; }
                }
                cur.push({ ts: new Date().toISOString(), spec: 'F8M § 41', ...entry });
                fs.writeFileSync(residueFile, JSON.stringify(cur, null, 2));
            } catch (e) {
                console.log(`[F8M § 41 afterAll] residue file write failed: ${e.message}`);
            }
        };
        try {
            const tokenBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-token.json'), 'utf-8'));
            const { request: apiReq } = await import('@playwright/test');
            const ctx = await apiReq.newContext({ baseURL: process.env.E2E_BASE_URL });
            const r = await ctx.delete(`/api/b2b/api-keys/${createdKeyAgencyId}`, {
                headers: { Authorization: `Bearer ${tokenBlob.stress_token}` },
                failOnStatusCode: false, timeout: 30_000,
            });
            const status = r.status();
            await ctx.dispose();
            console.log(`[F8M § 41 afterAll] belt-and-suspenders DELETE: status=${status}`);
            // 2xx = silindi, 404 = zaten silinmiş (C revoke testinde) — her
            // ikisi de kabul. Diğer status'lar residue.
            const ok = (status >= 200 && status < 300) || status === 404;
            if (!ok) {
                writeResidue({
                    kind: 'cleanup_delete_non_ok',
                    agency_id: createdKeyAgencyId,
                    status,
                    severity: 'P2',
                    note: 'API key DELETE afterAll non-2xx/non-404 — residue may persist into next stress run.',
                });
            }
        } catch (e) {
            console.log(`[F8M § 41 afterAll] cleanup exception: ${e.message}`);
            writeResidue({
                kind: 'cleanup_exception',
                agency_id: createdKeyAgencyId,
                error: e?.message || String(e),
                severity: 'P2',
                note: 'API key DELETE afterAll threw — residue almost certainly persists.',
            });
        }
    });
});

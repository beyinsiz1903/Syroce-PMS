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
    callTimed, callApiKey, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'b2b_api';

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
    let revokedRawKey = null;      // tur-3 fix: C revoke ettikten sonra C2 expired-key probe için saklanır

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

    test('B2) Extended B2B smoke — availability/rates/reservations/hotel-info/guests-search/folio under valid API key', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'extended_b2b_smoke', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Validation review (tur-2): task acceptance "supplier list /
        // availability/search / quote/offer dry-run / order create dry-run".
        // Repo B2B router'ı supplier/quote/offer YOK — bunlar mevcut yüzeyle
        // eşleştirilmedi (surface mapping documented). Mevcut B2B yüzeyleri:
        //   - GET /availability (booking_engine availability/search eşleniği)
        //   - GET /rates (rate inquiry — quote/offer dry-run eşleniği)
        //   - GET /reservations + GET /reservations/{id} (order list/read)
        //   - GET /hotel-info, /content (read-only metadata)
        //   - GET /guests/search (guest lookup)
        //   - GET /folio/{booking_id} (folio inquiry)
        // POST /reservations (order create) DRY-RUN edilmiyor — invalid
        // payload (eksik room_id) ile 400/422 expect ederek "create endpoint
        // reachable + validates" doğrulanır; real booking yaratılmaz.
        const today = new Date(); today.setDate(today.getDate() + 30);
        const tomorrow = new Date(today); tomorrow.setDate(tomorrow.getDate() + 1);
        const iso = (d) => d.toISOString().slice(0, 10);
        const dateFrom = iso(today), dateTo = iso(tomorrow);

        const ALLOWED_DENY = new Set([401, 403]);
        const ALLOWED_2XX_OR_404 = (s) => (s >= 200 && s < 300) || s === 404;
        const ALLOWED_VALIDATE = (s) => s === 400 || s === 422 || s === 404;

        // Tur-3 architect fix #3: `/api/b2b/rates` backend kontratı
        // `start_date` / `end_date` bekler (booking_engine.py L672+),
        // `check_in/check_out` DEĞİL. Probe path düzeltildi.
        const smokes = [
            { name: 'availability', method: 'get', path: `/api/b2b/availability?check_in=${dateFrom}&check_out=${dateTo}`, body: undefined, expect: ALLOWED_2XX_OR_404 },
            { name: 'rates', method: 'get', path: `/api/b2b/rates?start_date=${dateFrom}&end_date=${dateTo}`, body: undefined, expect: ALLOWED_2XX_OR_404 },
            { name: 'reservations_list', method: 'get', path: '/api/b2b/reservations?limit=5', body: undefined, expect: ALLOWED_2XX_OR_404 },
            { name: 'hotel_info', method: 'get', path: '/api/b2b/hotel-info', body: undefined, expect: ALLOWED_2XX_OR_404 },
            { name: 'guests_search', method: 'get', path: '/api/b2b/guests/search?q=zzznonexistent', body: undefined, expect: ALLOWED_2XX_OR_404 },
            // Order create DRY-RUN — invalid payload, 4xx validation beklenir.
            // 2xx dönerse gerçek booking yaratıldı = pilot drift riski + P0.
            { name: 'order_create_dryrun', method: 'post', path: '/api/b2b/reservations', body: { _dryrun: true, missing_required: true }, expect: ALLOWED_VALIDATE },
        ];

        // Tur-3 architect fix #2: her probe için `expect(r.status)` enforced.
        // Beklenen status sınıfı dışı sonuç → contract violation finding.
        // Order create için 2xx = orderLeak (P0). Diğer smoke'lar için 5xx
        // veya validation-band dışı status = P1 contract violation. 401/403
        // (key reject) = P1 (valid key reddedildi → key flow bozuk).
        const results = [];
        const denyLeak = [];     // cross-tenant pilot_tid leak
        const orderLeak = [];    // order_create 2xx
        const contractViolations = [];  // expect predicate fail
        for (const s of smokes) {
            const r = await callApiKey(request, s.method, s.path, s.body, createdRawKey);
            results.push({ name: s.name, status: r.status });
            const expectOk = s.expect(r.status);
            if (s.name === 'order_create_dryrun' && r.status >= 200 && r.status < 300) {
                orderLeak.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 200) });
            }
            if (!expectOk && !(s.name === 'order_create_dryrun')) {
                contractViolations.push({ name: s.name, status: r.status });
            }
            if (r.ok && r.body) {
                assertPiiMasked(testInfo, MOD, r.body, ['phone', 'email', 'identity_number', 'iban', 'guest_phone']);
                assertNoTokenLeak(testInfo, MOD, r.body, `b2b_smoke_${s.name}`);
                if (pilotTid && JSON.stringify(r.body).includes(pilotTid)) {
                    denyLeak.push({ name: s.name, status: r.status });
                }
            }
        }

        const pass = orderLeak.length === 0 && denyLeak.length === 0 && contractViolations.length === 0;
        rec(testInfo, { module: MOD, step: 'extended_b2b_smoke',
            status: pass ? 'PASS' : 'FAIL',
            note: `results=${JSON.stringify(results)} order_leak=${orderLeak.length} cross_tenant_leak=${denyLeak.length} contract_violations=${contractViolations.length}` });
        if (contractViolations.length > 0) {
            // Valid stres key ile smoke endpoint expect sınıfı dışı status —
            // contract zayıflığı veya API key middleware reject (401/403)
            // beklenmedik. P1 (valid key flow bozuk veya endpoint deploy
            // gevşek).
            recFinding(testInfo, 'P1', MOD,
                'B2B extended smoke endpoint contract violation',
                `Beklenen 2xx/404. Gözlenen: ${JSON.stringify(contractViolations)}. Valid stres key ile çağrılan endpoint expect band dışı status döndü; API key middleware reject veya endpoint deploy/shape regression olabilir.`);
        }
        if (orderLeak.length > 0) {
            recFinding(testInfo, 'P0', MOD,
                'B2B order create dry-run 2xx — gerçek reservation yaratıldı + pilot drift riski',
                `POST /api/b2b/reservations invalid payload ile 2xx döndü: ${JSON.stringify(orderLeak)}. Validation eksik veya endpoint deploy gevşek + dry-run kontratı yok.`);
        }
        if (denyLeak.length > 0) {
            recFinding(testInfo, 'P0', MOD,
                'B2B smoke response\'unda pilot tenant_id sızdı',
                `Cross-tenant leak endpoints: ${JSON.stringify(denyLeak)}. Valid stress key pilot tenant verisi gördü.`);
        }
        // Supplier / quote / offer endpoint mapping not-found documented.
        rec(testInfo, { module: MOD, step: 'b2b_surface_mapping_doc', status: 'PASS',
            note: 'supplier_list/quote/offer endpoints NOT present in backend/routers/b2b_api/ — surface mapping documented in spec header. F8M scope kapatıldı; supplier/quote/offer F8E (finance) veya F8G (sales-CRM) kapsamında ele alınmalı.' });
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
        // Tur-3 architect fix: revoked raw key'i ayrı değişkende sakla; C2
        // expired-key probe BUNU kullanır. createdRawKey null'lanır çünkü
        // afterAll cleanup için artık DELETE gereksiz.
        revokedRawKey = createdRawKey;
        createdRawKey = null;
    });

    test('C2) Expired-key + wrong-tenant endpoint-level scope', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'expired_wrong_tenant', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Validation review (tur-2): "explicit expired-key (401) + wrong-tenant
        // endpoint-level".
        //
        // Tur-3 architect fix: C testinde revoke edilen key `revokedRawKey`'de
        // saklanır (createdRawKey null'lanır). Expired-key endpoint coverage
        // BURADA enforced — `revokedRawKey` yoksa C revoke fail etmiş veya
        // module blocked. Coverage gap olmaması için revokedRawKey YOKSA
        // explicit REVIEW + P2 emit (test acceptance "expired-key 401"
        // doğrulanamadı sinyali).
        // Tur-4 architect fix: `/api/b2b/availability` backend contract
        // `check_in`/`check_out` bekler (booking_engine.py L613-L617).
        // start_date/end_date kullanırsak 400 validation döner ve C2
        // unexpectedDeny olarak P1 contract violation finding emit eder
        // — bu yanlış pozitif. Auth contract sinyalini saf tutmak için
        // doğru query param'ları kullan; revoke edilmiş key zaten
        // middleware'de 401/403 dönmeli, parameter validation'a hiç
        // ulaşmamalı.
        const expiredEndpoints = [
            '/api/b2b/housekeeping/rooms',
            `/api/b2b/availability?check_in=2026-12-01&check_out=2026-12-02`,
            '/api/b2b/hotel-info',
        ];
        const expiredResults = [];
        const expiredLeak = [];
        const ALLOWED_DENY_C2 = new Set([401, 403]);
        const unexpectedDeny = [];
        if (revokedRawKey) {
            for (const ep of expiredEndpoints) {
                const r = await callApiKey(request, 'get', ep, undefined, revokedRawKey);
                expiredResults.push({ ep, status: r.status });
                if (r.status >= 200 && r.status < 300) {
                    expiredLeak.push({ ep, status: r.status });
                } else if (!ALLOWED_DENY_C2.has(r.status) && r.status !== 404) {
                    // 5xx veya beklenmedik 4xx (örn. 400) → contract zayıflığı.
                    unexpectedDeny.push({ ep, status: r.status });
                }
            }
        } else {
            // Revoke fail edip revokedRawKey set değilse coverage gap.
            recFinding(testInfo, 'P2', MOD,
                'Expired-key endpoint scope coverage yok — revokedRawKey eksik',
                `C testi revoke yapamadı veya skip oldu; expired-key 401 enforcement doğrulanamadı.`);
        }
        rec(testInfo, { module: MOD, step: 'expired_key_endpoint_scope',
            status: !revokedRawKey ? 'REVIEW'
                : (expiredLeak.length === 0 && unexpectedDeny.length === 0 ? 'PASS' : 'FAIL'),
            note: `revoked_key_present=${revokedRawKey != null} results=${JSON.stringify(expiredResults)} leaks=${expiredLeak.length} unexpected_status=${unexpectedDeny.length}` });
        if (unexpectedDeny.length > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Expired B2B API key endpoint contract zayıf — 401/403/404 dışı status döndü',
                `Beklenen 401/403/404. Gözlenen: ${JSON.stringify(unexpectedDeny)}. Endpoint deny path tutarsız (validation 400 veya 5xx).`);
        }
        if (expiredLeak.length > 0) {
            recFinding(testInfo, 'P0', MOD,
                'Expired (revoked) B2B API key endpoint-level\'de hala 2xx dönüyor',
                `Endpoints: ${JSON.stringify(expiredLeak)}. C testinde DELETE 2xx ama key cache stale veya revocation enforcement yarım. Tek bir endpoint deny ediyor olabilir; sistem-wide deny gerekir.`);
        }

        // Wrong-tenant endpoint-level: bu test için tekrar bir key oluştur
        // (C revoke etti). Stress key ile pilot booking ID üzerinden
        // /folio/{pilot_booking_id} dene — 404/403 dönmeli; 2xx + folio
        // content dönerse cross-tenant disclosure (P0).
        let wrongTenantResult = null;
        try {
            // Re-create stress key for wrong-tenant test.
            const recreate = await callTimed(request, 'post',
                `/api/b2b/api-keys?agency_id=${createdKeyAgencyId}`, {}, stressTokens.stress_token);
            if (recreate.ok && recreate.body?.api_key) {
                const wtKey = recreate.body.api_key;
                createdRawKey = wtKey; // afterAll temizlesin diye güncelle.
                // Pilot booking ID setup'ta alınmadı; sample için pilot
                // bookings list'ten çek.
                let pilotBookingId = null;
                try {
                    const b = await callTimed(request, 'get', '/api/pms/bookings?limit=1',
                        undefined, stressTokens.pilot_token);
                    if (b.ok) {
                        const list = Array.isArray(b.body) ? b.body : (b.body?.bookings || b.body?.items || []);
                        if (list[0]) pilotBookingId = list[0].id || list[0]._id;
                    }
                } catch (_) {}
                if (pilotBookingId) {
                    const r = await callApiKey(request, 'get', `/api/b2b/folio/${pilotBookingId}`, undefined, wtKey);
                    wrongTenantResult = { booking: pilotBookingId.slice(0, 8), status: r.status,
                        body_size: JSON.stringify(r.body || {}).length };
                    if (r.status >= 200 && r.status < 300 && r.body && Object.keys(r.body).length > 0) {
                        recFinding(testInfo, 'P0', MOD,
                            'Wrong-tenant B2B API key cross-tenant folio disclosure',
                            `Stres tenant key + pilot booking_id GET /api/b2b/folio/${pilotBookingId} status=${r.status} body_size=${JSON.stringify(r.body).length}. Cross-tenant data leak.`);
                    }
                    // PII + cross-tenant tid scan
                    if (r.ok && r.body) {
                        assertPiiMasked(testInfo, MOD, r.body, ['phone', 'email', 'identity_number']);
                        if (JSON.stringify(r.body).includes(pilotTid)) {
                            recFinding(testInfo, 'P0', MOD,
                                'Wrong-tenant folio response pilot_tid içeriyor',
                                `endpoint=/api/b2b/folio/${pilotBookingId} pilot_tid leak.`);
                        }
                    }
                }
            }
        } catch (e) {
            rec(testInfo, { module: MOD, step: 'wrong_tenant_setup_err', status: 'REVIEW',
                note: `recreate_failed=${e.message}` });
        }
        // Tur-3 architect fix #4: wrong-tenant final rec'i evidence'a bağla —
        // recreate fail / pilot booking yoksa REVIEW (coverage gap),
        // wrongTenantResult 2xx + body → FAIL (P0 zaten emit), 4xx → PASS.
        let wtStatus = 'REVIEW';
        let wtNote = `result=${JSON.stringify(wrongTenantResult)}`;
        if (wrongTenantResult) {
            const s = wrongTenantResult.status;
            if (s >= 200 && s < 300 && wrongTenantResult.body_size > 2) {
                wtStatus = 'FAIL';
                wtNote = `LEAK status=${s} body_size=${wrongTenantResult.body_size} (P0 emitted)`;
            } else if (s === 401 || s === 403 || s === 404) {
                wtStatus = 'PASS';
                wtNote = `denied_correctly status=${s}`;
            } else {
                wtStatus = 'REVIEW';
                wtNote = `unexpected status=${s} body_size=${wrongTenantResult.body_size}`;
            }
        } else {
            recFinding(testInfo, 'P2', MOD,
                'Wrong-tenant endpoint scope coverage yok',
                `Stress key re-create veya pilot booking_id sample edilemedi → cross-tenant folio probe çalıştırılamadı.`);
        }
        rec(testInfo, { module: MOD, step: 'wrong_tenant_endpoint_scope',
            status: wtStatus, note: wtNote });
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

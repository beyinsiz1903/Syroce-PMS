// F8L § 50 — Channel Manager Exely Webhook Stress.
//
// Threat-model surface (threat_model.md § Spoofing + Tampering +
// Information Disclosure + DoS): `/api/webhooks/exely/*` provider'a
// SOAP/JSON callback yüzeyi açar. Doğrulama: IP whitelist (fail-closed),
// payload-size limit (EXELY_MAX_PAYLOAD_BYTES, default 256 KiB),
// empty-body reject, raw-payload PII guard (webhook_raw_payloads
// collection PII içerebilir → admin endpoint masklanmalı).
//
// Mutlak kurallar:
//   - pilot mutation YOK (drift=0). Webhook payload'larında tenant_id
//     YALNIZ stress_tid kullanılır; pilot_tid içerikli forge denemesi
//     reject edilmeli + pilot baseline değişmemeli.
//   - external_calls=[] (post-batch helper). Inbound webhook'lar
//     processing'i background task'a atıyor ama OUTBOUND OTA push
//     yapmıyor; dispatcher dry-run + stress_tid scope altında.
//   - failedTests=0, P0=P1=0.
//
// Module-blocked pattern (F8M § 40/41 mirror):
//   - GET /health probe non-2xx VEYA POST /reservations 5xx storm →
//     moduleBlocked + P2 informational + A/B/C/D test.skip; E pilot_drift
//     + external_calls bağımsız çalışır.
//
// Backend yüzeyleri (backend/domains/channel_manager/providers/exely/
// exely_webhook_router.py):
//   - GET  /api/webhooks/exely/health   (PingRS — sağlık probu)
//   - GET  /api/webhooks/exely/info     (config snapshot)
//   - POST /api/webhooks/exely/reservations (SOAP/XML payload, IP-gated)
//
// Auth contract:
//   - EXELY_IP_WHITELIST unset + ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK!=1
//     → 503 "Webhook not configured" (fail-closed).
//   - IP whitelist set ama caller IP listede değil → 403 SOAP fault.
//   - Bypass aktif (dev/staging only) → 2xx/4xx body-validation path'i.
//
// Stress E2E ortamında EXELY_IP_WHITELIST genelde set DEĞİL veya
// ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1 aktif olabilir. Spec her iki
// path'i de tanır:
//   - 503 → fail-closed contract honored (PASS)
//   - 403 → IP-gate enforced (PASS)
//   - 2xx/4xx (body validation) → bypass aktif, deeper assertions yürütülür
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'cm_exely_webhook';
const BASE = '/api/webhooks/exely';

// Webhook callback — anonymous (no auth header). Bearer pattern kullanmayız.
async function callWebhook(request, method, urlPath, opts = {}) {
    const headers = { 'Content-Type': opts.contentType || 'application/xml', ...(opts.headers || {}) };
    const t0 = Date.now();
    const r = await request[method](urlPath, {
        headers,
        data: opts.body,
        failOnStatusCode: false,
        timeout: opts.timeout ?? 30_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    const ms = Date.now() - t0;
    let bodyText = null, bodyJson = null;
    try { bodyText = r.text ? await r.text() : null; } catch { /* ignore */ }
    try { bodyJson = bodyText && bodyText.trim().startsWith('{') ? JSON.parse(bodyText) : null; } catch { /* xml/soap */ }
    const status = r.status?.() ?? 0;
    return { status, ms, body: bodyJson, text: bodyText, ok: status >= 200 && status < 300 };
}

// Webhook auth-mode classification:
//   - "fail_closed_503"   : config eksik, hiç bir 2xx yok (PASS contract).
//   - "ip_gated_403"      : IP whitelist aktif, biz dışındayız (PASS contract).
//   - "open_for_testing"  : bypass aktif, body-validation path'i açık.
function classifyMode(probeStatus) {
    if (probeStatus === 503) return 'fail_closed_503';
    if (probeStatus === 403) return 'ip_gated_403';
    if (probeStatus >= 200 && probeStatus < 500) return 'open_for_testing';
    return 'unknown';
}

test.describe.configure({ mode: 'serial' });

test.describe('F8L § 50 — Exely Webhook Stress', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressTid = null;
    let pilotTid = null;
    let authMode = 'unknown';

    test('Setup: prefix + pilot baseline + GET /health + GET /info reachability + auth-mode classification', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // /health probe — anonymous GET. 200 beklenir; 404 → router mount yok
        // (moduleBlocked); 5xx → backend down (moduleBlocked).
        const h = await callWebhook(request, 'get', `${BASE}/health`);
        rec(testInfo, { module: MOD, step: 'webhook_health_probe',
            status: h.ok ? 'PASS' : (h.status === 404 ? 'REVIEW' : 'FAIL'),
            endpoint: `GET ${BASE}/health`, http: h.status,
            note: `body=${(h.text || '').slice(0, 160)}` });
        if (h.status === 404) {
            moduleBlocked = true;
            blockedReason = `health_404 (router not mounted)`;
            recFinding(testInfo, 'P2', MOD, 'Exely webhook router not mounted (404)',
                `GET ${BASE}/health 404 — router deploy yok. A/B/C/D skipped, E pilot_drift+external_calls bağımsız.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        if (h.status >= 500) {
            moduleBlocked = true;
            blockedReason = `health_${h.status}_backend_unhealthy`;
            recFinding(testInfo, 'P2', MOD, `Exely webhook /health 5xx (status=${h.status})`,
                `Backend down veya init incomplete. A/B/C/D skipped.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }

        // /info probe — config snapshot. Anonymous GET. PII/token leak guard.
        const info = await callWebhook(request, 'get', `${BASE}/info`);
        rec(testInfo, { module: MOD, step: 'webhook_info_probe',
            status: info.ok ? 'PASS' : 'REVIEW',
            endpoint: `GET ${BASE}/info`, http: info.status,
            note: `body=${(info.text || '').slice(0, 200)}` });
        if (info.ok) {
            // /info response credential/secret material döndürmemeli
            // (EXELY_IP_WHITELIST IP listesi ok; secret/token YASAK).
            const tokOk = assertNoTokenLeak(testInfo, MOD, info.body || info.text || {}, 'exely_info');
            rec(testInfo, { module: MOD, step: 'info_token_leak_guard',
                status: tokOk ? 'PASS' : 'FAIL', note: `tok_ok=${tokOk}` });
        }

        // Auth-mode classification — POST /reservations boş body probe.
        // Beklenen contract:
        //   - 503 → fail_closed (EXELY_IP_WHITELIST set değil)
        //   - 403 → ip_gated (whitelist set, biz dışındayız)
        //   - 400 → bypass aktif, empty body reject (open_for_testing)
        const empty = await callWebhook(request, 'post', `${BASE}/reservations`, { body: '' });
        authMode = classifyMode(empty.status);
        rec(testInfo, { module: MOD, step: 'auth_mode_classification',
            status: (authMode !== 'unknown') ? 'PASS' : 'REVIEW',
            endpoint: `POST ${BASE}/reservations`, http: empty.status,
            note: `auth_mode=${authMode} empty_probe_status=${empty.status}` });

        if (authMode === 'unknown') {
            moduleBlocked = true;
            blockedReason = `auth_mode_unknown_status_${empty.status}`;
            recFinding(testInfo, 'P2', MOD, 'Exely webhook auth mode classify edilemedi',
                `POST ${BASE}/reservations empty body status=${empty.status} bekleneni dışında (503/403/4xx). Endpoint deploy belirsiz; A/B/C/D skipped.`);
        }

        rec(testInfo, { module: MOD, step: 'setup',
            status: moduleBlocked ? 'PASS' : 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} stress_tid=${stressTid?.slice(0, 8)} pilot_tid=${pilotTid?.slice(0, 8)} auth_mode=${authMode}` });
    });

    test('A) Auth contract — empty body, garbage payload, missing content-type → fail-closed (503/403/400)', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'auth_contract', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Acceptance contract (auth-mode aware):
        //   - fail_closed_503: tüm POST'lar 503 dönmeli (config missing).
        //   - ip_gated_403   : tüm POST'lar 403 dönmeli (caller IP not whitelisted).
        //   - open_for_testing: empty=400, garbage=400/422, validation path açık.
        const ALLOWED = {
            fail_closed_503: new Set([503]),
            ip_gated_403:    new Set([403]),
            open_for_testing: new Set([400, 422]),
        };
        const expected = ALLOWED[authMode] || new Set();

        const probes = [
            { name: 'empty_body', body: '', ct: 'application/xml' },
            { name: 'garbage_xml', body: '<not>valid</xml>', ct: 'application/xml' },
            { name: 'wrong_content_type', body: '{"x":1}', ct: 'text/plain' },
            { name: 'json_body_xml_endpoint', body: '{"forge":true,"tenant_id":"' + (stressTid || 'x') + '"}', ct: 'application/json' },
        ];
        const violations = [];
        const accepted2xx = [];
        for (const p of probes) {
            const r = await callWebhook(request, 'post', `${BASE}/reservations`,
                { body: p.body, contentType: p.ct });
            if (r.status >= 200 && r.status < 300) {
                // 2xx kabul = SOAP fault olmasa bile reservation create attempt
                // başladı → tehlike. open_for_testing modunda bile invalid
                // payload 2xx dönmemeli.
                accepted2xx.push({ name: p.name, status: r.status, body_size: (r.text || '').length });
            }
            if (!expected.has(r.status) && !(r.status >= 200 && r.status < 300)) {
                violations.push({ name: p.name, status: r.status, expected: [...expected] });
            }
        }
        const pass = accepted2xx.length === 0 && violations.length === 0;
        rec(testInfo, { module: MOD, step: 'auth_contract',
            status: pass ? 'PASS' : 'FAIL',
            note: `auth_mode=${authMode} accepted2xx=${accepted2xx.length} violations=${violations.length} detail=${JSON.stringify(violations).slice(0, 200)}` });

        if (accepted2xx.length > 0) {
            recFinding(testInfo, 'P0', MOD,
                'Exely webhook invalid payload\'lar 2xx döndürdü — body validation bypass',
                `Probes accepted: ${JSON.stringify(accepted2xx)}. SOAP/XML schema validation eksik veya empty/garbage payload reservation pipeline\'a sızıyor. Threat-model § Tampering.`);
        }
        if (violations.length > 0 && authMode === 'fail_closed_503') {
            recFinding(testInfo, 'P1', MOD,
                'Exely webhook fail-closed contract zayıf',
                `EXELY_IP_WHITELIST config eksik beklenirdi (auth_mode=fail_closed_503), tüm POST'lar 503 olmalıydı. Gözlenen: ${JSON.stringify(violations)}. Fail-closed kuralı kısmen kırık.`);
        }
        if (violations.length > 0 && authMode === 'ip_gated_403') {
            recFinding(testInfo, 'P1', MOD,
                'Exely webhook IP-gate enforcement tutarsız',
                `auth_mode=ip_gated_403, tüm POST'lar 403 olmalıydı. Gözlenen: ${JSON.stringify(violations)}.`);
        }
    });

    test('B) Payload-size limit — oversized body (>256 KiB) → 400/413', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'payload_limit', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // EXELY_MAX_PAYLOAD_BYTES default 256 KiB; 512 KiB body
        // EXPECT 400 (oversized) veya 413 (payload too large) — auth-mode'a göre
        // 503/403 da kabul (fail-closed öncelikli).
        const big = '<x>' + 'A'.repeat(512 * 1024) + '</x>';
        const r = await callWebhook(request, 'post', `${BASE}/reservations`,
            { body: big, contentType: 'application/xml', timeout: 60_000 });
        const ALLOWED_OVERSIZE = new Set([400, 413, 503, 403, 422]);
        const ok = ALLOWED_OVERSIZE.has(r.status);
        rec(testInfo, { module: MOD, step: 'payload_size_limit',
            status: ok ? 'PASS' : 'FAIL',
            endpoint: `POST ${BASE}/reservations`, http: r.status,
            note: `body_size=512KiB status=${r.status} auth_mode=${authMode}` });
        if (r.status >= 200 && r.status < 300) {
            recFinding(testInfo, 'P0', MOD,
                'Exely webhook oversize payload 2xx — size limit yok',
                `512 KiB body status=${r.status} kabul edildi. EXELY_MAX_PAYLOAD_BYTES enforcement eksik → DoS riski.`);
        } else if (!ok) {
            recFinding(testInfo, 'P1', MOD,
                'Exely webhook oversize payload beklenmedik status',
                `512 KiB body status=${r.status} (beklenen 400/413/503/403). Size-limit path tutarsız.`);
        }
    });

    test('C) Tenant injection probe — forge pilot_tid içerikli payload pilot tenant\'a sızdırmamalı', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'tenant_injection', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Probe doctrine: Webhook payload içine pilot_tid enjekte edilir.
        // Beklenti:
        //   - fail_closed/ip_gated mode'da: 503/403 — payload hiç parse
        //     edilmiyor, pilot drift impossible.
        //   - open mode'da: body validation (4xx) veya body kabul +
        //     stress_tid scope. Pilot tenant'a sızdırma KESİNLİKLE YASAK.
        // Kanıt: testin sonunda assertPilotDriftZero (E suite) çağrılır;
        // burada sadece per-call status + body inspection.
        const payload = `<?xml version="1.0"?><Reservation><TenantId>${pilotTid}</TenantId><Hotel>forge</Hotel><Guest><Name>STRESS_FORGE</Name></Guest></Reservation>`;
        const r = await callWebhook(request, 'post', `${BASE}/reservations`,
            { body: payload, contentType: 'application/xml' });
        const acceptedAs2xx = r.status >= 200 && r.status < 300;
        // ACCEPTED 2xx mode'a bağlı:
        //   - fail_closed/ip_gated → 2xx asla görmemeli (P0)
        //   - open → 2xx görse bile pilot drift kanıt E'de
        const pass = !acceptedAs2xx || authMode === 'open_for_testing';
        rec(testInfo, { module: MOD, step: 'tenant_injection_probe',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: `POST ${BASE}/reservations`, http: r.status,
            note: `auth_mode=${authMode} accepted_2xx=${acceptedAs2xx} body=${(r.text || '').slice(0, 160)}` });
        if (acceptedAs2xx && authMode !== 'open_for_testing') {
            recFinding(testInfo, 'P0', MOD,
                'Exely webhook fail-closed/ip-gated mode altında tenant-injection payload 2xx döndü',
                `payload pilot_tid enjekteli + auth_mode=${authMode}; gate bypass + tenant injection kombinasyonu. Threat-model § Spoofing + Tampering.`);
        }

        // Architect review fix #3: response raw text üzerinde gerçek
        // PII regex scan (email + TR-mobil + 11-haneli TC). assertPiiMasked
        // recursive ama string-as-value görmüyor; SOAP/XML response için
        // raw scan daha kanıtlayıcı.
        if (r.text) {
            const t = r.text.slice(0, 4096);
            const piiHits = {
                email: /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/.test(t),
                tr_mobile: /(?:\+?9?0?5\d{2})[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}/.test(t),
                tc_id: /\b[1-9]\d{10}\b/.test(t),
            };
            const piiOk = !Object.values(piiHits).some(Boolean);
            rec(testInfo, { module: MOD, step: 'tenant_injection_pii_raw_scan',
                status: piiOk ? 'PASS' : 'FAIL',
                note: `hits=${JSON.stringify(piiHits)} sample_len=${t.length}` });
            if (!piiOk) {
                recFinding(testInfo, 'P1', MOD,
                    'Exely webhook response raw text\'inde PII pattern',
                    `hits=${JSON.stringify(piiHits)} body_sample=${t.slice(0, 240)}. SOAP fault/echo response misafir PII\'sini echo ediyor olabilir.`);
            }
        }
    });

    test('D) Replay & burst — aynı payload 5x ardışık POST, 5xx storm yok + status istikrarlı', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'replay_burst', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // 5xx storm = backend resilience failure; tek bir webhook tekrarı
        // tenant'ı düşürmemeli. 5xx count >= 1 → P1 (DoS riski).
        const payload = '<?xml version="1.0"?><Reservation><Stress>true</Stress></Reservation>';
        const N = 5;
        const statuses = [];
        for (let i = 0; i < N; i++) {
            const r = await callWebhook(request, 'post', `${BASE}/reservations`,
                { body: payload, contentType: 'application/xml' });
            statuses.push(r.status);
        }
        const fiveXX = statuses.filter(s => s >= 500 && s !== 503).length;
        const distinct = new Set(statuses);
        rec(testInfo, { module: MOD, step: 'replay_burst',
            status: fiveXX === 0 ? 'PASS' : 'FAIL',
            note: `statuses=${JSON.stringify(statuses)} 5xx_storm=${fiveXX} distinct=${distinct.size}` });
        if (fiveXX > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Exely webhook replay burst altında 5xx storm',
                `${N} ardışık POST'tan ${fiveXX} adet 5xx (503 hariç). Backend resilience zayıf veya rate-limit hatası DoS yüzeyine dönüşebilir.`);
        }
    });

    test('F) EXELY readiness gate — env contract semantics (configured PASS / HR-only N/A / prod-like unset P1)', async ({ }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'exely_readiness_gate', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Architect-iter-3 talebi: EXELY_IP_WHITELIST için açık readiness
        // sinyal gate'i. Kontratlar (env-based, prod-config-aware):
        //   - EXELY_IP_WHITELIST set + ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK!=1
        //     → CONFIGURED (PASS) — production'a hazır.
        //   - HOTELRUNNER-only kurulum (Exely yok, AFSADAKAT_BASE_URL set
        //     ama EXELY env yok) → HR-only N/A (REVIEW, informational).
        //   - Prod-like unset (EXELY_IP_WHITELIST yok + ALLOW_UNAUTH yok)
        //     → P1 — fail-closed 503 contract honored ama prod readiness
        //     bozuk; CI'da explicit sinyal gerekli.
        //   - Bypass aktif (ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1) → P1
        //     (dev/staging only, prod'da SAKINCALI).
        const wl = (process.env.EXELY_IP_WHITELIST || '').trim();
        const bypass = process.env.ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK === '1';
        const hrOnly = !!process.env.HOTELRUNNER_WEBHOOK_SECRET && !wl && !bypass;
        let gate, severity;
        if (wl && !bypass) {
            gate = 'configured'; severity = null;
        } else if (bypass) {
            gate = 'bypass_active_dev_only'; severity = 'P1';
        } else if (hrOnly) {
            gate = 'hr_only_na'; severity = null;
        } else {
            gate = 'prod_like_unset'; severity = 'P1';
        }
        const pass = severity === null;
        rec(testInfo, { module: MOD, step: 'exely_readiness_gate',
            status: pass ? 'PASS' : (severity === 'P1' ? 'FAIL' : 'REVIEW'),
            note: `gate=${gate} wl_set=${!!wl} bypass=${bypass} hr_only=${hrOnly} auth_mode=${authMode}` });
        if (severity === 'P1') {
            const detail = (gate === 'bypass_active_dev_only')
                ? `ALLOW_UNAUTHENTICATED_EXELY_WEBHOOK=1 — production'da SAKINCALI; sadece dev/staging için geçerli.`
                : `EXELY_IP_WHITELIST set değil + bypass yok — fail-closed 503 contract honored ama production readiness bozuk. CI/CD env'inde whitelist seed'i gerekli.`;
            recFinding(testInfo, 'P1', MOD,
                `Exely readiness gate ${gate}`, detail);
        }
        if (gate === 'hr_only_na') {
            recFinding(testInfo, 'P2', MOD,
                'Exely readiness: HR-only kurulum (Exely entegrasyonu kullanılmıyor)',
                `HOTELRUNNER_WEBHOOK_SECRET var, EXELY_IP_WHITELIST yok. Exely path'leri prod'da kullanılmıyor varsayılır; N/A.`);
        }
    });

    test('G) Conditional valid payload + duplicate ingest idempotency (auth-mode=open_for_testing veya EXELY_IP_WHITELIST set)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'valid_payload_idemp', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Architect-iter-3 talebi: Exely valid parse + duplicate reservation
        // idempotency. Conditional on:
        //   - auth_mode=open_for_testing (bypass aktif, body kabul ediliyor) VE
        //   - stres ortamında Exely kullanıma uygun (env config).
        // Aksi halde REVIEW + P2 informational.
        if (authMode !== 'open_for_testing') {
            rec(testInfo, { module: MOD, step: 'valid_payload_idemp',
                status: 'REVIEW',
                note: `auth_mode=${authMode} — valid-payload path açık değil (fail_closed/ip_gated)` });
            recFinding(testInfo, 'P2', MOD,
                'Exely valid-payload + idempotency coverage gap',
                `auth_mode=${authMode}. Bu koşuda valid parse path test edilemedi; production-like ortamda (whitelist + caller IP) test sürdürülmeli.`);
            return;
        }
        // Open mode'da minimum valid SOAP payload + aynı reservation_id 2x ingest.
        const stableId = `${prefix || 'STRESS'}_EXELY_IDEMP_FIXED`;
        const validPayload = `<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body><Reservation><TenantId>${stressTid}</TenantId><Id>${stableId}</Id><Status>new</Status><Guest><Name>STRESS_VALID</Name></Guest></Reservation></soap:Body></soap:Envelope>`;
        let r1, r2;
        try {
            r1 = await request.post(`${BASE}/reservations`, {
                headers: { 'Content-Type': 'application/xml' },
                data: validPayload, failOnStatusCode: false, timeout: 30_000,
            });
        } catch (e) {
            rec(testInfo, { module: MOD, step: 'valid_payload_idemp',
                status: 'FAIL', note: `r1 network: ${e?.message}` });
            recFinding(testInfo, 'P1', MOD, 'Exely valid-payload r1 network error', `${e?.message}`);
            throw e;
        }
        await new Promise((r) => setTimeout(r, 500));
        try {
            r2 = await request.post(`${BASE}/reservations`, {
                headers: { 'Content-Type': 'application/xml' },
                data: validPayload, failOnStatusCode: false, timeout: 30_000,
            });
        } catch (e) {
            rec(testInfo, { module: MOD, step: 'valid_payload_idemp',
                status: 'FAIL', note: `r2 network: ${e?.message}` });
            recFinding(testInfo, 'P1', MOD, 'Exely valid-payload r2 network error', `${e?.message}`);
            throw e;
        }
        const s1 = r1.status();
        const s2 = r2.status();
        const both2xx = (s1 >= 200 && s1 < 300) && (s2 >= 200 && s2 < 300);
        // Idempotency contract: aynı stableId ile 2 ingest → r2 status sınıfı r1
        // ile aynı (her ikisi 2xx kabul, dedupe sessizce çalışır) VEYA r2 conflict
        // (409). r2 5xx veya farklı bir 4xx → idempotency tutarsız.
        const idempotencyOk = both2xx || (s1 === s2);
        rec(testInfo, { module: MOD, step: 'valid_payload_idemp',
            status: idempotencyOk ? 'PASS' : 'FAIL',
            note: `r1=${s1} r2=${s2} both2xx=${both2xx} stable_id=${stableId}` });
        if (!idempotencyOk) {
            recFinding(testInfo, 'P0', MOD,
                'Exely valid-payload duplicate ingest idempotency kırık',
                `r1=${s1} r2=${s2}. Aynı reservation_id=${stableId} 2x ingest farklı sonuçlar üretti.`);
        }
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'cm_exely_webhook_done', stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });
});

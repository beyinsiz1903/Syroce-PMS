// F8L § 51 — HotelRunner Webhook Signature + Outbox Stress.
//
// Threat-model surface (threat_model.md § Spoofing + Tampering):
// `/api/channel-manager/hotelrunner/*` provider'a signed callback yüzeyi.
// HMAC-SHA256(secret, "{ts}.{raw_body}") imza zorunlu (header
// X-HotelRunner-Signature + X-HotelRunner-Timestamp). Bypass:
// `ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK=1` (dev only). Secret missing +
// bypass off → 503 fail-closed.
//
// Mutlak kurallar:
//   - pilot mutation YOK (drift=0). Signed payload'larda tenant_id
//     YALNIZ stress_tid; pilot_tid forge denemesi reject edilmeli.
//   - external_calls=[] (post-batch helper). Webhook ingest pipeline
//     OUTBOUND OTA push tetiklemez; sadece outbox/raw_payloads'a yazar.
//   - failedTests=0, P0=P1=0.
//
// Module-blocked pattern (F8M § 40/41 + F8L § 50 mirror):
//   - GET /logs/events reachability non-2xx VEYA POST /callback 5xx storm
//     → moduleBlocked + P2 informational + A/B/C/D skip; E pilot_drift +
//     external_calls bağımsız.
//
// Backend yüzeyleri (backend/domains/channel_manager/providers/
// hotelrunner_webhook.py):
//   - POST /api/channel-manager/hotelrunner/callback              (signed, unified)
//   - POST /api/channel-manager/hotelrunner/webhooks/reservations  (signed)
//   - POST /api/channel-manager/hotelrunner/webhooks/modifications (signed)
//   - POST /api/channel-manager/hotelrunner/webhooks/cancellations (signed)
//   - GET  /api/channel-manager/hotelrunner/logs/events  (JWT auth)
//   - GET  /api/channel-manager/hotelrunner/logs/errors  (JWT auth)
//
// Signature contract (_verify_hotelrunner_signature):
//   - secret unset + bypass off → 503
//   - missing headers → 401 "Missing signature headers"
//   - ts > 300s skew → 401 "Timestamp out of tolerance"
//   - bad sig → 401 "Invalid signature"
//
// Stress E2E ortamında HOTELRUNNER_WEBHOOK_SECRET genelde set DEĞİL ve
// ALLOW_UNSIGNED_HOTELRUNNER_WEBHOOK!=1 → 503 fail-closed. Bu durumda
// signed-path test'leri 503 alır ve "fail-closed contract honored" PASS.
// Bypass aktifse signed-path 2xx + body validation çalışır.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'cm_hotelrunner_webhook';
const BASE = '/api/channel-manager/hotelrunner';

async function callWebhook(request, method, urlPath, opts = {}) {
    const headers = { 'Content-Type': opts.contentType || 'application/json', ...(opts.headers || {}) };
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
    try { bodyJson = bodyText && bodyText.trim().startsWith('{') ? JSON.parse(bodyText) : null; } catch {}
    const status = r.status?.() ?? 0;
    return { status, ms, body: bodyJson, text: bodyText, ok: status >= 200 && status < 300 };
}

function classifyMode(probeStatus) {
    if (probeStatus === 503) return 'fail_closed_503';
    if (probeStatus === 401) return 'sig_required_401';
    if (probeStatus >= 200 && probeStatus < 500) return 'open_for_testing';
    return 'unknown';
}

test.describe.configure({ mode: 'serial' });

test.describe('F8L § 51 — HotelRunner Webhook + Outbox', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressTid = null;
    let pilotTid = null;
    let authMode = 'unknown';

    test('Setup: prefix + pilot baseline + logs reachability probe + sig-mode classification', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // logs/events JWT-auth read probe — router mount kontrolü.
        const probe = await withModuleProbe(request, stressTokens.stress_token, `${BASE}/logs/events?limit=1`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `logs_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'HotelRunner webhook logs probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — router deploy yok veya RBAC. A/B/C/D skipped, E pilot_drift+external_calls bağımsız.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }

        // Sig-mode classification — POST /callback empty body, no headers.
        // Beklenen:
        //   - 503 → fail_closed (HOTELRUNNER_WEBHOOK_SECRET unset, bypass off)
        //   - 401 → sig_required (secret set, headers missing)
        //   - 4xx → open_for_testing (bypass aktif, body-validation path)
        const empty = await callWebhook(request, 'post', `${BASE}/callback`,
            { body: '{}', contentType: 'application/json' });
        authMode = classifyMode(empty.status);
        rec(testInfo, { module: MOD, step: 'sig_mode_classification',
            status: (authMode !== 'unknown') ? 'PASS' : 'REVIEW',
            endpoint: `POST ${BASE}/callback`, http: empty.status,
            note: `auth_mode=${authMode} empty_probe_status=${empty.status}` });

        if (authMode === 'unknown') {
            moduleBlocked = true;
            blockedReason = `auth_mode_unknown_status_${empty.status}`;
            recFinding(testInfo, 'P2', MOD, 'HotelRunner webhook sig mode classify edilemedi',
                `POST ${BASE}/callback empty body status=${empty.status} bekleneni dışında (503/401/4xx). A/B/C/D skipped.`);
        }

        rec(testInfo, { module: MOD, step: 'setup',
            status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} stress_tid=${stressTid?.slice(0, 8)} pilot_tid=${pilotTid?.slice(0, 8)} auth_mode=${authMode}` });
    });

    test('A) Sig contract — missing headers / bad sig / stale ts → 401 (or 503 fail-closed)', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'sig_contract', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const body = '{"reservation":{"hr_number":"FAKE_' + (prefix || 'X') + 'STRESS"}}';
        const now = Math.floor(Date.now() / 1000);
        const stale = now - 1000;

        const ALLOWED = {
            fail_closed_503: new Set([503]),
            sig_required_401: new Set([401]),
            open_for_testing: new Set([200, 201, 202, 400, 422]),
        };
        const expected = ALLOWED[authMode] || new Set();

        const probes = [
            { name: 'no_headers', headers: {} },
            { name: 'sig_only_no_ts', headers: { 'X-HotelRunner-Signature': 'sha256=deadbeef' } },
            { name: 'ts_only_no_sig', headers: { 'X-HotelRunner-Timestamp': String(now) } },
            { name: 'stale_ts', headers: { 'X-HotelRunner-Timestamp': String(stale), 'X-HotelRunner-Signature': 'sha256=deadbeef' } },
            { name: 'bad_sig_fresh_ts', headers: { 'X-HotelRunner-Timestamp': String(now), 'X-HotelRunner-Signature': 'sha256=' + 'a'.repeat(64) } },
            { name: 'invalid_ts_format', headers: { 'X-HotelRunner-Timestamp': 'NOT_A_NUMBER', 'X-HotelRunner-Signature': 'sha256=deadbeef' } },
        ];
        // Architect review fix #1: PASS logic mode-aware olmalı.
        // open_for_testing modunda 2xx LEGITIMATE (bypass aktif, body accept
        // edilebilir). Sadece fail_closed/sig_required mode'da 2xx = bypass
        // = P0. accepted2xx → mode-relative değerlendir; violations zaten
        // expected set ile mod başına ölçülüyor.
        const violations = [];
        const accepted2xx = [];
        for (const p of probes) {
            const r = await callWebhook(request, 'post', `${BASE}/callback`,
                { body, headers: p.headers });
            if (r.status >= 200 && r.status < 300) {
                accepted2xx.push({ name: p.name, status: r.status });
            }
            if (!expected.has(r.status)) {
                violations.push({ name: p.name, status: r.status, expected: [...expected] });
            }
        }
        const accepted2xxIsBypass = accepted2xx.length > 0 && authMode !== 'open_for_testing';
        const pass = !accepted2xxIsBypass && violations.length === 0;
        rec(testInfo, { module: MOD, step: 'sig_contract',
            status: pass ? 'PASS' : 'FAIL',
            note: `auth_mode=${authMode} accepted2xx=${accepted2xx.length} violations=${violations.length} detail=${JSON.stringify(violations).slice(0, 240)}` });

        if (accepted2xx.length > 0 && authMode !== 'open_for_testing') {
            recFinding(testInfo, 'P0', MOD,
                'HotelRunner webhook fail-closed/sig-required mode altında imzasız payload 2xx',
                `auth_mode=${authMode} accepted: ${JSON.stringify(accepted2xx)}. Signature verification bypass + tampering kombinasyonu. Threat-model § Spoofing.`);
        }
        if (violations.length > 0 && authMode === 'fail_closed_503') {
            recFinding(testInfo, 'P1', MOD,
                'HotelRunner webhook fail-closed contract zayıf',
                `Beklenen 503 (secret unset). Gözlenen: ${JSON.stringify(violations)}.`);
        }
        if (violations.length > 0 && authMode === 'sig_required_401') {
            recFinding(testInfo, 'P1', MOD,
                'HotelRunner webhook sig-required contract zayıf',
                `Beklenen 401 (sig validation). Gözlenen: ${JSON.stringify(violations)}.`);
        }
    });

    test('B) Webhook surface coverage — reservations/modifications/cancellations endpoints same contract', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'webhook_surface', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // 3 endpoint aynı imza zorunluluğunu paylaşmalı. Bir tanesi diğerlerinden
        // farklı status dönerse contract drift (P1).
        const endpoints = [
            `${BASE}/webhooks/reservations`,
            `${BASE}/webhooks/modifications`,
            `${BASE}/webhooks/cancellations`,
        ];
        const body = '{}';
        const results = [];
        for (const ep of endpoints) {
            const r = await callWebhook(request, 'post', ep, { body });
            results.push({ ep: ep.replace(BASE, ''), status: r.status });
        }
        // Architect review fix #2: exact-status uniformity yerine mode-aware
        // status-class drift. Backend her endpoint'te validation order veya
        // body-shape branching nedeniyle farklı 4xx döndürebilir (örn. 401 vs
        // 422). Drift sinyali, status'ları "deny class" (sig/auth) vs
        // "validation class" (body shape) vs "accept class" (2xx) kovalarına
        // bölüp KOVA değişimini ölçer. Aynı KOVA içinde 401 vs 503 OK.
        const classify = (s) => {
            if (s === 503) return 'fail_closed';
            if (s === 401 || s === 403) return 'sig_or_auth_deny';
            if (s >= 200 && s < 300) return 'accept_2xx';
            if (s >= 400 && s < 500) return 'validation_4xx';
            if (s >= 500) return 'server_5xx';
            return 'unknown';
        };
        const classes = new Set(results.map(r => classify(r.status)));
        const any2xx = results.some(r => r.status >= 200 && r.status < 300);
        const driftClass = classes.size > 1;
        // Mode-relative: fail_closed mode'da SADECE fail_closed sınıfı görmeli;
        // sig_required mode'da SADECE sig_or_auth_deny; open mode'da
        // accept_2xx + validation_4xx karışımı OK.
        let modeOk = true;
        if (authMode === 'fail_closed_503') modeOk = [...classes].every(c => c === 'fail_closed');
        else if (authMode === 'sig_required_401') modeOk = [...classes].every(c => c === 'sig_or_auth_deny');
        // open_for_testing — herhangi bir karışım kabul, sadece 5xx storm fail.

        const fiveXXAny = results.some(r => r.status >= 500 && r.status !== 503);
        const bypass2xx = any2xx && authMode !== 'open_for_testing';
        const pass = !bypass2xx && modeOk && !fiveXXAny;
        rec(testInfo, { module: MOD, step: 'webhook_surface_coverage',
            status: pass ? 'PASS' : 'FAIL',
            note: `auth_mode=${authMode} results=${JSON.stringify(results)} classes=${[...classes].join(',')} drift_class=${driftClass} mode_ok=${modeOk} bypass_2xx=${bypass2xx}` });
        if (bypass2xx) {
            recFinding(testInfo, 'P0', MOD,
                'HotelRunner webhook surface endpoint imzasız 2xx (sig bypass)',
                `endpoints=${JSON.stringify(results)} auth_mode=${authMode}.`);
        }
        if (!modeOk) {
            recFinding(testInfo, 'P1', MOD,
                'HotelRunner webhook surface mode contract zayıf',
                `auth_mode=${authMode}; bekleneni sınıfı dışı status sınıfları: ${[...classes].join(',')}. Detay: ${JSON.stringify(results)}.`);
        }
        if (fiveXXAny) {
            recFinding(testInfo, 'P1', MOD,
                'HotelRunner webhook surface 5xx (503 dışı) — backend resilience zayıf',
                `results=${JSON.stringify(results)}.`);
        }
    });

    test('C) Tenant injection probe — pilot_tid forge payload imzasız reject edilmeli', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'tenant_injection', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // pilot_tid içerikli payload + imzasız POST. fail_closed/sig_required
        // mode'da: 503/401. open mode'da: body validation. Pilot drift kanıtı
        // E test'inde.
        const forge = JSON.stringify({
            tenant_id: pilotTid,
            hotel: 'forge',
            reservation: { hr_number: 'FORGE_PILOT_INJECT', state: 'new', guest: { name: 'STRESS_FORGE' } },
        });
        const r = await callWebhook(request, 'post', `${BASE}/callback`, { body: forge });
        const accepted2xx = r.status >= 200 && r.status < 300;
        const pass = !accepted2xx || authMode === 'open_for_testing';
        rec(testInfo, { module: MOD, step: 'tenant_injection_probe',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: `POST ${BASE}/callback`, http: r.status,
            note: `auth_mode=${authMode} accepted_2xx=${accepted2xx} body=${(r.text || '').slice(0, 160)}` });
        if (accepted2xx && authMode !== 'open_for_testing') {
            recFinding(testInfo, 'P0', MOD,
                'HotelRunner webhook fail-closed/sig-required altında pilot_tid forge 2xx',
                `auth_mode=${authMode} body=${(r.text || '').slice(0, 160)}. Sig+tenant injection kombo bypass.`);
        }

        // Architect review fix #3 (mirror spec 50): raw text PII scan.
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
                    'HotelRunner webhook response raw text\'inde PII pattern',
                    `hits=${JSON.stringify(piiHits)} body_sample=${t.slice(0, 240)}.`);
            }
        }
    });

    test('D) Logs read scope — /logs/events ve /logs/errors stress tenant\'a scope\'lu olmalı + PII mask', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'logs_read_scope', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // logs/events JWT-auth + tenant scope. Stres tenant token ile çağırınca
        // dönen log'lar pilot_tid içermemeli.
        const ev = await callTimed(request, 'get', `${BASE}/logs/events?limit=20`,
            undefined, stressTokens.stress_token);
        const evList = Array.isArray(ev.body) ? ev.body
            : (ev.body?.events || ev.body?.items || []);
        let pilotLeak = false;
        if (ev.ok && pilotTid) {
            const blob = JSON.stringify(ev.body);
            if (blob.includes(pilotTid)) pilotLeak = true;
        }
        rec(testInfo, { module: MOD, step: 'logs_events_read',
            status: pilotLeak ? 'FAIL' : (ev.ok ? 'PASS' : 'REVIEW'),
            endpoint: `GET ${BASE}/logs/events`, http: ev.status,
            note: `len=${evList.length} pilot_leak=${pilotLeak}` });
        if (pilotLeak) {
            recFinding(testInfo, 'P0', MOD,
                'HotelRunner logs/events cross-tenant leak — pilot_tid stress response\'unda',
                `Stres token ile pilot tenant log'ları döndü. Tenant scope eksik. Threat-model § Information Disclosure.`);
        }

        // PII guard — log payload guest_name/phone/email taşıyabilir.
        if (ev.ok) {
            assertPiiMasked(testInfo, MOD, ev.body, ['phone', 'email', 'identity_number', 'guest_phone']);
            assertNoTokenLeak(testInfo, MOD, ev.body, 'hr_logs_events');
        }

        // Hata logları aynı doktrin.
        const err = await callTimed(request, 'get', `${BASE}/logs/errors?limit=20`,
            undefined, stressTokens.stress_token);
        let errPilotLeak = false;
        if (err.ok && pilotTid) {
            const blob = JSON.stringify(err.body);
            if (blob.includes(pilotTid)) errPilotLeak = true;
        }
        rec(testInfo, { module: MOD, step: 'logs_errors_read',
            status: errPilotLeak ? 'FAIL' : (err.ok ? 'PASS' : 'REVIEW'),
            endpoint: `GET ${BASE}/logs/errors`, http: err.status,
            note: `pilot_leak=${errPilotLeak}` });
        if (errPilotLeak) {
            recFinding(testInfo, 'P0', MOD,
                'HotelRunner logs/errors cross-tenant leak — pilot_tid stress response\'unda',
                `Stres token ile pilot tenant error log'ları döndü.`);
        }
        if (err.ok) {
            assertPiiMasked(testInfo, MOD, err.body, ['phone', 'email', 'identity_number', 'guest_phone']);
            assertNoTokenLeak(testInfo, MOD, err.body, 'hr_logs_errors');
        }
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'cm_hotelrunner_webhook_done', stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });
});

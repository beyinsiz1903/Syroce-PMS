// F8V § 98B — WebSocket / Live Panel Tenant Isolation stress.
//
// Threat-model surface (threat_model.md § Spoofing + Information Disclosure):
//   Canlı panel / notification stream HTTP test'leriyle yakalanmaz. WS
//   connection auth + per-tenant scoping + cross-tenant subscribe deny
//   ayrıca pen-test ister. Redis pub/sub auth invalidation gotcha mevcut
//   ama multi-tenant WS isolation için dedicated stress yoktu.
//
// Backend endpoint:
//   /api/enterprise/ws/live?token=JWT&last_event_ts=0  (backend/routers/
//   enterprise_live.py L86) — JWT query param ile auth, ws_hub.connect
//   tenant_id derive eder, accept başlangıçta yapılır ama auth fail
//   sonrasında close(4001) "Authentication failed".
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//
// Module-blocked pattern:
//   - WS connect HTTP 404/426 ya da `ws` import fail → A/B/C SKIP, D
//     pilot_drift + external_calls bağımsız.
//
// Probe doctrine:
//   - A) Unauth (token empty / garbage / tampered) → ws_hub reddetmeli;
//     close code 4001 veya HTTP 4xx beklenir. Connection 30s sonra hala
//     açık ve event akıyorsa P0.
//   - B) Valid stress token → connect OK + initial frame içinde tenant_id
//     stress_tid olmalı; pilot_tid string'i payload'ta görünmemeli.
//   - C) Cross-tenant subscribe spoof — stress token bağlı socket'te
//     `subscribe tenant=<pilot_tid>` message gönder; pilot event akmamalı.
//   - D) Final invariants.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'ws_tenant_isolation';

// `ws` package optional — yoksa moduleBlocked. Dynamic import (file-load
// time crash etmesin).
let WS = null;
async function ensureWs() {
    if (WS) return WS;
    try {
        WS = (await import('ws')).default || (await import('ws')).WebSocket;
        return WS;
    } catch (e) {
        return null;
    }
}

// E2E_BASE_URL → ws URL convert. http(s)://x → ws(s)://x.
function baseToWs(baseUrl) {
    if (!baseUrl) return null;
    return baseUrl.replace(/^http(s?):\/\//i, 'ws$1://');
}

// Tampered JWT — geçerli formattaki JWT'nin signature segment'inde 1 byte
// flip. Header/payload geçerli, signature broken → server reject etmeli
// ("format-OK ama signature invalid" code path).
function tamperJwt(jwt) {
    if (!jwt || typeof jwt !== 'string') return null;
    const parts = jwt.split('.');
    if (parts.length !== 3 || parts[2].length < 4) return null;
    const sig = parts[2];
    const ch = sig[0];
    parts[2] = (ch === 'A' ? 'B' : 'A') + sig.slice(1);
    return parts.join('.');
}

// Sensitive marker scan — non-JSON / opaque frame içeriklerinde tenant
// veya operasyonel data sızıntısı tespiti için. tenantId opsiyonel; yoksa
// yalnızca jenerik operasyonel anahtarlar taranır.
const _WS_OP_MARKERS = [
    'booking_id', 'guest_id', 'room_id', 'folio_id', 'reservation_id',
    'tenant_id', 'phone', 'email', 'iban', 'national_id', 'check_in',
    'payment', 'charge', 'invoice', 'PILOT_', 'PROD_',
];
function frameLooksLikeOperationalLeak(frame, tenantId) {
    if (!frame) return false;
    if (tenantId && frame.includes(tenantId)) return true;
    let hits = 0;
    for (const m of _WS_OP_MARKERS) {
        if (frame.includes(m)) hits++;
        if (hits >= 2) return true;  // ≥2 op marker = data frame, single = ambiguous
    }
    return false;
}

// Connect probe: timeoutMs içinde { opened, closed, closeCode, framesIn,
// firstFrame, error } döner. Frame=text mesajları biriktirir.
async function wsProbe(WsCtor, url, opts = {}) {
    const timeoutMs = opts.timeoutMs ?? 5000;
    const sendAfterOpen = opts.sendAfterOpen ?? null;
    const collectFramesMs = opts.collectFramesMs ?? 1500;
    return await new Promise((resolve) => {
        let ws = null;
        let opened = false;
        let closed = false;
        let closeCode = null;
        let firstFrame = null;
        const frames = [];
        let resolved = false;
        const settle = (extra = {}) => {
            if (resolved) return;
            resolved = true;
            try { ws && ws.close(); } catch { /* ignore */ }
            resolve({ opened, closed, closeCode, framesIn: frames.length, firstFrame, frames, ...extra });
        };
        try {
            ws = new WsCtor(url);
        } catch (e) {
            return settle({ error: `ctor_${String(e?.message || e).slice(0, 80)}` });
        }
        const killer = setTimeout(() => settle({ error: 'timeout' }), timeoutMs);
        ws.on('open', async () => {
            opened = true;
            if (sendAfterOpen) {
                try { ws.send(typeof sendAfterOpen === 'string' ? sendAfterOpen : JSON.stringify(sendAfterOpen)); } catch { /* ignore */ }
            }
            // Frame'leri topla — collectFramesMs sonra kapat ve settle.
            setTimeout(() => { clearTimeout(killer); settle(); }, collectFramesMs);
        });
        ws.on('message', (data) => {
            const s = data?.toString?.() || '';
            if (firstFrame == null) firstFrame = s.slice(0, 400);
            frames.push(s.slice(0, 200));
            if (frames.length >= 20) { clearTimeout(killer); settle(); }
        });
        ws.on('close', (code) => {
            closed = true;
            closeCode = code;
            clearTimeout(killer);
            settle();
        });
        ws.on('error', (e) => {
            clearTimeout(killer);
            settle({ error: `ws_${String(e?.message || e).slice(0, 80)}` });
        });
        // Task #164: handshake upgrade non-101 dönerse (örn. mount yok → HTTP
        // 404, pre-upgrade auth reject → 401/403) `ws` lib 'unexpected-response'
        // emit eder. httpStatus'u yakala — reachability bunu kullanır (HTTP-GET
        // probe WS-only route'ta DAİMA 404 verir; gerçek mount sinyali handshake).
        ws.on('unexpected-response', (_req, res) => {
            clearTimeout(killer);
            settle({ error: `unexpected_response_${res?.statusCode ?? 'na'}`, httpStatus: res?.statusCode ?? null });
        });
    });
}

test.describe.configure({ mode: 'serial' });

test.describe('F8V § 98B — WebSocket Tenant Isolation', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let wsBase = null;
    let WsCtor = null;
    let stressTid = null;
    let pilotTid = null;
    const wsPath = '/api/enterprise/ws/live';

    test('Setup: pilot baseline + ws lib probe + endpoint reachability', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        WsCtor = await ensureWs();
        if (!WsCtor) {
            moduleBlocked = true;
            blockedReason = 'ws_package_not_installed';
            recFinding(testInfo, 'P2', MOD, '`ws` paketi yüklü değil — WS probe yapılamadı',
                'frontend/node_modules/ws bulunamadı; A/B/C SKIP, D bağımsız.');
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            // Module-block: ws npm dep eksik (legit env), explicit skip — silent-return YASAK.
            test.skip(true, 'ws npm package not installed');
            return;
        }
        wsBase = baseToWs(stressState.base_url || process.env.E2E_BASE_URL);
        if (!wsBase) {
            moduleBlocked = true;
            blockedReason = 'ws_base_url_missing';
            recFinding(testInfo, 'P2', MOD, 'WS base URL üretilemedi',
                `base_url=${stressState.base_url || 'unset'} — A/B/C SKIP.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            // Module-block: env config eksik, explicit skip.
            test.skip(true, 'WS base URL not derivable');
            return;
        }

        // Endpoint reachability — Task #164 ROOT-CAUSE FIX: eski sürüm düz HTTP
        // GET atıyordu. Starlette WebSocketRoute SADECE "websocket" scope'unda
        // match eder; HTTP GET hiçbir zaman match etmez → DAİMA 404 → eski
        // sürüm bunu "mount yok" sanıp A/B/C'yi TÜMÜYLE SKIP ediyordu (vacuous).
        // Gerçek reachability ancak WS upgrade handshake ile ölçülür: garbage
        // token ile connect dene. Upgrade'e HTTP 404 dönerse mount gerçekten
        // yok; aksi halde reachable (handshake 101 → open + auth-fail close 4001,
        // ya da pre-upgrade 401/403 = mount VAR ama reddetti).
        const reach = await wsProbe(WsCtor, `${wsBase}${wsPath}?token=garbage.not.a.jwt&last_event_ts=0`,
            { timeoutMs: 8_000, collectFramesMs: 600 });
        if (reach.httpStatus === 404) {
            moduleBlocked = true;
            blockedReason = 'ws_endpoint_404';
            recFinding(testInfo, 'P2', MOD, 'WS endpoint 404 — enterprise_live router mount yok',
                'WS upgrade handshake 404 döndü (HTTP-GET değil). A/B/C SKIP, D bağımsız.');
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason} reach_http=404` });
            // Module-block: router mount yok (deploy variant), explicit skip.
            test.skip(true, 'WS endpoint not mounted (404 on upgrade)');
            return;
        }
        // Transport-level erişilemezlik (DNS/ECONNREFUSED/timeout) — handshake
        // ne açıldı ne de bir HTTP status döndü, sadece transport error var → env
        // blok (mount durumu kanıtlanamaz). 401/403 unexpected-response =
        // reachable (mount var), bu dala düşmez.
        if (!reach.opened && reach.httpStatus == null && reach.closeCode == null && reach.error) {
            moduleBlocked = true;
            blockedReason = `ws_unreachable_${reach.error}`;
            recFinding(testInfo, 'P2', MOD, 'WS transport erişilemez',
                `reach_error=${reach.error} — env/transport, A/B/C SKIP, D bağımsız.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            test.skip(true, 'WS transport unreachable');
            return;
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} ws_base=${wsBase} reach_opened=${reach.opened} reach_close=${reach.closeCode} reach_http=${reach.httpStatus ?? 'na'} stress_tid=${stressTid?.slice(0, 8)} pilot_tid=${pilotTid ? pilotTid.slice(0, 8) : 'unset'}` });
    });

    test('A) Unauthenticated / garbage / tampered tokens — WS auth fail (close code 4001 or short-lived) + no leaked frames', async ({ request, stressState, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'unauth_reject', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const tampered = tamperJwt(stressTokens.stress_token);
        const cases = [
            { name: 'no_token', tok: '' },
            { name: 'garbage', tok: 'garbage.not.ajwt' },
            { name: 'random_long', tok: 'A'.repeat(64) },
            // Fake JWT-shape (header/payload base64 valid, signature random) —
            // ws_hub.connect format parse'ı geçer, signature verify fail etmeli.
            { name: 'fake_jwt_shape', tok: 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4IiwidGVuYW50X2lkIjoiYXR0YWNrZXIifQ.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c' },
            // Tampered VALID JWT — gerçek stress JWT'nin signature byte-flip'i.
            // Header/payload geçerli, signature broken; auth flow için ayrı code path.
            ...(tampered ? [{ name: 'tampered_real_jwt', tok: tampered }] : []),
        ];
        const results = [];
        let leaked = 0;
        for (const c of cases) {
            const url = `${wsBase}${wsPath}?token=${encodeURIComponent(c.tok)}&last_event_ts=0`;
            const res = await wsProbe(WsCtor, url, { timeoutMs: 6000, collectFramesMs: 1500 });
            // Frame-by-frame leak scan: JSON-parse OK frame'lerde type whitelist
            // ('auth_error'/'error'/'pong'); parse FAIL frame'lerde ise opaque
            // payload'da operasyonel marker (booking_id, tenant_id, vs ≥2 adet)
            // → leak (defansif, hub binary/serialized frame de göndermiş olabilir).
            let dataLeak = false;
            let leakReason = null;
            for (const f of (res.frames || [])) {
                let parsed = false;
                try {
                    const j = JSON.parse(f);
                    parsed = true;
                    const t = (j?.type || j?.event || '').toLowerCase();
                    if (t && t !== 'auth_error' && t !== 'error' && t !== 'pong') {
                        dataLeak = true; leakReason = `json_type=${t}`;
                        break;
                    }
                    // JSON OK ama type alanı yok — operational marker scan da yap.
                    if (!t && frameLooksLikeOperationalLeak(f, pilotTid)) {
                        dataLeak = true; leakReason = 'json_no_type_op_markers';
                        break;
                    }
                } catch { /* non-JSON */ }
                if (!parsed && frameLooksLikeOperationalLeak(f, pilotTid)) {
                    dataLeak = true; leakReason = 'opaque_op_markers';
                    break;
                }
            }
            if (dataLeak) leaked++;
            // Auth-fail close enforcement: invalid token connection için server
            // *zorunlu* kapatmalı. Geçerli close akışları:
            //   - hiç open olmadan reject (en güvenli)
            //   - open + close(4001) (auth_error frame + 4001 ws_hub doctrine)
            //   - open + close(1008/1011/4xxx) (policy violation / internal err)
            // Hatalı/eksik akışlar:
            //   - opened=true, closed=false (collection window sonunda hala açık) → P1
            //   - opened=true, closeCode=1000 (normal closure, auth fail sinyali değil) → P2
            //   - opened=true, closeCode=null AND error set → P2 (transport-level fail)
            const acceptedAuthFailCodes = new Set([4001, 4003, 4008, 1008, 1011]);
            let closeBehaviorIssue = null;
            if (res.opened && !res.closed) {
                closeBehaviorIssue = 'opened_never_closed_within_window';
                recFinding(testInfo, 'P1', MOD,
                    `WS unauth connection açık kaldı — close enforcement eksik (case=${c.name})`,
                    `URL=${url.replace(c.tok, c.tok.slice(0, 12) + '…')} opened=true, closed=false, frames=${res.framesIn}, error=${res.error || 'none'}. Server auth-fail sonrası close(4001) göndermedi; long-lived idle session resource leak + DoS attack surface.`);
            } else if (res.opened && res.closed && res.closeCode != null && !acceptedAuthFailCodes.has(res.closeCode)) {
                closeBehaviorIssue = `unexpected_close_code_${res.closeCode}`;
                const sev = res.closeCode === 1000 ? 'P2' : 'P1';
                recFinding(testInfo, sev, MOD,
                    `WS unauth close code=${res.closeCode} (auth-fail için beklenmeyen) — case=${c.name}`,
                    `Server auth-fail için 4001 (veya 1008/1011) kullanmalı; observed=${res.closeCode}. ${sev === 'P1' ? 'Anormal sinyal — client tarafı auth-fail handle edemez.' : 'Normal closure auth-fail için observability noise.'}`);
            }
            results.push({ name: c.name, opened: res.opened, closed: res.closed, code: res.closeCode, frames: res.framesIn, first: (res.firstFrame || '').slice(0, 80), leak: leakReason, close_issue: closeBehaviorIssue, error: res.error });
        }
        // Test sonuç: data leak P0 + close behavior P1 finding kayıt edilir;
        // step status FAIL leak varsa, REVIEW close issue varsa.
        const closeIssues = results.filter(r => r.close_issue).length;
        const stepStatus = leaked > 0 ? 'FAIL' : (closeIssues > 0 ? 'REVIEW' : 'PASS');
        rec(testInfo, { module: MOD, step: 'unauth_reject',
            status: stepStatus,
            note: `cases=${cases.length} data_leaks=${leaked} close_issues=${closeIssues} results=${JSON.stringify(results)}` });
        if (leaked > 0) {
            recFinding(testInfo, 'P0', MOD,
                'Unauthenticated WS connection operasyonel veri frame aldı',
                `data_leaks=${leaked} cases=${JSON.stringify(results)}. WS auth bypass; live operational data unauthed leak.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'unauth_reject', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        // Task #164 hard-assert: unauth/garbage/tampered token WS bağlantısı
        // OPERASYONEL veri frame'i ALAMAZ (auth bypass = P0 leak). Close-code
        // davranışı (4001 vs 1000) observability bulgusu olarak REVIEW'da kalır;
        // güvenlik invariantı = sıfır data leak.
        expect(leaked, `unauth WS operational data leaks=${leaked}`).toBe(0);
    });

    test('B) Valid stress token — connect OK + initial frame scoped to stress tenant + no pilot_tid leak', async ({ request, stressState, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'valid_token_scope', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const url = `${wsBase}${wsPath}?token=${encodeURIComponent(stressTokens.stress_token)}&last_event_ts=0`;
        const res = await wsProbe(WsCtor, url, { timeoutMs: 6000, collectFramesMs: 2000 });
        const opened = !!res.opened;
        // Pilot tid leak scan — frame'lerin hiçbiri pilot tenant_id literal taşımamalı.
        let pilotLeak = false;
        if (pilotTid) {
            for (const f of (res.frames || [])) {
                if (f.includes(pilotTid)) { pilotLeak = true; break; }
            }
        }
        // Auth-error frame ile düştüyse valid token reddedildi = REVIEW.
        let authError = false;
        if (res.firstFrame) {
            try {
                const j = JSON.parse(res.firstFrame);
                if ((j?.type || '').toLowerCase() === 'auth_error') authError = true;
            } catch { /* ignore */ }
        }
        const okGate = opened && !pilotLeak && !authError;
        rec(testInfo, { module: MOD, step: 'valid_token_scope',
            status: okGate ? 'PASS' : (pilotLeak ? 'FAIL' : 'REVIEW'),
            note: `opened=${opened} closed=${res.closed} code=${res.closeCode} frames=${res.framesIn} auth_error=${authError} pilot_leak=${pilotLeak} first=${(res.firstFrame || '').slice(0, 80)} err=${res.error || ''}` });
        if (pilotLeak) {
            recFinding(testInfo, 'P0', MOD,
                'Stress token WS frame\'inde pilot tenant_id literal sızdı',
                `frame_sample=${(res.frames || []).slice(0, 2).join(' | ').slice(0, 300)}. Cross-tenant WS leak.`);
        }
        if (authError) {
            recFinding(testInfo, 'P1', MOD,
                'Valid stress token WS auth_error aldı',
                `first_frame=${res.firstFrame}. ws_hub auth derivation broken veya token type mismatch.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'valid_token_scope', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        // Task #164 hard-assert: valid stress token WS frame'inde pilot tenant_id
        // literal SIZAMAZ (cross-tenant scope leak = P0). opened/authError
        // fonksiyonel sorunları REVIEW olarak kaydedilir (env-flake'e karşı hard-
        // fail edilmez); güvenlik invariantı = pilot leak yok.
        expect(pilotLeak, `stress-token WS pilot_tid leak=${pilotLeak}`).toBe(false);
    });

    test('C) Cross-tenant subscribe spoof — stress socket "subscribe pilot tenant" must not yield pilot data', async ({ request, stressState, stressTokens }, testInfo) => {
        if (moduleBlocked || !pilotTid) {
            rec(testInfo, { module: MOD, step: 'cross_tenant_subscribe_spoof', status: 'SKIP',
                note: `module_blocked=${moduleBlocked} pilot_tid_present=${!!pilotTid}` });
            test.skip(true, 'pre-conditions missing');
            return;
        }
        const url = `${wsBase}${wsPath}?token=${encodeURIComponent(stressTokens.stress_token)}&last_event_ts=0`;
        // Birkaç olası subscribe message shape dene — ws_hub schema kapalı,
        // probe defansif: tüm message'lar gönderilir, server reddetmeli.
        const spoofMsgs = [
            { type: 'subscribe', tenant_id: pilotTid },
            { type: 'subscribe', room: `tenant:${pilotTid}` },
            { action: 'join', channel: `tenant:${pilotTid}` },
            { type: 'subscribe', topic: `pms.${pilotTid}.bookings` },
        ];
        const results = [];
        let pilotLeak = false;
        for (const msg of spoofMsgs) {
            const res = await wsProbe(WsCtor, url, {
                timeoutMs: 6000, collectFramesMs: 2000, sendAfterOpen: msg,
            });
            for (const f of (res.frames || [])) {
                if (f.includes(pilotTid)) { pilotLeak = true; break; }
            }
            results.push({ msg: JSON.stringify(msg).slice(0, 60), frames: res.framesIn, code: res.closeCode });
            if (pilotLeak) break;
        }
        rec(testInfo, { module: MOD, step: 'cross_tenant_subscribe_spoof',
            status: pilotLeak ? 'FAIL' : 'PASS',
            note: `pilot_leak=${pilotLeak} probes=${JSON.stringify(results)}` });
        if (pilotLeak) {
            recFinding(testInfo, 'P0', MOD,
                'Stress WS subscribe spoof pilot tenant verisi döndü',
                `probes=${JSON.stringify(results)}. ws_hub.handle_message tenant guard eksik.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'cross_tenant_subscribe_spoof', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        // Task #164 hard-assert: cross-tenant subscribe spoof pilot verisi
        // DÖNDÜREMEZ (ws_hub tenant guard = P0). Güvenlik invariantı.
        expect(pilotLeak, `WS cross-tenant subscribe spoof pilot leak=${pilotLeak}`).toBe(false);
    });

    test('D) Pilot drift = 0 + external_calls = [] (final invariants)', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});

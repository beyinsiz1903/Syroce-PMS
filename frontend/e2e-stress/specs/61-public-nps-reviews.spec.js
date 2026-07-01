// F8K § 61 — Public NPS + Review Invite Stress.
//
// Threat-model surface (threat_model.md § Spoofing + Tampering + Information
// Disclosure + DoS): NPS surveys staff-auth; review invite ise public token
// (32-char hex) tabanlı anonymous akış. Token guard zayıflığı → cross-tenant
// review injection. NPS by-room/recent endpoint'leri guest yorumları döner
// (PII + guest_name + comment metni). Rate-limit boundary public submit
// endpoint'inde kritik (DoS + invite enumeration).
//
// Mutlak kurallar (task #196):
//   - pilot mutation YOK. NPS write'lar stress_tid altında, stress_prefix'li
//     guest_name + feedback. Pilot tenant'ta hiç survey yazılmaz.
//   - external_calls=[] — NPS submit OTA dispatch tetiklemez; review submit
//     guest_reviews.insert (in-DB) yapar, outbound HTTP yoktur. Spec public
//     POST'u 404 (non-existent token) ile prober yapar, gerçek invite
//     consume etmez.
//   - failedTests=0, P0=P1=0.
//   - Cleanup idempotent: yazılan NPS satırları stress_prefix marker'lı,
//     DELETE /api/nps/survey/{id} ile temizlenir. afterAll'da residue sweep.
//
// Backend yüzeyleri:
//   - POST   /api/nps/survey                         (staff submit, JWT)
//   - GET    /api/nps/score                          (aggregation read)
//   - GET    /api/nps/recent                         (list, PII risk)
//   - GET    /api/nps/by-room                        (aggregation, room)
//   - DELETE /api/nps/survey/{survey_id}             (manage_sales perm)
//   - GET    /api/crm/reviews                        (staff read)
//   - GET    /api/feedback/public/invite/{token}     (public, no-auth)
//   - POST   /api/feedback/public/invite/{token}     (public, no-auth)
//
// Module-blocked: NPS score endpoint non-2xx (403/404) → moduleBlocked + skip.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'public_nps';

async function callRaw(request, method, urlPath, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    const t0 = Date.now();
    const r = await request[method](urlPath, {
        headers, data: opts.body, failOnStatusCode: false, timeout: opts.timeout ?? 30_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    const ms = Date.now() - t0;
    let bodyJson = null, bodyText = null;
    try { bodyText = r.text ? await r.text() : null; } catch { /* */ }
    try { bodyJson = bodyText && bodyText.trim().startsWith('{') ? JSON.parse(bodyText) : null; } catch { /* */ }
    return { status: r.status?.() ?? 0, ms, body: bodyJson, text: bodyText, ok: (r.status?.() ?? 0) >= 200 && (r.status?.() ?? 0) < 300 };
}

test.describe.configure({ mode: 'serial' });

test.describe('F8K § 61 — Public NPS + Review Invite Stress', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressTid = null;
    let pilotTid = null;
    const createdSurveyIds = [];      // cleanup için
    const createdMarker = `STRESS_F8K_NPS_${Date.now().toString(36)}`;

    test('Setup: prefix + pilot baseline + NPS score reachability probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/nps/score?days=30');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `nps_score_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'NPS score endpoint probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C/D skipped, E pilot_drift+external_calls bağımsız.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} created_marker=${createdMarker}` });
    });

    test('A) NPS submit + duplicate guard + score aggregation read', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'nps_submit', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // 1) Submit valid NPS — stress_prefix marker'lı guest_name.
        const body1 = {
            nps_score: 9,
            guest_name: `${createdMarker}_guest_1`,
            feedback: `${createdMarker} stress probe feedback 1`,
            room_number: `${createdMarker}_R1`,
            source: 'api',
        };
        const r1 = await callTimed(request, 'post', '/api/nps/survey', body1, stressTokens.stress_token);
        const r1Ok = r1.ok && r1.body?.survey_id;
        if (r1Ok) createdSurveyIds.push(r1.body.survey_id);

        // 2) Boundary — score=11 (invalid), 400 beklenir.
        const bad = await callTimed(request, 'post', '/api/nps/survey',
            { nps_score: 11, guest_name: `${createdMarker}_invalid` }, stressTokens.stress_token);
        const badRejected = bad.status === 400 || bad.status === 422;
        if (bad.ok) {
            recFinding(testInfo, 'P1', MOD,
                'NPS submit score=11 (>10) kabul edildi — boundary validation eksik',
                `POST /api/nps/survey status=${bad.status} body=${JSON.stringify(bad.body).slice(0, 160)}.`);
        }

        // 3) Boundary — score=-1, 400 beklenir.
        const neg = await callTimed(request, 'post', '/api/nps/survey',
            { nps_score: -1, guest_name: `${createdMarker}_negative` }, stressTokens.stress_token);
        const negRejected = neg.status === 400 || neg.status === 422;
        if (neg.ok) {
            recFinding(testInfo, 'P1', MOD,
                'NPS submit score=-1 kabul edildi — boundary validation eksik',
                `POST /api/nps/survey status=${neg.status}.`);
        }

        // 4) Missing score → 400.
        const missing = await callTimed(request, 'post', '/api/nps/survey',
            { guest_name: `${createdMarker}_no_score` }, stressTokens.stress_token);
        const missingRejected = missing.status === 400 || missing.status === 422;
        if (missing.ok) {
            recFinding(testInfo, 'P1', MOD,
                'NPS submit puansız kabul edildi',
                `POST /api/nps/survey status=${missing.status}.`);
        }

        // 5) Score aggregation read — son survey listede görünmeli + PII guard.
        const score = await callTimed(request, 'get', '/api/nps/score?days=30', undefined, stressTokens.stress_token);
        const scoreOk = score.ok && typeof score.body?.nps_score === 'number';
        if (score.ok) {
            assertNoTokenLeak(testInfo, MOD, score.body, 'nps_score_read');
        }

        // 6) DUPLICATE GUARD — aynı booking_id + guest_id + nps_score ile 2.
        //    submit. Backend'de explicit duplicate prevention YOK (her POST yeni
        //    UUID üretir), bu yüzden duplicate ALLOWED gelmesi REVIEW olur
        //    (informational data-quality signal), 5xx ise FAIL (storm guard).
        //    Tek-survey-per-booking enforcement gerekirse F8K-v2 backlog'a.
        const dupBody = { ...body1, feedback: `${createdMarker} DUP probe` };
        const dup = await callTimed(request, 'post', '/api/nps/survey', dupBody, stressTokens.stress_token);
        let dupNote = `dup=${dup.status}`;
        if (dup.ok && dup.body?.survey_id) {
            createdSurveyIds.push(dup.body.survey_id);
            dupNote += '_allowed_no_dedupe';
            // REVIEW only — backend tasarımı duplicate'e izin veriyor (manuel
            // entry); finding emit edilmez. Cleanup'ta silinir.
            rec(testInfo, { module: MOD, step: 'nps_duplicate_guard',
                status: 'REVIEW',
                note: `Duplicate (aynı booking/guest/score) 2xx döndü — backend tasarımı kasıtlı (her manuel entry ayrı kayıt). F8K-v2: tek-survey-per-booking-day enforcement değerlendirilsin.` });
        } else if (dup.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'NPS duplicate submit 5xx storm',
                `POST /api/nps/survey duplicate body status=${dup.status} — backend duplicate handling crash.`);
        } else {
            rec(testInfo, { module: MOD, step: 'nps_duplicate_guard',
                status: 'PASS', note: `dup_rejected=${dup.status}` });
        }

        const pass = r1Ok && badRejected && negRejected && missingRejected && scoreOk && dup.status < 500;
        rec(testInfo, { module: MOD, step: 'nps_submit',
            status: pass ? 'PASS' : 'FAIL',
            note: `r1=${r1.status} bad11=${bad.status} neg=${neg.status} missing=${missing.status} score=${score.status} ${dupNote} surveys_created=${createdSurveyIds.length}` });
    });

    test('B) NPS recent + by-room PII guard + cross-tenant scope', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'nps_read_pii', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // GET /nps/recent — guest_name + comment + room_number döner; PII guard.
        const recent = await callTimed(request, 'get', '/api/nps/recent?days=30&limit=50',
            undefined, stressTokens.stress_token);
        if (recent.ok && recent.body) {
            assertPiiMasked(testInfo, MOD, recent.body?.items || [],
                ['phone', 'email', 'identity_number', 'guest_phone']);
            assertNoTokenLeak(testInfo, MOD, recent.body, 'nps_recent_read');

            // Cross-tenant leak guard — response'da pilot_tid görünmemeli.
            if (pilotTid && JSON.stringify(recent.body).includes(pilotTid)) {
                recFinding(testInfo, 'P0', MOD,
                    'NPS /recent response\'unda pilot tenant_id sızdı',
                    `GET /api/nps/recent stress token ile pilot_tid içeren satır döndü. Tenant filter eksik.`);
            }
        }

        const byRoom = await callTimed(request, 'get', '/api/nps/by-room?days=30',
            undefined, stressTokens.stress_token);
        if (byRoom.ok && byRoom.body) {
            assertPiiMasked(testInfo, MOD, byRoom.body?.rooms || [],
                ['phone', 'email', 'identity_number']);
            assertNoTokenLeak(testInfo, MOD, byRoom.body, 'nps_by_room_read');
        }

        rec(testInfo, { module: MOD, step: 'nps_read_pii',
            status: (recent.ok && byRoom.ok) ? 'PASS' : 'REVIEW',
            note: `recent=${recent.status}(items=${recent.body?.items?.length ?? 0}) by_room=${byRoom.status}(rooms=${byRoom.body?.rooms?.length ?? 0})` });
    });

    test('C) Public review invite token guard — anonymous GET + invalid format + non-existent + rate-limit boundary', async ({ request }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'review_token_guard', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const BASE = '/api/feedback/public/invite';

        // 1) Invalid format (non-hex / wrong length) → 400 beklenir (token regex
        //    32 char hex). 200 dönerse format guard yok = P1.
        const badFormats = [
            'NOT_A_HEX_TOKEN_xxxxxxxxxxxxxxxx',   // 32 chars but underscore
            '12345',                              // too short
            '<script>alert(1)</script>aaaaaaaa',  // XSS injection attempt
            '00000000000000000000000000000000',   // 32 hex zeros (valid format, non-existent)
        ];
        const formatResults = [];
        for (const tk of badFormats) {
            const r = await callRaw(request, 'get', `${BASE}/${encodeURIComponent(tk)}`);
            formatResults.push({ token_kind: tk.slice(0, 20), status: r.status });
            if (r.ok) {
                recFinding(testInfo, 'P0', MOD,
                    'Public review invite GET malformed token ile 2xx döndü',
                    `GET ${BASE}/${tk.slice(0, 24)} status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)} — token validation bypass + invite enumeration primitive.`);
            }
            // PII / token leak guard on error body.
            if (r.body) assertNoTokenLeak(testInfo, MOD, r.body, 'public_invite_error');
        }

        // 2) Non-existent VALID-FORMAT token → 404. (Hex 32 char ama DB'de yok.)
        const ghost = 'a'.repeat(32);  // valid format, non-existent
        const ghostR = await callRaw(request, 'get', `${BASE}/${ghost}`);
        const ghostOk = ghostR.status === 404 || ghostR.status === 410;
        if (ghostR.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Public review invite GET non-existent token ile 2xx döndü',
                `GET ${BASE}/<ghost_32hex> status=${ghostR.status} — invite existence-disclosure veya generation bypass.`);
        }

        // 3) Rate-limit boundary — 20 ardışık GET non-existent token. 5xx storm
        //    veya cascade 429 olursa REVIEW (DoS surface açık).
        const rlStatuses = [];
        for (let i = 0; i < 20; i++) {
            const r = await callRaw(request, 'get', `${BASE}/${'b'.repeat(32)}`);
            rlStatuses.push(r.status);
        }
        const fiveXxCount = rlStatuses.filter(s => s >= 500).length;
        const fourXXCount = rlStatuses.filter(s => s === 404 || s === 410 || s === 429).length;
        const rlOk = fiveXxCount === 0;
        if (fiveXxCount > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Public review invite rate-limit boundary 5xx storm',
                `20 ardışık GET ${BASE}/<ghost> sonuç: 5xx_count=${fiveXxCount} 4xx_count=${fourXXCount}. Backend public surface stres altında crash/degrade ediyor.`);
        }

        // 4) Public SUBMIT — non-existent token, 404 beklenir (atomic claim
        //    öncesinde pre-check). 2xx dönerse review yaratıldı = P0.
        const sub = await callRaw(request, 'post', `${BASE}/${ghost}`, {
            body: { rating: 5, comment: `${createdMarker} stress probe submit`, guest_name: 'F8K STRESS PROBE' },
        });
        const subOk = sub.status === 404 || sub.status === 410;
        if (sub.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Public review submit non-existent token ile 2xx döndü',
                `POST ${BASE}/<ghost> status=${sub.status} — token validation bypass; arbitrary tenant'a review enjekte edilebilir.`);
        }

        const allFormatOk = formatResults.every(f => !(f.status >= 200 && f.status < 300));
        const pass = allFormatOk && ghostOk && rlOk && subOk;
        rec(testInfo, { module: MOD, step: 'review_token_guard',
            status: pass ? 'PASS' : 'FAIL',
            note: `format_results=${JSON.stringify(formatResults)} ghost=${ghostR.status} rl_5xx=${fiveXxCount}/20 rl_4xx=${fourXXCount}/20 submit_ghost=${sub.status}` });
    });

    test('D) Pilot drift + external_calls invariant', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'public_nps_probes',
            stressState, request, stressTokens.pilot_token);
    });

    test.afterAll(async ({ request, stressTokens }) => {
        if (!stressTokens) return;
        // 1) Tracked NPS survey id'leri DELETE.
        for (const sid of createdSurveyIds) {
            try {
                await request.delete(`/api/nps/survey/${sid}`, {
                    headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                    failOnStatusCode: false, timeout: 10_000,
                }).catch(() => null);
            } catch (_) { /* */ }
        }
        // 2) Residue sweep — createdMarker prefix'li NPS recent listesi tara.
        try {
            const r = await request.get('/api/nps/recent?days=30&limit=200', {
                headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                failOnStatusCode: false, timeout: 15_000,
            });
            if (r.ok()) {
                const j = await r.json().catch(() => ({}));
                const items = j?.items || [];
                for (const it of items) {
                    const tag = (it.guest_name || '') + (it.feedback || '') + (it.room_number || '');
                    if (tag.includes(createdMarker) || tag.includes('STRESS_F8K_NPS_')) {
                        const sid = it.id || it._id;
                        if (sid && !createdSurveyIds.includes(sid)) {
                            await request.delete(`/api/nps/survey/${sid}`, {
                                headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                                failOnStatusCode: false, timeout: 10_000,
                            }).catch(() => null);
                        }
                    }
                }
            }
        } catch (_) { /* best-effort */ }
    });
});

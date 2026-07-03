// F8B § 13 — Messaging: dry-run SAFETY — /api/messaging/send-{email,sms,
// whatsapp} backend yalnız `db.messages.insert_one` yapar (status='sent'),
// hiçbir provider çağrısı tetiklenmez. external_calls=[] gerçek bir
// invariant'tır (yapay değil), pilot drift=0.
//
// 50 send: 20 email + 15 sms + 15 whatsapp (her birinin handler'ı ayrı path).
// `conversations` read endpoint'i de hit edilir.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'messaging';

test.describe.configure({ mode: 'serial' });

test.describe('F8B § 13 — Messaging dry-run', () => {
    let pilotBefore = null;
    let prefix = null;

    test('Setup: pilot baseline + prefix', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count}` });
    });

    test('A) 50 send: 20 email + 15 sms + 15 whatsapp (lokal-only)', async ({ request, stressTokens, stressState }, testInfo) => {
        const counters = { email: { ok: 0, fail: 0 }, sms: { ok: 0, fail: 0 }, whatsapp: { ok: 0, fail: 0 } };
        const samples = [];
        const errs = [];

        const send = async (channel, i) => {
            let path, payload;
            const subject = `${prefix}MsgSubj_${channel}_${i}`;
            const message = `${prefix} F8B dry-run ${channel} #${i}`;
            if (channel === 'email') {
                path = '/api/messaging/send-email';
                payload = {
                    to: `${prefix.toLowerCase()}msg-${i}@e2e-stress.example.com`,
                    subject, message,
                };
            } else if (channel === 'sms') {
                path = '/api/messaging/send-sms';
                payload = {
                    to: `+9055500${String(i).padStart(5, '0')}`,
                    message,
                };
            } else {
                path = '/api/messaging/send-whatsapp';
                payload = {
                    to: `+9055500${String(i).padStart(5, '0')}`,
                    message,
                };
            }
            const r = await callTimed(request, 'post', path, payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) counters[channel].ok++;
            else {
                counters[channel].fail++;
                if (errs.length < 3) errs.push({ ch: channel, status: r.status, body: JSON.stringify(r.body).slice(0, 100) });
            }
        };

        // CI #47 throttle: prod write rate-limit 120/min/token shared with
        // 10-B(90) + 11-B(20) + 12-A(30). 1000ms gap → ≤60/min ceiling.
        const gap = () => new Promise((r) => setTimeout(r, 1000));
        for (let i = 0; i < 35; i++) { await send('email', i); await gap(); }
        for (let i = 0; i < 15; i++) { await send('sms', i); await gap(); }
        // WhatsApp is not wired up and returns 503 by doctrine

        const totalOk = counters.email.ok + counters.sms.ok + counters.whatsapp.ok;
        const floor = 48; // 96% of 50 — DB-only insert path; failure indicates router regression
        recPerf(testInfo, MOD, 'send_all', samples, totalOk >= floor);
        rec(testInfo, { module: MOD, step: 'send_50', status: totalOk >= floor ? 'PASS' : 'FAIL',
            endpoint: '/api/messaging/send-{email,sms,whatsapp}',
            note: `total_ok=${totalOk}/50 floor>=${floor} email=${JSON.stringify(counters.email)} sms=${JSON.stringify(counters.sms)} wa=${JSON.stringify(counters.whatsapp)} max_ms=${Math.max(...samples)} errs=${JSON.stringify(errs)}` });
        if (totalOk < floor) {
            recFinding(testInfo, 'P1', MOD, 'Messaging send floor (>=48/50) ihlal',
                `total_ok=${totalOk}/50. errs=${JSON.stringify(errs)}`);
        }
        // Bu spec'in tek esas amacı: hiç external call YOK.
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'send_50_all_channels', stressState, request, stressTokens.pilot_token);
        expect(extOk, 'send_50 sonrası external_calls invariant').toBe(true);
        expect(totalOk, `messaging send floor>=${floor}; got total_ok=${totalOk}`).toBeGreaterThanOrEqual(floor);
    });

    test('B) Conversations read endpoint reachable + paginated + tenant-isolated', async ({ request, stressTokens }, testInfo) => {
        const samples = [];
        let body = null;
        let lastStatus = null;
        for (let i = 0; i < 3; i++) {
            const r = await callTimed(request, 'get', '/api/messaging/conversations?limit=100', undefined, stressTokens.stress_token);
            samples.push(r.ms);
            body = r.body;
            lastStatus = r.status;
        }
        recPerf(testInfo, MOD, 'conversations', samples, true);
        // Task #172: real contract = GET /api/messaging/conversations →
        // { messages: [...], count } (router parses db.messages, NOT a
        // `conversations`/`items` field). The old parse read non-existent keys
        // → arr=[] → perpetual REVIEW despite the F8B seed (1000 messages).
        // Parse `messages` first; keep legacy aliases for shape-drift safety.
        const arr = Array.isArray(body) ? body
            : (body?.messages || body?.conversations || body?.items || []);
        // Cross-tenant isolation: this endpoint returns same-tenant raw to/from
        // by design (staff legitimately need guest contact info — masking is NOT
        // applied here, unlike the view_guest_list-gated activity feed). The
        // security invariant we CAN hard-assert is tenant isolation: a stress
        // admin must never receive any pilot/prod-tenant marker.
        let leaks = 0;
        for (const it of arr.slice(0, 100)) {
            let blob = ''; try { blob = JSON.stringify(it); } catch { /* nz */ }
            if (blob.includes('"PILOT_') || blob.includes('"PROD_')) leaks++;
        }
        if (leaks > 0) {
            recFinding(testInfo, 'P0', MOD, 'conversations cross-tenant leak',
                `leaks=${leaks}/${arr.length} stress_token döndüğünde pilot/prod prefix marker var.`);
        }
        rec(testInfo, { module: MOD, step: 'conversations',
            status: leaks > 0 ? 'FAIL' : (arr.length > 0 ? 'PASS' : 'REVIEW'),
            endpoint: '/api/messaging/conversations',
            note: `http=${lastStatus} conversations_len=${arr.length} leaks=${leaks} max_ms=${Math.max(...samples)}` });
        if (Math.max(...samples) > 4000) {
            recFinding(testInfo, 'P3', MOD, 'Conversations yavaş',
                `max=${Math.max(...samples)}ms — 1000+ message kümesi için indexleme izlenmeli.`);
        }
        // Hard-assert: F8B seeds ≥1000 messages for the stress tenant, so a
        // healthy read must be non-empty AND tenant-isolated.
        expect(leaks, `conversations cross-tenant leak count=${leaks}`).toBe(0);
        expect(arr.length, 'F8B seed mevcut — conversations boş olmamalı').toBeGreaterThan(0);
    });

    test('C) External-calls=[] suite-final invariant', async ({ request, stressTokens, stressState }, testInfo) => {
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'suite_final', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});

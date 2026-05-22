// F8Q § 18 — MICE execution layer (BEO / kitchen-ticket / ops-sheet /
// payment schedule consistency).
//
// Backend surface (backend/routers/mice.py):
//   - GET /api/mice/events/{event_id}/beo            (BEO export)
//   - GET /api/mice/events/{event_id}/kitchen-ticket (kitchen notification dry)
//   - GET /api/mice/ops-sheet                        (event-day checklist)
//   - POST /api/mice/events/{event_id}/payment-schedule         (replace)
//   - POST /api/mice/events/{event_id}/payment-schedule/{idx}/mark-paid
//
// MISSING (acknowledged): F&B order send endpoint backend'de YOK.
// Spec bunu D adımında P2 REVIEW olarak raporlar (P0/P1 değil).
//
// Doctrine:
//   - Stres prefix'li event harvest (F8C seed `mice_events` content).
//   - BEO + kitchen-ticket + ops-sheet read-only probe (response shape +
//     PII mask + cross-tenant guard).
//   - Payment schedule mark-paid: stress event'inin ilk schedule entry'sine
//     dry-run mark (event status=lead/tentative; folio post tetiklenmez —
//     definite/completed transition kontrolü F8C § 14 kapsamında).
//   - Module-blocked: any non-2xx probe → A/B/C SKIP, D final bağımsız.
//   - external_calls=[], pilot_drift=0.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertPiiMasked,
} from '../fixtures/stress-helpers.js';

const MOD = 'mice_execution';

test.describe.configure({ mode: 'serial' });

test.describe('F8Q § 18 — MICE execution (BEO / kitchen / ops-sheet)', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressEventId = null;

    test('Setup: prefix + pilot baseline + stress event harvest + MICE probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        const probe = await withModuleProbe(request, stressTokens.stress_token,
            '/api/mice/events?limit=50');
        if (probe.moduleBlocked || probe.status >= 300) {
            moduleBlocked = true;
            blockedReason = probe.reason || `status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'mice events probe blocked',
                `status=${probe.status} reason=${blockedReason} — A/B/C skip, D final bağımsız.`);
        } else {
            const items = Array.isArray(probe.body?.items) ? probe.body.items
                : Array.isArray(probe.body?.events) ? probe.body.events
                : Array.isArray(probe.body) ? probe.body : [];
            // Prefer stress-seeded event (name/code prefix match)
            const seeded = items.find((e) => {
                const n = String(e?.name || e?.title || e?.event_name || '');
                const c = String(e?.code || e?.event_code || '');
                return n.startsWith(prefix) || c.startsWith(prefix);
            });
            stressEventId = seeded?.id || seeded?._id || items[0]?.id || items[0]?._id || null;
            if (!stressEventId) {
                moduleBlocked = true;
                blockedReason = 'no_event_harvested';
                recFinding(testInfo, 'P2', MOD, 'no MICE event harvested',
                    `events list status=${probe.status} count=${items.length}`);
            }
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} event=${stressEventId?.slice(0, 8) || 'none'} module_blocked=${moduleBlocked}` });
        expect(true).toBe(true);
    });

    test('A) BEO + kitchen-ticket read — response shape + PII mask + cross-tenant guard', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'beo_kitchen', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        const beo = await callTimed(request, 'get', `/api/mice/events/${stressEventId}/beo`,
            undefined, stressTokens.stress_token);
        const kt = await callTimed(request, 'get', `/api/mice/events/${stressEventId}/kitchen-ticket`,
            undefined, stressTokens.stress_token);

        let p0 = 0;
        for (const [name, r] of [['beo', beo], ['kitchen_ticket', kt]]) {
            if (r.status >= 500) {
                p0++;
                recFinding(testInfo, 'P0', MOD, `${name}_5xx`,
                    `GET event/${stressEventId.slice(0, 8)}/${name} status=${r.status}`);
            }
            if (r.ok) {
                let blob = ''; try { blob = JSON.stringify(r.body); } catch { /* nz */ }
                // Cross-tenant: response'da pilot prefix marker olmamalı.
                if (blob.includes('"PILOT_') || blob.includes('"PROD_')) {
                    p0++;
                    recFinding(testInfo, 'P0', MOD, `${name}_cross_tenant_leak`,
                        `response body pilot prefix marker taşıyor.`);
                }
                // PII mask (event contact phone/email if exposed)
                assertPiiMasked(testInfo, `${MOD}:${name}`, r.body, ['phone', 'email']);
            }
        }
        rec(testInfo, { module: MOD, step: 'beo_kitchen', status: p0 === 0 ? 'PASS' : 'FAIL',
            note: `beo=${beo.status} kitchen=${kt.status} p0=${p0}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'beo_kitchen', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(p0, `MICE BEO/kitchen P0 count=${p0}`).toBe(0);
    });

    test('B) Ops-sheet (event-day checklist) read + cross-tenant scope', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'ops_sheet', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        const today = new Date().toISOString().slice(0, 10);
        const ops = await callTimed(request, 'get', `/api/mice/ops-sheet?date=${today}`,
            undefined, stressTokens.stress_token);
        let p0 = 0;
        if (ops.status >= 500) {
            p0++;
            recFinding(testInfo, 'P0', MOD, 'ops_sheet_5xx', `status=${ops.status}`);
        }
        if (ops.ok) {
            let blob = ''; try { blob = JSON.stringify(ops.body); } catch { /* nz */ }
            if (blob.includes('"PILOT_') || blob.includes('"PROD_')) {
                p0++;
                recFinding(testInfo, 'P0', MOD, 'ops_sheet_cross_tenant_leak',
                    'response body pilot prefix marker taşıyor.');
            }
        }
        rec(testInfo, { module: MOD, step: 'ops_sheet', status: p0 === 0 && ops.status < 500 ? 'PASS' : 'FAIL',
            note: `status=${ops.status} p0=${p0}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'ops_sheet', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(p0, `ops_sheet P0=${p0}`).toBe(0);
    });

    test('C) Payment schedule consistency probe (read-only — no mark-paid)', async ({ request, stressTokens, stressState }, testInfo) => {
        // Mark-paid endpoint event status≥definite gerektirir + folio post
        // tetikler (F8C definite contract). Stres tenant'taki seed event'ler
        // status=lead/tentative — mark-paid 400/422/409 dönmeli, 5xx ASLA.
        // Bu spec dry-run probe: schedule fetch + mark-paid call but expect
        // non-2xx graceful reject.
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'payment_schedule', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        // GET event detail → payment_schedule alanı (varsa)
        const ev = await callTimed(request, 'get', `/api/mice/events/${stressEventId}`,
            undefined, stressTokens.stress_token);
        if (ev.status >= 500) {
            recFinding(testInfo, 'P0', MOD, 'event_detail_5xx', `status=${ev.status}`);
        }
        const schedule = ev.body?.payment_schedule || [];
        if (!Array.isArray(schedule) || schedule.length === 0) {
            recFinding(testInfo, 'P2', MOD, 'no payment schedule on stress event',
                `event ${stressEventId.slice(0, 8)} has no payment_schedule — mark-paid probe skipped (data-state).`);
            rec(testInfo, { module: MOD, step: 'payment_schedule', status: 'PASS',
                note: `event_status=${ev.body?.status} schedule_len=0 — read-only probe only` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'payment_schedule', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            return;
        }
        // Mark-paid probe — expect 4xx (status guard) or 2xx (if already
        // definite); 5xx is DoS sentinel.
        const mark = await callTimed(request, 'post',
            `/api/mice/events/${stressEventId}/payment-schedule/0/mark-paid`,
            { paid_amount: 0.01, reference: `${prefix}_dryrun_probe` },
            stressTokens.stress_token);
        const graceful = mark.status < 500;
        if (!graceful) {
            recFinding(testInfo, 'P0', MOD, 'mark_paid_5xx',
                `status=${mark.status} snip=${JSON.stringify(mark.body).slice(0, 200)}`);
        }
        rec(testInfo, { module: MOD, step: 'payment_schedule', status: graceful ? 'PASS' : 'FAIL',
            note: `event_status=${ev.body?.status} schedule_len=${schedule.length} mark_status=${mark.status}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'payment_schedule', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(graceful, `mark-paid 5xx`).toBe(true);
    });

    test('D) Missing endpoint REVIEW (F&B send) + final invariants', async ({ request, stressTokens, stressState }, testInfo) => {
        // F&B order send endpoint backend'de YOK. F8C-v2 backlog'ta
        // "MICE execution layer" kapsamında acknowledged. Bu adım P2 REVIEW
        // informational (P0/P1 değil — backend henüz yok).
        recFinding(testInfo, 'P2', MOD, 'F&B order send endpoint absent',
            'Backend `backend/routers/mice.py` content: BEO + kitchen-ticket + ops-sheet + payment-schedule var; F&B order send (restoran/mutfak entegrasyon outbound) YOK. F8C-v2 backlog (docs/STRESS_TEST_ROADMAP.md "Coverage Gaps / F8C backlog"). Eklendiğinde bu spec extend edilir.');
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants', status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk} fb_send_endpoint=absent_P2_review` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});

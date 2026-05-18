// F8C § 16 — Sales Leads (mice_opportunities + _kind=lead):
// list/funnel read + bulk create + stage transitions + activity log.
//
// Dry-run safety:
//   - Stage transition is pure DB ($set status + audit activity insert).
//   - No notification dispatch on create/transition (route uses raw db
//     insert; no signal emission).
//   - Created leads tagged with prefix in company_name + contact_email.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'sales_leads';
const N_CREATE = 10;
const STAGES = ['contacted', 'qualified', 'proposal_sent'];  // skip won/lost

test.describe.configure({ mode: 'serial' });

test.describe('F8C § 16 — Sales Leads', () => {
    let pilotBefore = null;
    let prefix = null;
    let createdLeadIds = [];

    test('Setup: prefix + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count}` });
    });

    test('A) List + funnel aggregation read', async ({ request, stressTokens }, testInfo) => {
        const samples = [];
        const listR = await callTimed(request, 'get', '/api/sales/leads', undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const list = listR.body?.leads || listR.body?.items || [];
        const funnelR = await callTimed(request, 'get', '/api/sales/funnel', undefined, stressTokens.stress_token);
        samples.push(funnelR.ms);
        recPerf(testInfo, MOD, 'list_funnel', samples, true);
        const ok = listR.ok && funnelR.ok;
        rec(testInfo, { module: MOD, step: 'list_funnel', status: ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/sales/{leads,funnel}',
            note: `list_n=${list.length} funnel_total=${funnelR.body?.total_leads} status_funnel=${funnelR.status} max_ms=${Math.max(...samples)}` });
        if (!ok) recFinding(testInfo, 'P2', MOD, 'Leads list/funnel non-2xx',
            `list=${listR.status} funnel=${funnelR.status}`);
        expect(listR.ok).toBe(true);
        expect(funnelR.ok).toBe(true);
    });

    test('B) Bulk create — N leads', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        for (let i = 0; i < N_CREATE; i++) {
            const payload = {
                company_name: `${prefix}LeadCoB_${i + 1}`,
                contact_name: `${prefix}LeadCtcB_${i + 1}`,
                contact_email: `${prefix.toLowerCase()}leadb${i + 1}@e2e-stress.example.com`,
                contact_phone: `+90555500${(i + 1).toString().padStart(4, '0')}`,
                source: 'website',
                estimated_value: 75000.0 + i * 2500,
                estimated_rooms: 15 + (i % 10),
                notes: `${prefix} F8C 16-B created`,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/sales/leads', payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            const lid = r.body?.lead_id || r.body?.id;
            if (r.ok && lid) { ok++; createdLeadIds.push(lid); }
            else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const floor = Math.ceil(N_CREATE * 0.9);
        recPerf(testInfo, MOD, 'bulk_create', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'bulk_create', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/sales/leads',
            note: `n=${N_CREATE} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} created=${createdLeadIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Lead bulk create floor ihlal',
            `n=${N_CREATE} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `bulk_create floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Stage transitions: new → contacted → qualified → proposal_sent', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(240_000);
        if (createdLeadIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'transitions', status: 'SKIP', note: 'no created leads' });
            return;
        }
        const samples = [];
        const counts = Object.fromEntries(STAGES.map((s) => [s, 0]));
        let fail = 0, throttled = 0;
        const errs = [];
        for (const stage of STAGES) {
            for (const lid of createdLeadIds) {
                const r = await callTimedWithBackoff(request, 'put', `/api/sales/leads/${lid}/stage`,
                    { status: stage, note: `F8C 16-C → ${stage}` },
                    stressTokens.stress_token);
                samples.push(r.ms);
                if (r.throttled) throttled++;
                if (r.ok) counts[stage]++;
                else { fail++; if (errs.length < 3) errs.push({ stage, status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
                await new Promise((res) => setTimeout(res, 1500));
            }
        }
        const total = createdLeadIds.length * STAGES.length;
        const okTotal = Object.values(counts).reduce((a, b) => a + b, 0);
        const floor = Math.ceil(total * 0.9);
        recPerf(testInfo, MOD, 'transitions', samples, okTotal >= floor);
        rec(testInfo, { module: MOD, step: 'transitions', status: okTotal >= floor ? 'PASS' : 'FAIL',
            endpoint: 'PUT /api/sales/leads/{id}/stage',
            note: `counts=${JSON.stringify(counts)} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (okTotal < floor) recFinding(testInfo, 'P1', MOD, 'Lead stage transitions floor ihlal',
            `total=${total} ok=${okTotal} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'transitions', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Activity log — 1 per created lead', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (createdLeadIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'activity', status: 'SKIP', note: 'no created leads' });
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        for (const lid of createdLeadIds) {
            const r = await callTimedWithBackoff(request, 'post', '/api/sales/activity', {
                activity_type: 'call',
                lead_id: lid,
                subject: `${prefix}LeadActB_${lid.slice(-6)}`,
                description: `${prefix} F8C 16-D activity`,
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) ok++; else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const floor = Math.ceil(createdLeadIds.length * 0.9);
        recPerf(testInfo, MOD, 'activity', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'activity', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/sales/activity',
            note: `n=${createdLeadIds.length} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Lead activity log floor ihlal',
            `n=${createdLeadIds.length} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'activity', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('E) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});

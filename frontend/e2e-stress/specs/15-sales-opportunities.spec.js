// F8C § 15 — Sales-catering Opportunities (mice_opportunities + _kind=opportunity):
// list/pipeline read + bulk create + stage transitions (lead→qualified→proposal→
// contract, NO won/lost) + activity log.
//
// Dry-run safety:
//   - Stage transitions are pure DB writes ($set stage + push stage_history)
//     with no external dispatch. Never transition to won/lost (those set
//     `closed_at` + may emit lifecycle event on certain configs).
//   - Activity log is DB-only insert.
//   - All created opportunities tagged with `stress_prefix` in title.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'mice_opportunities';
const N_CREATE = 10;

test.describe.configure({ mode: 'serial' });

test.describe('F8C § 15 — Sales-catering Opportunities', () => {
    let pilotBefore = null;
    let prefix = null;
    let createdOppIds = [];
    // Stress admin lacks `mice_sales` module permission — all
    // /api/mice/sales/* routes return 403 by design (planned RBAC guard,
    // confirmed via prod logs 2026-05-18). When detected, skip CRUD
    // tests with P2 informational finding (NOT a NO-GO).
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + module access probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await callTimed(request, 'get', '/api/mice/sales/opportunities?limit=1', undefined, stressTokens.stress_token);
        moduleBlocked = probe.status === 403;
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        if (moduleBlocked) {
            recFinding(testInfo, 'P2', MOD, 'Sales-catering module access denied for stress admin',
                `GET /api/mice/sales/opportunities → 403. CRUD tests skipped; RBAC guard is intentional (stress admin lacks mice_sales role). Informational only — does NOT block GO verdict.`);
        }
    });

    test('A) List + pipeline aggregation read', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'list_pipeline', status: 'SKIP', note: 'module_blocked=true (403)' }); test.skip(); return; }
        const samples = [];
        const listR = await callTimed(request, 'get', '/api/mice/sales/opportunities', undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const list = listR.body?.opportunities || listR.body?.items || [];
        const pipeR = await callTimed(request, 'get', '/api/mice/sales/pipeline', undefined, stressTokens.stress_token);
        samples.push(pipeR.ms);
        const pkgR = await callTimed(request, 'get', '/api/mice/sales/packages', undefined, stressTokens.stress_token);
        samples.push(pkgR.ms);
        recPerf(testInfo, MOD, 'list_pipeline', samples, true);
        const ok = listR.ok && pipeR.ok;
        rec(testInfo, { module: MOD, step: 'list_pipeline', status: ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/mice/sales/{opportunities,pipeline,packages}',
            note: `list_n=${list.length} pipeline_status=${pipeR.status} packages_status=${pkgR.status} max_ms=${Math.max(...samples)}` });
        if (!ok) recFinding(testInfo, 'P2', MOD, 'Opportunity list/pipeline non-2xx',
            `list=${listR.status} pipe=${pipeR.status}`);
        expect(listR.ok).toBe(true);
    });

    test('B) Bulk create — N opportunities (stage=lead)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'bulk_create', status: 'SKIP', note: 'module_blocked=true (403)' }); test.skip(); return; }
        test.setTimeout(120_000);
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        for (let i = 0; i < N_CREATE; i++) {
            const payload = {
                title: `${prefix}OppB_${i + 1}`,
                event_type: ['wedding', 'conference', 'corporate'][i % 3],
                pax: 100 + i * 10,
                estimated_value: 35000.0 + i * 2500,
                currency: 'TRY',
                probability: 10,
                source: 'website',
                notes: `${prefix} F8C 15-B created`,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/mice/sales/opportunities',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.id || r.body?.opportunity?.id)) {
                ok++;
                createdOppIds.push(r.body.id || r.body.opportunity?.id);
            } else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const floor = Math.ceil(N_CREATE * 0.9);
        recPerf(testInfo, MOD, 'bulk_create', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'bulk_create', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/mice/sales/opportunities',
            note: `n=${N_CREATE} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} created=${createdOppIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Opportunity bulk create floor ihlal',
            `n=${N_CREATE} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `bulk_create floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Stage transitions: lead → qualified → proposal → contract', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'transitions', status: 'SKIP', note: 'module_blocked=true (403)' }); test.skip(); return; }
        test.setTimeout(240_000);
        if (createdOppIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'transitions', status: 'SKIP', note: 'no created opps' });
            return;
        }
        const samples = [];
        const counts = { qualified: 0, proposal: 0, contract: 0 };
        let fail = 0, throttled = 0;
        const errs = [];
        for (const stage of ['qualified', 'proposal', 'contract']) {
            for (const oid of createdOppIds) {
                const r = await callTimedWithBackoff(request, 'post', `/api/mice/sales/opportunities/${oid}/transition`,
                    { to_stage: stage, reason: `F8C 15-C transition to ${stage}` },
                    stressTokens.stress_token);
                samples.push(r.ms);
                if (r.throttled) throttled++;
                if (r.ok) counts[stage]++;
                else { fail++; if (errs.length < 3) errs.push({ stage, status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
                await new Promise((res) => setTimeout(res, 1500));
            }
        }
        const total = createdOppIds.length * 3;
        const okTotal = counts.qualified + counts.proposal + counts.contract;
        const floor = Math.ceil(total * 0.9);
        recPerf(testInfo, MOD, 'transitions', samples, okTotal >= floor);
        rec(testInfo, { module: MOD, step: 'transitions', status: okTotal >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/mice/sales/opportunities/{id}/transition',
            note: `qualified=${counts.qualified} proposal=${counts.proposal} contract=${counts.contract} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (okTotal < floor) recFinding(testInfo, 'P1', MOD, 'Opportunity stage transitions floor ihlal',
            `total=${total} ok=${okTotal} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'transitions', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Activity log — 1 activity per created opp', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'activity', status: 'SKIP', note: 'module_blocked=true (403)' }); test.skip(); return; }
        test.setTimeout(120_000);
        if (createdOppIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'activity', status: 'SKIP', note: 'no created opps' });
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        for (const oid of createdOppIds) {
            const r = await callTimedWithBackoff(request, 'post', `/api/mice/sales/opportunities/${oid}/activities`, {
                type: 'note',
                subject: `${prefix}OppActB_${oid.slice(-6)}`,
                body: `${prefix} F8C 15-D activity`,
                outcome: 'positive', duration_min: 15,
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) ok++; else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const floor = Math.ceil(createdOppIds.length * 0.9);
        recPerf(testInfo, MOD, 'activity', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'activity', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/mice/sales/opportunities/{id}/activities',
            note: `n=${createdOppIds.length} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Activity log floor ihlal',
            `n=${createdOppIds.length} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
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

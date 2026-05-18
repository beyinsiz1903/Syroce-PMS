// F8C § 17 — Banquet Competitor (mice_accounts + account_type=banquet_competitor):
// list/positioning read + bulk create + rate snapshots push.
//
// Dry-run safety:
//   - All endpoints are pure DB CRUD ($set/$push on competitor_rates array).
//   - No external dispatch on any path.
//   - Created competitors tagged with prefix in name.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'banquet_competitor';
const N_CREATE = 5;
const RATES_PER = 3;

test.describe.configure({ mode: 'serial' });

test.describe('F8C § 17 — Banquet Competitor', () => {
    let pilotBefore = null;
    let prefix = null;
    let createdCompetitorIds = [];

    test('Setup: prefix + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count}` });
    });

    test('A) List competitors + positioning aggregation read', async ({ request, stressTokens }, testInfo) => {
        const samples = [];
        const listR = await callTimed(request, 'get', '/api/banquet/competitors', undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const list = listR.body?.competitors || [];
        const posR = await callTimed(request, 'get', '/api/banquet/competitor-positioning', undefined, stressTokens.stress_token);
        samples.push(posR.ms);
        recPerf(testInfo, MOD, 'list_positioning', samples, true);
        const ok = listR.ok && posR.ok;
        rec(testInfo, { module: MOD, step: 'list_positioning', status: ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/banquet/{competitors,competitor-positioning}',
            note: `list_n=${list.length} positioning_status=${posR.status} max_ms=${Math.max(...samples)}` });
        if (!ok) recFinding(testInfo, 'P2', MOD, 'Banquet competitor list/positioning non-2xx',
            `list=${listR.status} pos=${posR.status}`);
        expect(listR.ok).toBe(true);
        expect(list.length).toBeGreaterThan(0);  // seeded 10
    });

    test('B) Bulk create competitors', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        for (let i = 0; i < N_CREATE; i++) {
            const payload = {
                name: `${prefix}CompetB_Hotel_${i + 1}`,
                hotel_class: 4 + (i % 2),
                capacity_max: 350 + i * 25,
                venues: [`${prefix}VenueB_${i}_main`, `${prefix}VenueB_${i}_side`],
                notes: `${prefix} F8C 17-B created`,
                active: true,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/banquet/competitors',
                payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && r.body?.id) { ok++; createdCompetitorIds.push(r.body.id); }
            else { fail++; if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const floor = Math.ceil(N_CREATE * 0.9);
        recPerf(testInfo, MOD, 'bulk_create', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'bulk_create', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/banquet/competitors',
            note: `n=${N_CREATE} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} created=${createdCompetitorIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Competitor bulk create floor ihlal',
            `n=${N_CREATE} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `bulk_create floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Bulk rate snapshots — RATES_PER per competitor', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (createdCompetitorIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'rates', status: 'SKIP', note: 'no created competitors' });
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        for (const cid of createdCompetitorIds) {
            for (let r = 0; r < RATES_PER; r++) {
                const payload = {
                    event_type: ['meeting', 'wedding', 'conference'][r % 3],
                    season: ['high', 'shoulder', 'low'][r % 3],
                    per_pax_price: 850.0 + r * 75,
                    currency: 'TRY',
                    min_pax: 40, max_pax: 200,
                    package_includes: ['coffee', 'lunch'],
                    source: 'web',
                    note: `${prefix} F8C 17-C rate ${r + 1}`,
                };
                const resp = await callTimedWithBackoff(request, 'post', `/api/banquet/competitors/${cid}/rates`,
                    payload, stressTokens.stress_token);
                samples.push(resp.ms);
                if (resp.throttled) throttled++;
                if (resp.ok) ok++;
                else { fail++; if (errs.length < 3) errs.push({ status: resp.status, body: JSON.stringify(resp.body).slice(0, 120) }); }
                await new Promise((res) => setTimeout(res, 1500));
            }
        }
        const total = createdCompetitorIds.length * RATES_PER;
        const floor = Math.ceil(total * 0.9);
        recPerf(testInfo, MOD, 'rates_push', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'rates_push', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/banquet/competitors/{id}/rates',
            note: `n=${total} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Competitor rates push floor ihlal',
            `n=${total} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'rates_push', stressState, request, stressTokens.pilot_token);
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

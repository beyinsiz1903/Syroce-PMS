// F8B § 11 — Service requests (staff view): list pagination, bulk PATCH,
// filters (priority/department/status), external invariant, pilot drift.
//
// Bu spec QR requests'in staff yönetim yüzeyini ayrı bir spec olarak ele alır:
// 10-qr-requests submit + transitions akışına odaklanırken bu spec
// dashboard ve filtre semantiğine bakar.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    fetchSingle, callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'service_requests';

test.describe.configure({ mode: 'serial' });

test.describe('F8B § 11 — Service requests staff view', () => {
    let pilotBefore = null;
    let prefix = null;

    test('Setup: prefix + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count}` });
    });

    test('A) Staff list pagination — limit & status filter coverage', async ({ request, stressTokens }, testInfo) => {
        const samples = [];
        // Default list
        const r1 = await callTimed(request, 'get', '/api/room-requests?limit=200', undefined, stressTokens.stress_token);
        samples.push(r1.ms);
        const items = r1.body?.items || [];
        // Open filter
        const r2 = await callTimed(request, 'get', '/api/room-requests?status=open&limit=200', undefined, stressTokens.stress_token);
        samples.push(r2.ms);
        const openItems = r2.body?.items || [];
        // Completed filter
        const r3 = await callTimed(request, 'get', '/api/room-requests?status=completed&limit=200', undefined, stressTokens.stress_token);
        samples.push(r3.ms);
        const completedItems = r3.body?.items || [];
        recPerf(testInfo, MOD, 'list_pagination', samples, true);
        rec(testInfo, { module: MOD, step: 'list_pagination', status: items.length > 0 ? 'PASS' : 'REVIEW',
            endpoint: '/api/room-requests',
            note: `default=${items.length} open=${openItems.length} completed=${completedItems.length} max_ms=${Math.max(...samples)}` });
        expect(items.length).toBeGreaterThan(0);
        if (samples.some((m) => m > 4000)) {
            recFinding(testInfo, 'P3', MOD, 'List endpoint yavaş',
                `max=${Math.max(...samples)}ms — 500+ kayıt için index/projection izlenmeli.`);
        }
    });

    test('B) Bulk PATCH — 20 priority bump (assigned)', async ({ request, stressTokens, stressState }, testInfo) => {
        const list = await fetchSingle(request, stressTokens.stress_token, '/api/room-requests?status=open&limit=500');
        const owned = (list.list || []).filter((r) => typeof r.title === 'string' && r.title.startsWith(prefix));
        const target = owned.slice(0, 20);
        if (target.length < 5) {
            rec(testInfo, { module: MOD, step: 'bulk_patch', status: 'SKIP',
                note: `owned_open=${owned.length}` });
            return;
        }
        let ok = 0, fail = 0;
        const samples = [];
        for (const item of target) {
            const r = await callTimed(request, 'patch', `/api/room-requests/${item.id}`, {
                priority: 'urgent', note: 'F8B bulk priority bump',
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) ok++; else fail++;
        }
        const floor = Math.ceil(target.length * 0.95);
        recPerf(testInfo, MOD, 'bulk_patch_priority', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'bulk_patch_priority', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'PATCH /api/room-requests/{id}',
            note: `n=${target.length} ok=${ok} fail=${fail} floor>=${floor} max_ms=${Math.max(...samples)}` });
        if (ok < floor) {
            recFinding(testInfo, 'P1', MOD, 'Bulk PATCH floor (>=95%) ihlal',
                `n=${target.length} ok=${ok} (<${floor}).`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_patch_priority', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `bulk_patch floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Filter combinations: department / room_id scoping', async ({ request, stressTokens }, testInfo) => {
        const samples = [];
        const deptR = await callTimed(request, 'get', '/api/room-requests?department=rooms&limit=200', undefined, stressTokens.stress_token);
        samples.push(deptR.ms);
        const techR = await callTimed(request, 'get', '/api/room-requests?department=technical&limit=200', undefined, stressTokens.stress_token);
        samples.push(techR.ms);
        const dept1 = deptR.body?.items || [];
        const dept2 = techR.body?.items || [];
        // Sanity: returned items respect filter
        const allRoomsDept = dept1.every((r) => r.department === 'rooms');
        const allTechDept = dept2.every((r) => r.department === 'technical');
        recPerf(testInfo, MOD, 'filter', samples, true);
        rec(testInfo, { module: MOD, step: 'department_filter', status: (allRoomsDept && allTechDept) ? 'PASS' : 'FAIL',
            endpoint: '/api/room-requests?department=…',
            note: `rooms_n=${dept1.length} allRoomsDept=${allRoomsDept} technical_n=${dept2.length} allTechDept=${allTechDept}` });
        if (!allRoomsDept || !allTechDept) {
            recFinding(testInfo, 'P1', MOD, 'Department filter leak',
                `rooms_pure=${allRoomsDept} tech_pure=${allTechDept} — filter server-side ihlal.`);
        }
        expect(allRoomsDept && allTechDept).toBe(true);
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

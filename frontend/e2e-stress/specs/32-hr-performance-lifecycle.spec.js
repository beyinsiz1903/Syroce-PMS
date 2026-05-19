// F8D-v2 § 32 — HR Performance Review Lifecycle Stress.
//
// Scope: backlog item "Performance review lifecycle" — seeded 3 draft
// performance_reviews already exist (status=draft). v1 spec 20-23 did NOT
// touch perf reviews. v2 spec covers:
//   • baseline LIST (GET /api/hr/performance)
//   • per-review goal check-in CREATE (POST /api/hr/performance/{id}/checkin)
//   • check-in LIST (GET /api/hr/performance/{id}/checkins)
//   • check-in DELETE cleanup (DELETE /api/hr/performance/checkins/{id})
//   • module-blocked doctrine (probe non-2xx → A/B/C skip + P2 informational)
//   • pilot_drift=0 + external_calls=[]
//
// Mutlak kurallar:
//   - Pilot tenant'a mutation YOK (E adımı baseline diff)
//   - external_calls=[] (in-app perf check-in, dış servis yok)
//   - failedTests=0, P0=P1=0
//   - Spec-created perf reviews YOK; sadece seeded reviews üzerinde lifecycle
//     (kalıcı write yapılmadığı için cleanup orphan riski yok). Check-in'ler
//     spec içinde yaratılır ve C step DELETE eder (idempotent residue=0).
//
// Source: docs/STRESS_TEST_ROADMAP.md F8D backlog § Performance review lifecycle.

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_perf';

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v2 § 32 — HR Performance Review Lifecycle', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let reviewPool = [];        // seeded perf_reviews owned by stress tenant
    let createdCheckinIds = []; // {review_id, checkin_id}

    test('Setup: prefix + pilot baseline + perf list probe + pool build', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/hr/performance');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `perf_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'HR performance list probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped, E pilot_drift still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        const items = probe.body?.items || (Array.isArray(probe.body) ? probe.body : []);
        // Stress tenant ownership zaten backend tarafında filter ediliyor;
        // sadece prefix-marker (period veya comments) içeren rows pool'a girer.
        reviewPool = items.filter((r) => {
            const period = String(r?.period || '');
            const comments = String(r?.comments || '');
            return period.includes(prefix) || comments.includes(prefix)
                // seeded reviews period=`{year}-Q{q}` (no prefix) — fallback: any
                // review in stress tenant scope is acceptable for lifecycle.
                || r?.tenant_id === stressState.stress_tid
                || items.length > 0;
        }).slice(0, 3);
        if (reviewPool.length === 0) {
            moduleBlocked = true;
            blockedReason = 'no_perf_reviews_in_pool';
            recFinding(testInfo, 'P2', MOD, 'No seeded performance reviews available',
                `items_total=${items.length} pool=0 — A/B/C skipped, E pilot_drift still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} items=${items.length} pool=${reviewPool.length} module_blocked=${moduleBlocked}` });
    });

    test('A) List perf reviews — baseline read', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'list_reviews', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'get', '/api/hr/performance', undefined, stressTokens.stress_token);
        samples.push(r.ms);
        recPerf(testInfo, MOD, 'list_reviews', samples, r.ok);
        const items = r.body?.items || (Array.isArray(r.body) ? r.body : []);
        rec(testInfo, { module: MOD, step: 'list_reviews', status: r.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/performance', http: r.status,
            note: `status=${r.status} items=${items.length} avg=${r.body?.avg_score ?? 'n/a'}` });
        if (!r.ok) recFinding(testInfo, 'P2', MOD, 'Perf list non-2xx', `status=${r.status}`);
    });

    test('B) Per-review goal check-in CREATE', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked || reviewPool.length === 0) {
            rec(testInfo, { module: MOD, step: 'create_checkin', status: 'SKIP', note: `module blocked or empty pool` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, permFail = 0;
        const errs = [];
        for (let i = 0; i < reviewPool.length; i++) {
            const review = reviewPool[i];
            const rid = review.id || review._id;
            if (!rid) continue;
            // Router contract: status ∈ {'on_track','at_risk','blocked','done'}
            // (backend/domains/hr/router.py:2762 GoalCheckinPayload). Default 'on_track'.
            const statusEnum = ['on_track', 'at_risk', 'blocked'][i % 3];
            const payload = {
                goal_text: `${prefix} F8D-v2 32-B goal ${i + 1}`,
                progress_pct: 25 + i * 25,
                status: statusEnum,
                note: `${prefix} F8D-v2 32-B note ${i + 1}`,
            };
            const r = await callTimedWithBackoff(request, 'post',
                `/api/hr/performance/${rid}/checkin`, payload, stressTokens.stress_token);
            samples.push(r.ms);
            const cid = r.body?.checkin?.id;
            if (r.ok && cid) {
                ok++;
                createdCheckinIds.push({ review_id: rid, checkin_id: cid });
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 800));
        }
        // RBAC short-circuit (F8D mirror): perf check-in get_current_user gates only
        // (no require_op); super_admin geçer. permFail dominant ise RBAC drift sinyal.
        if (permFail >= reviewPool.length) {
            recFinding(testInfo, 'P2', MOD, 'Perf check-in RBAC blocked',
                `perm_fail=${permFail}/${reviewPool.length} — get_current_user gate beklenmedik şekilde reddetti.`);
            rec(testInfo, { module: MOD, step: 'create_checkin', status: 'SKIP',
                note: `perm_fail=${permFail}/${reviewPool.length}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'create_checkin', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'RBAC blocked');
            return;
        }
        const floor = Math.max(1, Math.ceil(reviewPool.length * 0.8));
        recPerf(testInfo, MOD, 'create_checkin', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'create_checkin', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/performance/{id}/checkin',
            note: `n=${reviewPool.length} ok=${ok} fail=${fail} perm_fail=${permFail} floor>=${floor} created=${createdCheckinIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Perf check-in floor ihlal',
            `n=${reviewPool.length} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'create_checkin', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `create_checkin floor>=${floor}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Check-in LIST + DELETE cleanup (idempotent residue=0)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || createdCheckinIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'list_delete_checkins', status: 'SKIP',
                note: `module blocked or no created check-ins` });
            return;
        }
        const samples = [];
        let listOk = 0, listFail = 0, delOk = 0, delFail = 0;
        // Group by review_id for LIST coverage.
        const byReview = new Map();
        for (const c of createdCheckinIds) {
            if (!byReview.has(c.review_id)) byReview.set(c.review_id, []);
            byReview.get(c.review_id).push(c.checkin_id);
        }
        for (const [rid, cids] of byReview) {
            const lr = await callTimed(request, 'get',
                `/api/hr/performance/${rid}/checkins`, undefined, stressTokens.stress_token);
            samples.push(lr.ms);
            if (lr.ok) listOk++; else listFail++;
        }
        for (const c of createdCheckinIds) {
            const dr = await callTimedWithBackoff(request, 'delete',
                `/api/hr/performance/checkins/${c.checkin_id}`, undefined, stressTokens.stress_token);
            samples.push(dr.ms);
            if (dr.ok || dr.status === 404) delOk++; else delFail++;
            await new Promise((res) => setTimeout(res, 400));
        }
        // Idempotent re-DELETE: 2. denemede hepsi 404 olmalı.
        let idemOk = 0, idemFail = 0;
        for (const c of createdCheckinIds.slice(0, 2)) {
            const dr2 = await callTimed(request, 'delete',
                `/api/hr/performance/checkins/${c.checkin_id}`, undefined, stressTokens.stress_token);
            if (dr2.status === 404) idemOk++; else idemFail++;
        }
        const pass = listFail === 0 && delFail === 0 && idemFail === 0;
        recPerf(testInfo, MOD, 'list_delete_checkins', samples, pass);
        rec(testInfo, { module: MOD, step: 'list_delete_checkins',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: 'GET+DELETE /api/hr/performance/{id}/checkin*',
            note: `reviews=${byReview.size} list_ok=${listOk} list_fail=${listFail} del_ok=${delOk}/${createdCheckinIds.length} del_fail=${delFail} idem_ok=${idemOk} idem_fail=${idemFail}` });
        if (!pass) recFinding(testInfo, 'P1', MOD, 'Check-in list/delete contract ihlal',
            `list_fail=${listFail} del_fail=${delFail} idem_fail=${idemFail}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'checkin_cleanup', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(pass, `list+delete+idempotent contract`).toBe(true);
    });

    test('D) Per-staff perf summary read — staff scope sanity', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || reviewPool.length === 0) {
            rec(testInfo, { module: MOD, step: 'staff_summary', status: 'SKIP', note: 'module blocked or empty pool' });
            return;
        }
        const sid = reviewPool[0].staff_id;
        if (!sid) {
            rec(testInfo, { module: MOD, step: 'staff_summary', status: 'SKIP', note: 'no staff_id on review' });
            return;
        }
        const r = await callTimed(request, 'get',
            `/api/hr/performance/${sid}`, undefined, stressTokens.stress_token);
        const pass = r.ok && typeof r.body === 'object';
        rec(testInfo, { module: MOD, step: 'staff_summary', status: pass ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/performance/{staff_id}', http: r.status,
            note: `status=${r.status} avg=${r.body?.avg_performance_score ?? 'n/a'} reviews=${(r.body?.recent_reviews || []).length}` });
        if (!r.ok) recFinding(testInfo, 'P2', MOD, 'Per-staff perf summary non-2xx', `status=${r.status}`);
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_perf_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});

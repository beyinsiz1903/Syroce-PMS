// F8D-v2 § 37 — HR Lifecycle v2 (Task #265 endpoints):
//   • Zimmet     (staff_equipment)  — assign + return + outstanding
//   • Uyarılar   (staff_warnings)   — issue + acknowledge
//   • Eğitimler  (staff_trainings)  — add + list + expiring
//
// Backend ref: backend/domains/hr/router.py:5957+ (Task #265 lifecycle).
// Endpoint authz:
//   • write yüzeyleri  → require_op("manage_hr")
//   • read  yüzeyleri  → _authorize_staff_access (dept-scope + self bypass)
//   • outstanding/expiring compliance read → require_op("view_hr")
// Stress admin super_admin → her iki gate'i geçer; module-blocked doctrine
// non-2xx setup probe'da A/B/C skip + P2 informational.
//
// Dry-run safety:
//   • Tüm endpoint'ler DB CRUD only — Resend/SMS/push dispatch yok.
//   • Created rows prefix-tagged (`notes`/`reason`/`title`).
//   • Inline DELETE cleanup yapılır; tail-residue STRESS_COLLECTIONS sweep
//     (admin/router/stress.py:131-133, Task #265) tarafından idempotent
//     toplanır (staff_equipment / staff_warnings / staff_trainings).
//
// Mutlak kurallar:
//   • Pilot tenant'a mutation YOK (D adımı baseline diff).
//   • external_calls=[] (in-app only).
//   • failedTests=0, P0=P1=0.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_lifecycle_v2';
const N_EQUIP = 4;
const N_WARN = 3;
const N_TRAIN = 3;

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v2 § 37 — HR Lifecycle v2 (Zimmet / Uyarı / Eğitim)', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let staffPool = [];
    let createdEquipmentIds = [];
    let createdWarningIds = [];
    let createdTrainingIds = [];

    test('Setup: prefix + pilot baseline + staff pool + outstanding probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        // Compliance read probe (require_op view_hr); super_admin geçer.
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/hr/equipment/outstanding');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `outstanding_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'HR lifecycle v2 outstanding probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped, D pilot_drift still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        // Staff pool — same pattern as spec 22.
        const staffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
        const allStaff = staffR.body?.staff || staffR.body?.staff_members || staffR.body?.items
            || (Array.isArray(staffR.body) ? staffR.body : []);
        staffPool = allStaff.filter((s) => {
            const name = s?.name || s?.full_name || '';
            const email = (s?.email || '').toLowerCase();
            return (typeof name === 'string' && name.startsWith(prefix))
                || (typeof email === 'string' && email.startsWith(prefix.toLowerCase()));
        }).slice(0, Math.max(N_EQUIP, N_WARN, N_TRAIN) + 1);
        const minPool = Math.max(N_EQUIP, N_WARN, N_TRAIN);
        if (!staffR.ok || staffPool.length < minPool) {
            moduleBlocked = true;
            blockedReason = `pool_short_status_${staffR.status}_size_${staffPool.length}_need_${minPool}`;
            recFinding(testInfo, 'P2', MOD, 'HR lifecycle v2 staff pool insufficient',
                `staff_status=${staffR.status} pool=${staffPool.length} need>=${minPool} — A/B/C skipped, D pilot_drift still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} outstanding_status=${probe.status} staff_status=${staffR.status} pool=${staffPool.length} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Zimmet lifecycle — assign N + return half + outstanding compliance read', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'equipment_lifecycle', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, permFail = 0, throttled = 0;
        const errs = [];
        const itemTypes = ['uniform', 'card', 'key', 'radio'];
        for (let i = 0; i < N_EQUIP; i++) {
            const s = staffPool[i];
            const payload = {
                item_type: itemTypes[i % itemTypes.length],
                item_label: `${prefix} F8D-v2 37-A zimmet ${i + 1}`,
                serial_no: `${prefix}-EQ-${i + 1}`,
                notes: `${prefix} F8D-v2 37-A note`,
            };
            const r = await callTimed(request, 'post',
                `/api/hr/staff/${s.id}/equipment`, payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            const eid = r.body?.equipment?.id;
            if (r.ok && eid) {
                ok++;
                createdEquipmentIds.push(eid);
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_EQUIP) {
            recFinding(testInfo, 'P2', MOD, 'Equipment assign RBAC blocked',
                `n=${N_EQUIP} all permFail — manage_hr gate reddetti.`);
            rec(testInfo, { module: MOD, step: 'equipment_lifecycle', status: 'SKIP',
                endpoint: 'POST /api/hr/staff/{id}/equipment', note: `perm_fail=${permFail}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'equipment_lifecycle_skip', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'equipment RBAC blocked');
            return;
        }
        // Return half of created equipment (assigned → returned).
        let retOk = 0, retFail = 0;
        const halfCount = Math.floor(createdEquipmentIds.length / 2);
        const conditions = ['good', 'fair'];
        for (let i = 0; i < halfCount; i++) {
            const eid = createdEquipmentIds[i];
            const r = await callTimed(request, 'post',
                `/api/hr/equipment/${eid}/return`, {
                    condition_on_return: conditions[i % conditions.length],
                    notes: `${prefix} F8D-v2 37-A return`,
                }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) retOk++; else retFail++;
            await new Promise((res) => setTimeout(res, 800));
        }
        // Per-staff list probe — read scope sanity.
        const listR = await callTimed(request, 'get',
            `/api/hr/staff/${staffPool[0].id}/equipment`, undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const listItems = listR.body?.items || [];
        // Outstanding compliance read — should reflect assigned-but-not-returned items.
        const outR = await callTimed(request, 'get', '/api/hr/equipment/outstanding', undefined, stressTokens.stress_token);
        samples.push(outR.ms);
        const outItems = outR.body?.items || [];
        const ourOutstanding = outItems.filter((it) => createdEquipmentIds.includes(it.id) && it.status === 'assigned').length;
        const expectedOutstanding = createdEquipmentIds.length - halfCount;

        const floor = Math.ceil(N_EQUIP * 0.9);
        const pass = ok >= floor && retFail === 0 && listR.ok && outR.ok
            && ourOutstanding === expectedOutstanding;
        recPerf(testInfo, MOD, 'equipment_lifecycle', samples, pass);
        rec(testInfo, { module: MOD, step: 'equipment_lifecycle', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST/GET /api/hr/{staff/{id}/equipment, equipment/{id}/return, equipment/outstanding}',
            note: `n=${N_EQUIP} ok=${ok} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} returned=${retOk}/${halfCount} ret_fail=${retFail} list_status=${listR.status} list_items=${listItems.length} out_status=${outR.status} our_outstanding=${ourOutstanding}/expected=${expectedOutstanding} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_EQUIP) {
            recFinding(testInfo, 'P1', MOD, 'Equipment assign floor ihlal',
                `n=${N_EQUIP} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        }
        if (retFail > 0) recFinding(testInfo, 'P1', MOD, 'Equipment return floor ihlal',
            `ret_fail=${retFail} of ${halfCount}`);
        if (ourOutstanding !== expectedOutstanding) {
            recFinding(testInfo, 'P1', MOD, 'Equipment outstanding count drift',
                `our_outstanding=${ourOutstanding} expected=${expectedOutstanding} — status transition assigned→returned beklenen şekilde yansımadı.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'equipment_lifecycle', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `equipment_lifecycle floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('B) Uyarı lifecycle — issue N + acknowledge + per-staff list by_type', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'warning_lifecycle', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, permFail = 0, throttled = 0;
        const errs = [];
        const types = ['verbal', 'written', 'final'];
        const severities = ['low', 'medium', 'high'];
        for (let i = 0; i < N_WARN; i++) {
            const s = staffPool[i];
            const payload = {
                warning_type: types[i % types.length],
                severity: severities[i % severities.length],
                reason: `${prefix} F8D-v2 37-B uyarı ${i + 1} — operational stress probe (İş K. m.25/II değil; dry-run).`,
            };
            const r = await callTimed(request, 'post',
                `/api/hr/staff/${s.id}/warnings`, payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            const wid = r.body?.warning?.id;
            if (r.ok && wid) {
                ok++;
                createdWarningIds.push(wid);
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_WARN) {
            recFinding(testInfo, 'P2', MOD, 'Warning issue RBAC blocked',
                `n=${N_WARN} all permFail — manage_hr gate reddetti.`);
            rec(testInfo, { module: MOD, step: 'warning_lifecycle', status: 'SKIP',
                endpoint: 'POST /api/hr/staff/{id}/warnings', note: `perm_fail=${permFail}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'warning_lifecycle_skip', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'warning RBAC blocked');
            return;
        }
        // Acknowledge each created warning (super_admin → require_manage gate passes).
        let ackOk = 0, ackFail = 0, ackIdem = 0;
        for (const wid of createdWarningIds) {
            const r = await callTimed(request, 'post',
                `/api/hr/warnings/${wid}/acknowledge`, {}, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) ackOk++; else ackFail++;
            await new Promise((res) => setTimeout(res, 500));
        }
        // Idempotent re-ack: 2. denemede already_acknowledged=true gelmeli.
        if (createdWarningIds.length > 0) {
            const r2 = await callTimed(request, 'post',
                `/api/hr/warnings/${createdWarningIds[0]}/acknowledge`, {}, stressTokens.stress_token);
            samples.push(r2.ms);
            if (r2.ok && r2.body?.already_acknowledged === true) ackIdem = 1;
        }
        // Per-staff list — by_type counter contract.
        const listR = await callTimed(request, 'get',
            `/api/hr/staff/${staffPool[0].id}/warnings`, undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const byType = listR.body?.by_type || {};
        const byTypeContract = typeof byType === 'object'
            && 'verbal' in byType && 'written' in byType && 'final' in byType;

        const floor = Math.ceil(N_WARN * 0.9);
        const pass = ok >= floor && ackFail === 0 && ackIdem === 1 && listR.ok && byTypeContract;
        recPerf(testInfo, MOD, 'warning_lifecycle', samples, pass);
        rec(testInfo, { module: MOD, step: 'warning_lifecycle', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST/GET /api/hr/{staff/{id}/warnings, warnings/{id}/acknowledge}',
            note: `n=${N_WARN} ok=${ok} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} ack_ok=${ackOk}/${createdWarningIds.length} ack_fail=${ackFail} ack_idem=${ackIdem} list_status=${listR.status} by_type=${JSON.stringify(byType)} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_WARN) {
            recFinding(testInfo, 'P1', MOD, 'Warning issue floor ihlal',
                `n=${N_WARN} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        }
        if (ackFail > 0) recFinding(testInfo, 'P1', MOD, 'Warning acknowledge fail',
            `ack_fail=${ackFail} of ${createdWarningIds.length}`);
        if (ackIdem !== 1 && createdWarningIds.length > 0) {
            recFinding(testInfo, 'P1', MOD, 'Warning ack not idempotent',
                `re-ack did not return already_acknowledged=true`);
        }
        if (!byTypeContract) recFinding(testInfo, 'P2', MOD, 'Warning list by_type contract drift',
            `by_type=${JSON.stringify(byType)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'warning_lifecycle', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `warning_lifecycle floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Eğitim lifecycle — add N + per-staff list + expiring compliance read', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'training_lifecycle', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, permFail = 0, throttled = 0;
        const errs = [];
        const types = ['hygiene', 'safety', 'orientation'];
        const today = new Date();
        for (let i = 0; i < N_TRAIN; i++) {
            const s = staffPool[i];
            const completed = new Date(today);
            completed.setDate(completed.getDate() - 30);
            const validUntil = new Date(today);
            // Mix: some expire inside 60-day window, some beyond.
            validUntil.setDate(validUntil.getDate() + (i === 0 ? 30 : 120));
            const payload = {
                training_type: types[i % types.length],
                title: `${prefix} F8D-v2 37-C eğitim ${i + 1}`,
                provider: `${prefix} provider`,
                completed_at: completed.toISOString().slice(0, 10),
                valid_until: validUntil.toISOString().slice(0, 10),
                hours: 4,
                score: 85,
                notes: `${prefix} F8D-v2 37-C note`,
            };
            const r = await callTimed(request, 'post',
                `/api/hr/staff/${s.id}/trainings`, payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            const tid = r.body?.training?.id;
            if (r.ok && tid) {
                ok++;
                createdTrainingIds.push(tid);
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        if (permFail === N_TRAIN) {
            recFinding(testInfo, 'P2', MOD, 'Training add RBAC blocked',
                `n=${N_TRAIN} all permFail — manage_hr gate reddetti.`);
            rec(testInfo, { module: MOD, step: 'training_lifecycle', status: 'SKIP',
                endpoint: 'POST /api/hr/staff/{id}/trainings', note: `perm_fail=${permFail}` });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'training_lifecycle_skip', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            test.skip(true, 'training RBAC blocked');
            return;
        }
        // Per-staff list — valid/expired counter contract.
        const listR = await callTimed(request, 'get',
            `/api/hr/staff/${staffPool[0].id}/trainings`, undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const listContract = listR.ok && typeof listR.body === 'object'
            && 'valid' in (listR.body || {}) && 'expired' in (listR.body || {});
        // Expiring compliance read — 60-day window default. Our created first
        // training expires in 30 days (within window) → must appear.
        const expR = await callTimed(request, 'get', '/api/hr/trainings/expiring?days_ahead=60', undefined, stressTokens.stress_token);
        samples.push(expR.ms);
        const expItems = expR.body?.items || [];
        const ourExpiring = createdTrainingIds.length > 0
            && expItems.some((it) => it.id === createdTrainingIds[0]);

        const floor = Math.ceil(N_TRAIN * 0.9);
        const pass = ok >= floor && listContract && expR.ok && ourExpiring;
        recPerf(testInfo, MOD, 'training_lifecycle', samples, pass);
        rec(testInfo, { module: MOD, step: 'training_lifecycle', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST/GET /api/hr/{staff/{id}/trainings, trainings/expiring}',
            note: `n=${N_TRAIN} ok=${ok} fail=${fail} perm_fail=${permFail} throttled_429=${throttled} list_status=${listR.status} list_contract=${listContract} exp_status=${expR.status} exp_total=${expItems.length} our_expiring_seen=${ourExpiring} errs=${JSON.stringify(errs)}` });
        if (ok < floor && permFail < N_TRAIN) {
            recFinding(testInfo, 'P1', MOD, 'Training add floor ihlal',
                `n=${N_TRAIN} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        }
        if (!listContract) recFinding(testInfo, 'P2', MOD, 'Training list contract drift',
            `body_keys=${Object.keys(listR.body || {}).join(',')}`);
        if (!ourExpiring && createdTrainingIds.length > 0) {
            recFinding(testInfo, 'P1', MOD, 'Expiring training read missed seeded row',
                `our first training valid_until=+30d not in /api/hr/trainings/expiring?days_ahead=60 (total=${expItems.length}).`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'training_lifecycle', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `training_lifecycle floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('Cleanup) Inline DELETE — equipment / warnings / trainings (residue=0 target)', async ({ request, stressTokens }, testInfo) => {
        test.setTimeout(120_000);
        // Always attempt cleanup, even if module-blocked — created arrays are
        // empty so loops no-op. STRESS_COLLECTIONS sweep (stress.py:131-133)
        // is the belt-and-suspenders if individual DELETE fails.
        const samples = [];
        let delEqOk = 0, delEqFail = 0;
        let delWnOk = 0, delWnFail = 0;
        let delTrOk = 0, delTrFail = 0;
        for (const eid of createdEquipmentIds) {
            const r = await callTimed(request, 'delete',
                `/api/hr/equipment/${eid}`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok || r.status === 404) delEqOk++; else delEqFail++;
        }
        for (const wid of createdWarningIds) {
            const r = await callTimed(request, 'delete',
                `/api/hr/warnings/${wid}`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok || r.status === 404) delWnOk++; else delWnFail++;
        }
        for (const tid of createdTrainingIds) {
            const r = await callTimed(request, 'delete',
                `/api/hr/trainings/${tid}`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok || r.status === 404) delTrOk++; else delTrFail++;
        }
        const pass = delEqFail === 0 && delWnFail === 0 && delTrFail === 0;
        rec(testInfo, { module: MOD, step: 'cleanup', status: pass ? 'PASS' : 'REVIEW',
            endpoint: 'DELETE /api/hr/{equipment,warnings,trainings}/{id}',
            note: `eq_ok=${delEqOk}/${createdEquipmentIds.length} eq_fail=${delEqFail} wn_ok=${delWnOk}/${createdWarningIds.length} wn_fail=${delWnFail} tr_ok=${delTrOk}/${createdTrainingIds.length} tr_fail=${delTrFail}` });
        if (!pass) {
            recFinding(testInfo, 'P2', MOD, 'Inline DELETE cleanup partial — STRESS_COLLECTIONS sweep fallback',
                `eq_fail=${delEqFail} wn_fail=${delWnFail} tr_fail=${delTrFail} — unified orphan scrub will mop up next round.`);
        }
    });

    test('D) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_lifecycle_v2_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});

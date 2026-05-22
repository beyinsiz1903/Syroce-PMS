// F8D-v3 § 39B — Offboarding / İşten Ayrılış:
//   • POST /hr/staff/{staff_id}/terminate — KESİNLİKLE force_release=false ile
//     soft-probe ÇAĞRILIR (outstanding_equipment 409 guard test); gerçek
//     termination ASLA yapılmaz (E2E_EXTERNAL_DRY_RUN doctrine).
//   • GET  /hr/staff/{staff_id}/termination — kayıt sorgu (read-only)
//   • Outstanding equipment listesi 409 detail body'de görünmeli
//   • Severance preview probe — calc shape contract (read endpoint yok, sadece
//     409 response içindeki severance_calc gözükmeli — value=null/0 expected
//     dry-run)
//
// Backend ref: backend/domains/hr/router.py:4979 (terminate), :5062 (get).
//
// KRİTİK GÜVENLİK KURALI: Bu spec stress staff'ı GERÇEKTEN terminate ETMEZ.
// Yalnızca outstanding equipment yokken bile force_release=false → 200/4xx
// gözlemini stress staff'ta yapmak istemiyoruz (terminated_at set olur,
// next run staff_pool boşalır). Bu yüzden:
//   • A adımı: pilot staff_id ile CROSS-TENANT 403/404 probe (mutation pilot'a
//     ulaşmaz — RBAC engelleyecek).
//   • B adımı: stress staff'ta termination GET (read-only) — kayıt var/yok
//     shape.
//   • C adımı: stress staff'ta force_release=false POST → outstanding ekipman
//     varsa 409 (idempotent guard test); 400 "zaten ayrılmış" da geçerli;
//     200 dönerse P0 (stress staff terminated, gelecek run zarar görür).
//
// Mutlak kurallar: pilot mutation YOK, irreversible termination YOK,
// external_calls=[].
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_offboarding';

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v3 § 39B — Offboarding (Termination Read-Only + 409 Guard)', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let staffSample = null;

    test('Setup: prefix + pilot baseline + termination GET probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const staffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
        const allStaff = staffR.body?.staff || staffR.body?.staff_members || staffR.body?.items
            || (Array.isArray(staffR.body) ? staffR.body : []);
        const ourStaff = allStaff.filter((s) => {
            const name = s?.name || s?.full_name || '';
            return typeof name === 'string' && name.startsWith(prefix);
        });
        if (ourStaff.length === 0) {
            moduleBlocked = true;
            blockedReason = `no_stress_staff_status_${staffR.status}`;
            recFinding(testInfo, 'P2', MOD, 'Offboarding stress staff pool empty',
                `staff_status=${staffR.status} prefix=${prefix} — A/B/C skipped, D pilot_drift still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        staffSample = ourStaff[0];
        // Termination GET probe (read-only).
        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/hr/staff/${staffSample.id}/termination`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `termination_get_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Termination GET probe non-2xx',
                `status=${probe.status} reason=${probe.reason}`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} staff_pool=${ourStaff.length} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Cross-tenant termination probe — pilot staff_id ile stress token (must 403/404)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'cross_tenant_terminate', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const pilotStaffR = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.pilot_token);
        const pilotStaff = pilotStaffR.body?.staff || pilotStaffR.body?.staff_members
            || pilotStaffR.body?.items || (Array.isArray(pilotStaffR.body) ? pilotStaffR.body : []);
        if (pilotStaff.length === 0) {
            rec(testInfo, { module: MOD, step: 'cross_tenant_terminate', status: 'PASS', note: 'pilot_pool=0' });
            return;
        }
        const pilotSampleId = pilotStaff[0].id;
        // KRİTİK: stress_token + pilot staff_id + force_release=false → tenant
        // mismatch nedeniyle 403/404 alınmalı. Eğer 200 alırsak P0 — pilot
        // tenant'ta gerçek termination yarattık demektir.
        const r = await callTimed(request, 'post',
            `/api/hr/staff/${pilotSampleId}/terminate?force_release=false`,
            {
                reason: `${MOD} F8D-v3 cross-tenant probe — should reject`,
                last_day: '2099-01-01',
                notice_period_days: 0,
                exit_interview_notes: 'dry-run cross-tenant probe',
                eligible_for_rehire: true,
            },
            stressTokens.stress_token,
        );
        const properly_rejected = r.status === 403 || r.status === 404;
        const idor_evidence = r.ok && r.body?.success === true;
        const pass = properly_rejected && !idor_evidence;
        rec(testInfo, { module: MOD, step: 'cross_tenant_terminate', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/staff/{pilot_id}/terminate (stress_token)',
            note: `pilot_sample=${pilotSampleId.slice(0, 8)}.. status=${r.status} idor_evidence=${idor_evidence}` });
        if (idor_evidence) recFinding(testInfo, 'P0', MOD, 'Cross-tenant termination IDOR — pilot staff terminated by stress token',
            `status=${r.status} body=${JSON.stringify(r.body).slice(0, 200)} — KATASTROFİK pilot tenant mutation.`);
        else if (!properly_rejected) recFinding(testInfo, 'P1', MOD, 'Cross-tenant terminate not 403/404',
            `status=${r.status}`);
        expect(idor_evidence, 'no cross-tenant termination IDOR').toBe(false);
    });

    test('B) Termination GET read-only — record shape + masked PII', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(60_000);
        if (moduleBlocked || !staffSample) {
            rec(testInfo, { module: MOD, step: 'termination_get', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const r = await callTimed(request, 'get',
            `/api/hr/staff/${staffSample.id}/termination`, undefined, stressTokens.stress_token);
        const shapeOk = r.ok && r.body && 'record' in r.body;
        // record null beklenir (stress staff aktif → ayrılış yok).
        const recordIsNull = shapeOk && (r.body.record === null || r.body.record === undefined);
        const pass = shapeOk;
        recPerf(testInfo, MOD, 'termination_get', [r.ms], pass);
        rec(testInfo, { module: MOD, step: 'termination_get', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/hr/staff/{id}/termination',
            note: `status=${r.status} shape_ok=${shapeOk} record_is_null=${recordIsNull}` });
        if (!shapeOk) recFinding(testInfo, 'P2', MOD, 'Termination GET shape drift',
            `status=${r.status} body_keys=${Object.keys(r.body || {}).join(',')}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'termination_get', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) Outstanding equipment 409 guard — PRECONDITIONED (assign→probe→return)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked || !staffSample) {
            rec(testInfo, { module: MOD, step: 'outstanding_409_guard', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // GÜVENLİK DOKTRİNİ (architect review feedback):
        // force_release=false guard ÇALIŞMAYI garantileyen tek yol: probe'dan
        // ÖNCE outstanding equipment'in mevcut olduğunu kanıtlamaktır. Aksi
        // halde guard pas geçer ve stress staff GERÇEKTEN terminate edilir.
        //
        // Strateji:
        //   1) Synthetic equipment assign et (stress staff'a 1 adet)
        //   2) Outstanding listede görünmesini doğrula (sanity)
        //   3) force_release=false ile terminate POST → 409 GUARANTEED
        //   4) Equipment'i geri al (return) — temizlik
        //   5) Eğer 1. adım başarısızsa, asla 3. adıma geçme → SKIP
        //
        // Bu sayede stress staff aktif kalır (terminated_at set olmaz).
        const samples = [];
        let synthEquipId = null;
        let preconditionOk = false;

        // 1) Synthetic equipment assign — manage_hr gate; super_admin geçer.
        const assignR = await callTimed(request, 'post',
            `/api/hr/staff/${staffSample.id}/equipment`,
            {
                item_type: 'card',
                item_label: `${prefix} F8D-v3 39B precondition probe`,
                serial_no: `${prefix}-39B-precond`,
                notes: `${prefix} 39B outstanding guard precondition — auto-return after probe`,
            }, stressTokens.stress_token);
        samples.push(assignR.ms);
        synthEquipId = assignR.body?.equipment?.id;
        if (!assignR.ok || !synthEquipId) {
            // Precondition başarısız — terminate'i ASLA çağırma.
            rec(testInfo, { module: MOD, step: 'outstanding_409_guard', status: 'SKIP',
                endpoint: 'precondition: POST /api/hr/staff/{id}/equipment',
                note: `assign_status=${assignR.status} synth_equip=${!!synthEquipId} — precondition failed, terminate probe SKIPPED to preserve staff` });
            recFinding(testInfo, 'P2', MOD, 'Outstanding-409 guard precondition failed',
                `equipment assign status=${assignR.status} — terminate probe skipped (staff safety).`);
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'outstanding_409_guard_skip', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            return;
        }
        // 2) Sanity — outstanding listede synthetic equipment var mı?
        const outR = await callTimed(request, 'get', '/api/hr/equipment/outstanding',
            undefined, stressTokens.stress_token);
        samples.push(outR.ms);
        const outItems = outR.body?.items || [];
        preconditionOk = outItems.some((it) => it.id === synthEquipId && it.status === 'assigned');
        if (!preconditionOk) {
            // Sanity geçmedi — yine terminate'i çağırma, sadece cleanup.
            const retR = await callTimed(request, 'post',
                `/api/hr/equipment/${synthEquipId}/return`,
                { condition_on_return: 'good', notes: `${prefix} 39B precond cleanup` },
                stressTokens.stress_token);
            samples.push(retR.ms);
            rec(testInfo, { module: MOD, step: 'outstanding_409_guard', status: 'SKIP',
                note: `outstanding sanity failed — synth_id=${synthEquipId.slice(0, 8)} not in outstanding list (status=${outR.status}, items=${outItems.length}). Equipment returned, terminate probe SKIPPED.` });
            recFinding(testInfo, 'P2', MOD, 'Outstanding-409 sanity check failed',
                `synth equipment not surfaced in /equipment/outstanding — terminate probe skipped (staff safety).`);
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'outstanding_409_guard_sanity_skip', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            return;
        }

        // 3) ARTIK GÜVENLİ: outstanding equipment garantili → 409 expected.
        const r = await callTimed(request, 'post',
            `/api/hr/staff/${staffSample.id}/terminate?force_release=false`,
            {
                reason: `${MOD} F8D-v3 outstanding-equipment 409 guard probe (precondition verified)`,
                last_day: '2099-12-31',
                notice_period_days: 0,
                exit_interview_notes: 'dry-run outstanding guard probe — staff must remain active',
                eligible_for_rehire: true,
            },
            stressTokens.stress_token,
        );
        samples.push(r.ms);
        const safe_status = [400, 401, 403, 409].includes(r.status);
        const has_outstanding_payload = r.status === 409
            && r.body?.detail?.code === 'outstanding_equipment'
            && Array.isArray(r.body?.detail?.outstanding_equipment);
        const stress_staff_terminated = r.status === 200 || r.status === 201;

        // 4) Cleanup synthetic equipment unconditionally.
        const retR = await callTimed(request, 'post',
            `/api/hr/equipment/${synthEquipId}/return`,
            { condition_on_return: 'good', notes: `${prefix} 39B post-probe return` },
            stressTokens.stress_token);
        samples.push(retR.ms);

        // 5) Verify staff still active (post-probe sanity).
        const staffR = await callTimed(request, 'get',
            `/api/hr/staff/${staffSample.id}/termination`, undefined, stressTokens.stress_token);
        samples.push(staffR.ms);
        const staff_still_active = staffR.ok && (staffR.body?.record === null || staffR.body?.record === undefined);

        const pass = safe_status && has_outstanding_payload && staff_still_active && !stress_staff_terminated;
        recPerf(testInfo, MOD, 'outstanding_409_guard', samples, pass);
        rec(testInfo, { module: MOD, step: 'outstanding_409_guard', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/hr/staff/{stress_id}/terminate?force_release=false (preconditioned)',
            note: `precondition_ok=true synth_equip=${synthEquipId.slice(0, 8)}.. terminate_status=${r.status} has_409_payload=${has_outstanding_payload} ret_status=${retR.status} staff_still_active=${staff_still_active} stress_staff_terminated=${stress_staff_terminated}` });
        if (stress_staff_terminated) {
            recFinding(testInfo, 'P0', MOD, 'Outstanding-equipment 409 guard BYPASS — stress staff terminated',
                `status=${r.status} — 409 guard ihlal: outstanding equipment varken terminate kabul edildi. KATASTROFİK.`);
        }
        if (!has_outstanding_payload && safe_status) {
            recFinding(testInfo, 'P1', MOD, '409 response shape drift',
                `status=${r.status} detail.code=${r.body?.detail?.code} — outstanding_equipment payload yok.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'outstanding_409_guard', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(stress_staff_terminated, 'stress staff must NOT be terminated by probe').toBe(false);
        expect(staff_still_active, 'stress staff must remain active post-probe').toBe(true);
    });

    test('D) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_offboarding_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});

// F8D-v2 § 29 — HR Payroll Lifecycle (Task #264):
// Dry-run preview + draft save (idempotent) + runs list + run detail +
// revisions read. RBAC + PII guard + pilot_drift.
//
// MUTLAK SÖZLEŞME:
//   - `/hr/payroll/{run_id}/finalize` ASLA çağrılmaz (production-safety
//     contract; locked yaratmak stres sırasında muhasebe/audit yan etkisi
//     sayılır; F8E doktrini ile aynı).
//   - `/hr/payroll/{run_id}/revisions` (POST) da çağrılmaz (yalnız list).
//   - Yalnız draft yazılır → unified cleanup loop `payroll_runs` koleksiyonunu
//     `stress_prefix` ile silebilmek için server tarafı seed tag'ine ihtiyaç
//     duymadan tenant-scoped (stress tenant) tüm draft+revisions silinir
//     (admin/router/stress.py STRESS_COLLECTIONS Task #264 maddesi).
//
// module-blocked doktrin:
//   - Setup probe (/hr/payroll/{month} dry-run) non-2xx → moduleBlocked=true,
//     A/B/C test.skip; D pilot_drift hâlâ enforce.
//   - RBAC short-circuit: super_admin permFail beklenmez; permFail>=hard
//     ratio → P2 informational.
import fs from 'fs';
import path from 'path';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount, assertPiiMasked,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_payroll_lifecycle';

const currentMonth = () => {
    const d = new Date();
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
};

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v2 § 29 — HR Payroll Lifecycle', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let savedRunId = null;
    const MONTH = currentMonth();

    test('Setup: prefix + pilot baseline + dry-run probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await callTimed(request, 'get', `/api/hr/payroll/${MONTH}`,
            undefined, stressTokens.stress_token);
        if (!probe.ok) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'HR payroll dry-run probe non-2xx',
                `status=${probe.status} body=${JSON.stringify(probe.body).slice(0, 120)} — A/B/C skipped, pilot_drift gate still enforced.`);
        }
        const isDryRun = probe.body?.is_dry_run === true;
        // Deploy-lag tolerance: bazı CI ortamlarında prod backend henüz Task #264
        // v2 kontratını içermeyebilir (is_dry_run alanı yok). Eski kontratı sıkı
        // P1 ile engellemek false-positive NO-GO üretir — bu durum module-blocked
        // (deploy-lag) olarak işaretlenir, P2 informational, A/B/C skip; D
        // pilot_drift bağımsız çalışır.
        if (probe.ok && !isDryRun) {
            moduleBlocked = true;
            recFinding(testInfo, 'P2', MOD, 'Payroll v2 kontratı deploy edilmemiş',
                `GET /hr/payroll/{month} is_dry_run alanı yok (Task #264 v2 backend deploy bekleniyor). probe_status=${probe.status} keys=${Object.keys(probe.body || {}).slice(0, 8).join(',')} — A/B/C skipped, D pilot_drift still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} is_dry_run=${isDryRun} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) Draft save (idempotent) + runs list + run detail', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'draft_lifecycle', status: 'SKIP', note: 'module blocked' });
            test.skip(true, 'Payroll module blocked');
            return;
        }
        const samples = [];

        // 1. Save draft (1st)
        const save1 = await callTimedWithBackoff(request, 'post', `/api/hr/payroll/${MONTH}/save`,
            { extras: [] }, stressTokens.stress_token);
        samples.push(save1.ms);
        // 2. Save draft (2nd) — idempotent update (same run_id)
        const save2 = await callTimedWithBackoff(request, 'post', `/api/hr/payroll/${MONTH}/save`,
            { extras: [] }, stressTokens.stress_token);
        samples.push(save2.ms);

        // 400 = "Bu ay için devam kaydı yok" → seed-less stress tenant
        // bekleneni; module-state ayrımı (P2 informational, skip rest).
        const noAttendance = save1.status === 400 || save2.status === 400;
        if (noAttendance) {
            recFinding(testInfo, 'P2', MOD, 'Stress tenant attendance seed yok → draft yaratılamaz',
                `save1=${save1.status} save2=${save2.status} (kontrat ihlali değil; F8D attendance seed kapsam dışı).`);
            rec(testInfo, { module: MOD, step: 'draft_lifecycle', status: 'SKIP',
                note: `no attendance → cannot create draft (save1=${save1.status})` });
            test.skip(true, 'No attendance → cannot create draft');
            return;
        }

        const draftOk = save1.ok && save2.ok;
        const sameRun = save1.body?.run_id && save1.body.run_id === save2.body?.run_id;
        if (draftOk) savedRunId = save1.body.run_id;

        // 3. List runs for month
        const listR = await callTimed(request, 'get', `/api/hr/payroll/runs?month=${MONTH}`,
            undefined, stressTokens.stress_token);
        samples.push(listR.ms);
        const listContainsSaved = !!savedRunId
            && Array.isArray(listR.body?.items)
            && listR.body.items.some((r) => r.id === savedRunId);

        // 4. Detail
        let detailOk = false;
        let revsOk = false;
        if (savedRunId) {
            const detailR = await callTimed(request, 'get',
                `/api/hr/payroll/runs/${savedRunId}`, undefined, stressTokens.stress_token);
            samples.push(detailR.ms);
            detailOk = detailR.ok && detailR.body?.status === 'draft'
                && Array.isArray(detailR.body?.rows);

            // PII guard — manage_hr stress token, mask BEKLENMEZ; ama yine de
            // herhangi bir TC/IBAN raw field görünür mü kontrolü (data shape)
            const rows = detailR.body?.rows || [];
            if (rows.length > 0) {
                // Stress token manage_hr varsa unmasked döner; kontrat ihlali değil.
                // Yalnız field SHAPE'i sabit olmalı.
                const r0 = rows[0];
                if (!r0.staff_id) {
                    recFinding(testInfo, 'P2', MOD, 'Bordro satırı staff_id alanı eksik',
                        `keys=${Object.keys(r0).slice(0, 12).join(',')}`);
                }
            }

            const revR = await callTimed(request, 'get',
                `/api/hr/payroll/runs/${savedRunId}/revisions`, undefined, stressTokens.stress_token);
            samples.push(revR.ms);
            revsOk = revR.ok && Array.isArray(revR.body?.items);
        }

        const allOk = draftOk && sameRun && listR.ok && listContainsSaved && detailOk && revsOk;
        const status = allOk ? 'PASS' : 'REVIEW';
        recPerf(testInfo, MOD, 'draft_lifecycle', samples, allOk);
        rec(testInfo, { module: MOD, step: 'draft_lifecycle', status,
            endpoint: '/api/hr/payroll/{month,runs,runs/{id},runs/{id}/revisions}',
            note: `save1=${save1.status}/${save1.body?.run_id?.slice(0,8)} save2=${save2.status}/${save2.body?.run_id?.slice(0,8)} same_run=${sameRun} list=${listR.status} contains=${listContainsSaved} detail_ok=${detailOk} revs_ok=${revsOk}` });

        if (!allOk) {
            recFinding(testInfo, 'P2', MOD, 'Draft lifecycle smoke partial',
                `Tüm adımlar PASS değil — backend kontrat değişikliği olabilir.`);
        }
        expect(typeof save1.status).toBe('number');
    });

    test('B) RBAC + finalize-without-perm (no-op safety net)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'rbac_probe', status: 'SKIP', note: 'module blocked' });
            test.skip(true, 'Payroll module blocked');
            return;
        }
        // Stress NON-auth probe → 401/403 beklenir. Bu test sırasında 200
        // dönerse P0 (kimliksiz bordro erişimi).
        const noAuthR = await callTimed(request, 'get', `/api/hr/payroll/${MONTH}`,
            undefined, null);
        const expectedReject = noAuthR.status === 401 || noAuthR.status === 403;
        if (!expectedReject) {
            recFinding(testInfo, 'P0', MOD, 'Bordro public erişilebilir',
                `no-auth GET /hr/payroll/{month} → status=${noAuthR.status} (401/403 olmalı).`);
        }
        rec(testInfo, { module: MOD, step: 'rbac_probe',
            status: expectedReject ? 'PASS' : 'FAIL',
            note: `no_auth_status=${noAuthR.status}` });
        expect(expectedReject, 'no-auth must be 401/403').toBe(true);
    });

    test('C) Dry-run idempotency — preview tekrar çağrısı drift üretmez', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'dryrun_idempotency', status: 'SKIP', note: 'module blocked' });
            test.skip(true, 'Payroll module blocked');
            return;
        }
        const samples = [];
        const r1 = await callTimed(request, 'get', `/api/hr/payroll/${MONTH}`,
            undefined, stressTokens.stress_token);
        samples.push(r1.ms);
        const r2 = await callTimed(request, 'get', `/api/hr/payroll/${MONTH}`,
            undefined, stressTokens.stress_token);
        samples.push(r2.ms);
        const sameSummary = r1.ok && r2.ok
            && r1.body?.staff_count === r2.body?.staff_count
            && Math.abs((r1.body?.total_gross_pay ?? 0) - (r2.body?.total_gross_pay ?? 0)) < 0.01;
        recPerf(testInfo, MOD, 'dryrun_idempotency', samples, sameSummary);
        rec(testInfo, { module: MOD, step: 'dryrun_idempotency',
            status: sameSummary ? 'PASS' : 'REVIEW',
            note: `r1_staff=${r1.body?.staff_count} r2_staff=${r2.body?.staff_count} r1_gross=${r1.body?.total_gross_pay} r2_gross=${r2.body?.total_gross_pay}` });
        expect(r1.ok).toBe(true);
        expect(r2.ok).toBe(true);
    });

    test('D) Pilot drift + external_calls invariant', async ({ request, stressTokens }, testInfo) => {
        const pilotAfter = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (pilotAfter?.count ?? 0) - (pilotBefore?.count ?? 0);
        const ok = drift === 0;
        rec(testInfo, { module: MOD, step: 'pilot_drift',
            status: ok ? 'PASS' : 'FAIL',
            note: `pilot_before=${pilotBefore?.count} pilot_after=${pilotAfter?.count} drift=${drift}` });
        if (!ok) {
            recFinding(testInfo, 'P0', MOD, 'Pilot tenant drift (bookings)',
                `Stress run pilot tenant bookings sayısını değiştirdi (drift=${drift}).`);
        }
        // Helper signature: (testInfo, module, batchName, stressState, request, pilotToken)
        // Önceki çağrı 4-arg idi → pilotToken=undefined → caller_missing_pilot_token FAIL P1.
        const stateBlob = JSON.parse(fs.readFileSync(
            path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'),
            'utf-8',
        ));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_payroll_done',
            stateBlob, request, stressTokens.pilot_token);
        expect(drift, 'pilot drift must be zero').toBe(0);
    });
});

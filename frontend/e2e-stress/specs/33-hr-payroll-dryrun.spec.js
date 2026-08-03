// F8D-v2 § 33 — HR Payroll Dry-run Stress.
//
// Scope: backlog item "Payroll smoke" — calculate dry-run + export preview;
// kalıcı insert eden FORBIDDEN endpoint ASLA tetiklenmez. v1 spec'lerde
// payroll hiç dokunulmadı.
//
// Covered endpoints (READ-only):
//   • GET  /api/hr/payroll/{month}        — finalized records lookup
//   • GET  /api/hr/payroll/export         — JSON preview (dry-run calc)
//   • GET  /api/hr/payroll/export/csv     — CSV stream preview
//
// FORBIDDEN doctrine: payroll write/finalize endpoint'i bu spec dosyasında
// HİÇBİR ŞEKİLDE literal olarak yer almaz — ne yorum içinde, ne string
// içinde, ne regex içinde. Helper modülünden import edilen
// `FORBIDDEN_HR_PAYROLL_FINALIZE` sabit ismi referans olarak kullanılır;
// sabitin değeri helper içinde string concat ile inşa edilir, böylece
// substring olarak spec source'unda hiç görünmez. `assertEndpointNeverCalled`
// source-scan guard'ı bu invariant'ı her run'da doğrular (FAIL P0 →
// substring spec içinde bulundu).
//
// Mutlak kurallar:
//   - failedTests=0, P0=P1=0
//   - external_calls=[]
//   - pilot_drift=0 (read-only)
//   - payroll_records koleksiyonuna spec write YOK

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertNoTokenLeak,
    assertEndpointNeverCalled, FORBIDDEN_HR_PAYROLL_FINALIZE,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_payroll';

function currentMonth() {
    const d = new Date();
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v2 § 33 — HR Payroll Dry-run', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    const MONTH = currentMonth();

    test('Setup: prefix + pilot baseline + payroll export probe + FORBIDDEN source-scan guard', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // FORBIDDEN guard — helper source-scan: spec dosyasının kendisi
        // yasak URL substring'ini literal olarak içermemeli. Helper sabiti
        // ismen referans, değer string concat (helper).
        const guardOk = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_HR_PAYROLL_FINALIZE);

        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/hr/payroll/export?month=${MONTH}`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `payroll_export_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Payroll export probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped, E pilot_drift still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: guardOk ? 'PASS' : 'FAIL',
            note: `prefix=${prefix} month=${MONTH} pilot_before=${pilotBefore?.count} probe_status=${probe.status} forbidden_guard_clean=${guardOk} module_blocked=${moduleBlocked}` });
        // Hard assert: source-scan ihlali → suite fail.
        expect(guardOk, 'spec source FORBIDDEN substring guard').toBe(true);
    });

    test('A) GET /hr/payroll/{month} — finalized records lookup (read-only)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'lookup_month', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimed(request, 'get',
            `/api/hr/payroll/${MONTH}`, undefined, stressTokens.stress_token);
        samples.push(r.ms);
        recPerf(testInfo, MOD, 'lookup_month', samples, r.ok);
        const payrollList = r.body?.payroll || [];
        const shapeOk = r.ok && typeof r.body === 'object'
            && Array.isArray(payrollList)
            && 'count' in r.body && 'total_gross' in r.body;
        // HARD-ASSERT numeric typing (architect iter-3): count + total_gross
        // + total_net response'da MUTLAKA number (financial response shape
        // contract). String/null/undefined → P1 + FAIL.
        const numericFields = r.ok ? ['count', 'total_gross', 'total_net'] : [];
        const numericDrift = numericFields.filter((f) => typeof r.body?.[f] !== 'number');
        const numericOk = r.ok ? numericDrift.length === 0 : true;
        rec(testInfo, { module: MOD, step: 'lookup_month',
            status: (shapeOk && numericOk) ? 'PASS' : 'REVIEW',
            endpoint: `/api/hr/payroll/{month}`, http: r.status,
            note: `status=${r.status} count=${r.body?.count} total_gross=${r.body?.total_gross} total_net=${r.body?.total_net} numeric_drift=${numericDrift.join('|') || 'none'}` });
        if (!r.ok) recFinding(testInfo, 'P2', MOD, 'Payroll month-lookup non-2xx', `status=${r.status}`);
        if (r.ok && !shapeOk) recFinding(testInfo, 'P2', MOD, 'Payroll month-lookup shape drift',
            `body keys=${Object.keys(r.body || {}).join(',')}`);
        if (r.ok && !numericOk) recFinding(testInfo, 'P1', MOD,
            'Payroll month-lookup numeric type drift',
            `non-numeric fields=${numericDrift.join('|')} body=${JSON.stringify({c: r.body?.count, tg: r.body?.total_gross, tn: r.body?.total_net})}`);
        if (r.ok) assertNoTokenLeak(testInfo, MOD, r.body, 'payroll_month_lookup');
        expect(numericOk,
            `payroll numeric contract: count/total_gross/total_net typeof === 'number'. drift=${numericDrift.join('|')}`).toBe(true);
    });

    test('B) GET /hr/payroll/export — JSON dry-run preview', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'export_json', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimed(request, 'get',
            `/api/hr/payroll/export?month=${MONTH}`, undefined, stressTokens.stress_token);
        samples.push(r.ms);
        recPerf(testInfo, MOD, 'export_json', samples, r.ok);
        const payrollList = r.body?.payroll || [];
        const shapeOk = r.ok && Array.isArray(payrollList)
            && 'staff_count' in r.body && 'total_gross_pay' in r.body && 'total_net_pay' in r.body;
        // HARD-ASSERT numeric typing (architect iter-3): export response
        // staff_count + total_gross_pay + total_net_pay number olmalı.
        const numericFieldsX = r.ok ? ['staff_count', 'total_gross_pay', 'total_net_pay'] : [];
        const numericDriftX = numericFieldsX.filter((f) => typeof r.body?.[f] !== 'number');
        const numericOkX = r.ok ? numericDriftX.length === 0 : true;
        rec(testInfo, { module: MOD, step: 'export_json',
            status: (shapeOk && numericOkX) ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/payroll/export', http: r.status,
            note: `status=${r.status} staff_count=${r.body?.staff_count} total_gross=${r.body?.total_gross_pay} rows=${payrollList.length} period=${r.body?.period} numeric_drift=${numericDriftX.join('|') || 'none'}` });
        if (!r.ok) recFinding(testInfo, 'P2', MOD, 'Payroll export non-2xx', `status=${r.status}`);
        if (r.ok && !shapeOk) recFinding(testInfo, 'P2', MOD, 'Payroll export shape drift',
            `body keys=${Object.keys(r.body || {}).join(',')}`);
        if (r.ok && !numericOkX) recFinding(testInfo, 'P1', MOD,
            'Payroll export numeric type drift',
            `non-numeric fields=${numericDriftX.join('|')}`);
        if (r.ok) assertNoTokenLeak(testInfo, MOD, r.body, 'payroll_export_json');
        expect(numericOkX,
            `payroll export numeric contract: staff_count/total_gross_pay/total_net_pay typeof === 'number'. drift=${numericDriftX.join('|')}`).toBe(true);
    });

    test('C) GET /hr/payroll/export/csv — CSV stream preview', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'export_csv', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const t0 = Date.now();
        const r = await request.get(`/api/hr/payroll/export/csv?month=${MONTH}`, {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false, timeout: 30_000,
        });
        const ms = Date.now() - t0;
        const ct = r.headers()['content-type'] || '';
        const cd = r.headers()['content-disposition'] || '';
        const body = await r.text();
        const looksLikeCsv = /text\/csv|application\/octet-stream/i.test(ct)
            || /attachment.*\.csv/i.test(cd);
        const pass = r.ok() && looksLikeCsv && body.length > 0;
        recPerf(testInfo, MOD, 'export_csv', [ms], pass);
        rec(testInfo, { module: MOD, step: 'export_csv',
            status: pass ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/payroll/export/csv', http: r.status(),
            note: `status=${r.status()} ms=${ms} ct=${ct} cd=${cd.slice(0, 80)} body_len=${body.length} csv_marker=${looksLikeCsv}` });
        if (!r.ok()) recFinding(testInfo, 'P2', MOD, 'Payroll CSV export non-2xx', `status=${r.status()}`);
        // Token leak in CSV bytes
        if (r.ok() && /eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/.test(body)) {
            recFinding(testInfo, 'P0', MOD, 'JWT leak inside payroll CSV stream',
                `CSV body contains JWT-shaped token; finance export PII/token guard fail.`);
        }
    });

    test('D) FORBIDDEN doctrine — runtime invariant (helper-constant referenced, literal NEVER in source)', async ({ request, stressTokens }, testInfo) => {
        // Re-assert source-scan invariant: helper sabit isimle referansta
        // bulundu (üstte import edildi) ama literal substring spec source'unda
        // hiç geçmemeli. Bu test sadece doctrine'i kayıt altına alır + ikincil
        // guard çağrısı yapar; herhangi bir HTTP call yapmaz.
        const guardOk = assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_HR_PAYROLL_FINALIZE);
        rec(testInfo, { module: MOD, step: 'forbidden_doctrine_runtime',
            status: guardOk ? 'PASS' : 'FAIL',
            note: `helper_const_name=FORBIDDEN_HR_PAYROLL_FINALIZE source_clean=${guardOk}. Doctrine: yasak endpoint dry-run/preview/CSV path'lerinden bağımsız olarak NEVER called from F8D-v2 § 33.` });
        expect(guardOk, 'forbidden source-scan doctrine').toBe(true);
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_payroll_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});

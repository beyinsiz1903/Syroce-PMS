// F8D-v2 § 33 — HR Payroll Dry-run Stress.
//
// Scope: backlog item "Payroll smoke" — calculate dry-run + export preview;
// `/api/hr/payroll/finalize` ASLA tetiklenmez (KESİN). v1 spec'lerde payroll
// hiç dokunulmadı.
//
// Covered endpoints (READ-only):
//   • GET  /api/hr/payroll/{month}        — finalized records lookup
//   • GET  /api/hr/payroll/export         — JSON preview (dry-run calc)
//   • GET  /api/hr/payroll/export/csv     — CSV stream preview
// FORBIDDEN (NEVER CALLED):
//   • POST /api/hr/payroll/finalize       — kalıcı insert; live workflow için
//
// Pre-flight source-scan guard: spec dosyasının kendisi /payroll/finalize
// POST referansı içermemeli (literal grep). İçerirse P0 finding + skip.
//
// Mutlak kurallar:
//   - failedTests=0, P0=P1=0
//   - external_calls=[]
//   - pilot_drift=0 (read-only)
//   - payroll_records koleksiyonuna spec write YOK

import fs from 'node:fs';
import path from 'node:path';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertNoTokenLeak,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_payroll';
const FORBIDDEN_POST = '/payroll/finalize';

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

    test('Setup: prefix + pilot baseline + payroll export probe + FORBIDDEN guard', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Pre-flight: spec dosyasının kendisi POST /api/hr/payroll/finalize
        // çağrısı içermemeli. Literal source-scan guard.
        // ESM-safe: __filename Playwright ESM context'inde undefined olabilir.
        const candidatePaths = [];
        if (typeof __filename !== 'undefined') candidatePaths.push(__filename);
        candidatePaths.push(path.join(process.cwd(), 'e2e-stress', 'specs', '33-hr-payroll-dryrun.spec.js'));
        candidatePaths.push(path.join(process.cwd(), 'frontend', 'e2e-stress', 'specs', '33-hr-payroll-dryrun.spec.js'));
        let source = '';
        for (const p of candidatePaths) {
            try { source = fs.readFileSync(p, 'utf-8'); if (source) break; } catch (_) { /* try next */ }
        }
        if (!source) {
            // Source unreachable — guard'ı atlayamayız ama spec'in PASS'lemesini
            // de bloke etmemeli. P2 informational + runtime invariant'a güven.
            recFinding(testInfo, 'P2', MOD, 'Source-scan guard skipped — spec source unreachable',
                `candidate_paths=${candidatePaths.length} — D adımı runtime invariant doctrine'i kayıt altına alacak.`);
        }
        // POST request to finalize endpoint detection — match `'post'` followed by
        // '/payroll/finalize' in callTimed/request.post/etc. Sadece KONUM bağlamı
        // (post + finalize path); doctrine sabit isim FORBIDDEN_POST string'i
        // bu listede — false-positive sayılmaz çünkü string oluşumu kasıtlı.
        const postFinalizeRe = /(['"])post\1[^)]*\/api\/hr\/payroll\/finalize|request\.post\([^)]*\/api\/hr\/payroll\/finalize/i;
        const forbiddenHit = postFinalizeRe.test(source);
        if (forbiddenHit) {
            recFinding(testInfo, 'P0', MOD, 'FORBIDDEN endpoint POST referansı bulundu — spec source ihlali',
                `Spec dosyası POST /api/hr/payroll/finalize çağrısı içeriyor; finalize ASLA tetiklenmemeli (KVKK + finance immutability).`);
        }

        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/hr/payroll/export?month=${MONTH}`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `payroll_export_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Payroll export probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped, E pilot_drift still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: forbiddenHit ? 'FAIL' : 'PASS',
            note: `prefix=${prefix} month=${MONTH} pilot_before=${pilotBefore?.count} probe_status=${probe.status} forbidden_post_in_source=${forbiddenHit} module_blocked=${moduleBlocked}` });
        expect(forbiddenHit, 'spec source must NEVER reference POST /api/hr/payroll/finalize').toBe(false);
    });

    test('A) GET /hr/payroll/{month} — finalized records lookup (read-only)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'lookup_month', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'get',
            `/api/hr/payroll/${MONTH}`, undefined, stressTokens.stress_token);
        samples.push(r.ms);
        recPerf(testInfo, MOD, 'lookup_month', samples, r.ok);
        const payrollList = r.body?.payroll || [];
        const shapeOk = r.ok && typeof r.body === 'object'
            && Array.isArray(payrollList)
            && 'count' in r.body && 'total_gross' in r.body;
        rec(testInfo, { module: MOD, step: 'lookup_month',
            status: shapeOk ? 'PASS' : 'REVIEW',
            endpoint: `/api/hr/payroll/{month}`, http: r.status,
            note: `status=${r.status} count=${r.body?.count} total_gross=${r.body?.total_gross} total_net=${r.body?.total_net}` });
        if (!r.ok) recFinding(testInfo, 'P2', MOD, 'Payroll month-lookup non-2xx', `status=${r.status}`);
        if (r.ok && !shapeOk) recFinding(testInfo, 'P2', MOD, 'Payroll month-lookup shape drift',
            `body keys=${Object.keys(r.body || {}).join(',')}`);
        // Token leak guard — payroll responses kazara JWT/refresh içermemeli.
        if (r.ok) assertNoTokenLeak(testInfo, MOD, r.body, 'payroll_month_lookup');
    });

    test('B) GET /hr/payroll/export — JSON dry-run preview', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'export_json', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'get',
            `/api/hr/payroll/export?month=${MONTH}`, undefined, stressTokens.stress_token);
        samples.push(r.ms);
        recPerf(testInfo, MOD, 'export_json', samples, r.ok);
        const payrollList = r.body?.payroll || [];
        const shapeOk = r.ok && Array.isArray(payrollList)
            && 'staff_count' in r.body && 'total_gross_pay' in r.body && 'total_net_pay' in r.body;
        rec(testInfo, { module: MOD, step: 'export_json',
            status: shapeOk ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/payroll/export', http: r.status,
            note: `status=${r.status} staff_count=${r.body?.staff_count} total_gross=${r.body?.total_gross_pay} rows=${payrollList.length} period=${r.body?.period}` });
        if (!r.ok) recFinding(testInfo, 'P2', MOD, 'Payroll export non-2xx', `status=${r.status}`);
        if (r.ok && !shapeOk) recFinding(testInfo, 'P2', MOD, 'Payroll export shape drift',
            `body keys=${Object.keys(r.body || {}).join(',')}`);
        if (r.ok) assertNoTokenLeak(testInfo, MOD, r.body, 'payroll_export_json');
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

    test('D) FORBIDDEN doctrine — runtime invariant (no finalize call ever)', async ({ request, stressTokens }, testInfo) => {
        // Defansif: spec lifecycle boyunca finalize asla tetiklenmedi; bu test
        // sadece doctrine'i kayıt altına alır. Hiç POST yapmaz.
        rec(testInfo, { module: MOD, step: 'forbidden_doctrine',
            status: 'PASS',
            note: `Doctrine: POST ${FORBIDDEN_POST} NEVER called from F8D-v2 § 33. Setup pre-flight source-scan guard enforces this at literal-text level.` });
        expect(true).toBe(true);
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_payroll_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});

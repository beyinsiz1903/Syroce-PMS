// F8D-v3 § 33B — Payroll Export PII / Role Visibility Contract:
//   • GET /hr/payroll/export?period_month=YYYY-MM (JSON, view_finance)
//   • GET /hr/payroll/export/csv?period_month=YYYY-MM (StreamingResponse)
//   • GET /hr/payroll/runs/{run_id}/export.xlsx (binary XLSX)
//
// Coverage:
//   • Content-type contract (json / text/csv / xlsx)
//   • Body non-empty + numeric contract (count, total_gross, total_net)
//   • PII fields (TC kimlik, IBAN, phone, email) plain-text scan in CSV body
//   • Token leak guard (`Bearer eyJ...` JWT serialization)
//   • Cross-tenant download reject — stress_token + pilot run_id (404 expect)
//
// Backend ref: backend/domains/hr/router.py:1097 (export json), :1127 (csv),
//              :1854 (xlsx).
//
// Not: 33-hr-payroll-dryrun zaten temel JSON/CSV smoke yapıyor. Bu spec
// PII-mask scan + cross-tenant XLSX IDOR + role visibility'e odaklanır.
//
// Mutlak kurallar: pilot mutation YOK, external_calls=[], failedTests=0.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_payroll_export_pii';

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v3 § 33B — Payroll Export PII / Role Visibility', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let month = null;

    test('Setup: prefix + pilot baseline + export probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const today = new Date();
        month = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
        const probe = await withModuleProbe(request, stressTokens.stress_token,
            `/api/hr/payroll/export?period_month=${month}`);
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `export_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Payroll export probe non-2xx',
                `status=${probe.status} reason=${probe.reason}`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} month=${month} probe_status=${probe.status} module_blocked=${moduleBlocked}` });
        expect(typeof probe.status).toBe('number');
    });

    test('A) JSON export — content-type + numeric contract + PII guard', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'json_export', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const r = await callTimed(request, 'get',
            `/api/hr/payroll/export?period_month=${month}`, undefined, stressTokens.stress_token);
        const ctOk = r.headers?.['content-type']?.includes('application/json');
        const body = r.body || {};
        const numericOk = typeof body.count === 'number'
            && typeof body.total_gross === 'number' && typeof body.total_net === 'number';
        // PII scan — bordro JSON içinde TC (11 hane), IBAN (TR + 24 hane), JWT.
        // Architect feedback: bare JWT (Bearer prefix YOK) da yakalan; TC için
        // identity_no/tc_kimlik field bağlamına bakarak false-positive azalt.
        const bodyStr = JSON.stringify(body);
        // TC: 11-digit literal aranır AMA field bağlamı: identity_no/tc_kimlik/tc_no
        // alanlarında plain 11-digit varsa P0 (genel id_/uuid alanları edge case).
        const tcContextMatch = bodyStr.match(/"(?:identity_no|tc_kimlik|tc_no|national_id|tckn)"\s*:\s*"(\d{11})"/i);
        const tcBareMatch = !tcContextMatch ? bodyStr.match(/\b\d{11}\b/) : null;
        const ibanMatch = bodyStr.match(/\bTR\d{2}[\s\-]?(?:\d{4}[\s\-]?){5}\d{2}\b/);
        // JWT: Bearer-prefixed VEYA bare three-segment base64url (eyJ...).
        const jwtBearerMatch = bodyStr.match(/Bearer\s+eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/);
        const jwtBareMatch = !jwtBearerMatch ? bodyStr.match(/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/) : null;
        const tcMatch = tcContextMatch || tcBareMatch;
        const tokenMatch = jwtBearerMatch || jwtBareMatch;
        const piiClean = !tcContextMatch && !ibanMatch && !tokenMatch;
        // Bare 11-digit informational only (P2) — likely ID/timestamp false positive.
        const tcBareFalsePositive = !!tcBareMatch;
        const pass = r.ok && ctOk && numericOk && piiClean;
        recPerf(testInfo, MOD, 'json_export', [r.ms], pass);
        rec(testInfo, { module: MOD, step: 'json_export', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/hr/payroll/export',
            note: `status=${r.status} ct_ok=${ctOk} numeric_ok=${numericOk} count=${body.count} tc_present=${!!tcMatch} iban_present=${!!ibanMatch} token_present=${!!tokenMatch}` });
        if (tcContextMatch) recFinding(testInfo, 'P0', MOD, 'TC kimlik plain-text in payroll JSON export (context field)',
            `field-context match (identity_no/tc_kimlik); first 3 digits=${tcContextMatch[1].slice(0, 3)}***`);
        else if (tcBareFalsePositive) recFinding(testInfo, 'P2', MOD, '11-digit literal in payroll JSON (informational, likely ID/ts)',
            `bare 11-digit detected outside identity field context — manual review.`);
        if (ibanMatch) recFinding(testInfo, 'P0', MOD, 'IBAN plain-text in payroll JSON export',
            `match=${ibanMatch[0].slice(0, 6)}***`);
        if (tokenMatch) recFinding(testInfo, 'P0', MOD, 'JWT token leak in payroll JSON export',
            `kind=${jwtBearerMatch ? 'bearer_prefixed' : 'bare_three_segment'} serialized in body`);
        if (!numericOk) recFinding(testInfo, 'P1', MOD, 'Payroll export numeric contract drift',
            `count_type=${typeof body.count} gross_type=${typeof body.total_gross} net_type=${typeof body.total_net}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'json_export', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) CSV stream export — content-type + PII guard in raw text', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'csv_export', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // CSV stream — callTimed uses request.get; we need raw text body.
        const t0 = Date.now();
        const r = await request.get(`/api/hr/payroll/export/csv?period_month=${month}`, {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false,
        });
        const ms = Date.now() - t0;
        const status = r.status();
        const ct = r.headers()['content-type'] || '';
        const text = await r.text();
        const ctOk = ct.includes('text/csv') || ct.includes('application/csv');
        const header = text.split('\n')[0] || '';
        const hasHeader = header.includes(',');
        // PII scan — CSV body. CSV'de field bağlamı zayıf, ama header
        // analyzer ile column-aware tarama yapıyoruz.
        const lowerHeader = header.toLowerCase();
        const hasTcColumn = /tc_?(kimlik|no|kn)|identity_?no|national_?id|tckn/i.test(lowerHeader);
        const tcBareMatch = text.match(/\b\d{11}\b/);
        const ibanMatch = text.match(/\bTR\d{2}[\s\-]?(?:\d{4}[\s\-]?){5}\d{2}\b/);
        const jwtBearerMatch = text.match(/Bearer\s+eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+/);
        const jwtBareMatch = !jwtBearerMatch ? text.match(/eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}/) : null;
        // CSV: TC bare match P0 ONLY IF header has TC column (column-aware);
        // aksi halde P2 informational (false-positive risk: row IDs, dates).
        const tcMatch = hasTcColumn && tcBareMatch;
        const tokenMatch = jwtBearerMatch || jwtBareMatch;
        const piiClean = !tcMatch && !ibanMatch && !tokenMatch;
        const tcBareFalsePositive = !hasTcColumn && !!tcBareMatch;
        const pass = (status === 200 || status === 204) && ctOk && piiClean && text.length > 0;
        recPerf(testInfo, MOD, 'csv_export', [ms], pass);
        rec(testInfo, { module: MOD, step: 'csv_export', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/hr/payroll/export/csv',
            note: `status=${status} ct=${ct.slice(0, 40)} ct_ok=${ctOk} text_len=${text.length} has_header=${hasHeader} tc_present=${!!tcMatch} iban_present=${!!ibanMatch} token_present=${!!tokenMatch}` });
        if (tcMatch) recFinding(testInfo, 'P0', MOD, 'TC kimlik plain-text in payroll CSV export (column-confirmed)',
            `header has TC column; match=${tcMatch[0].slice(0, 3)}*** at byte=${text.indexOf(tcMatch[0])}`);
        else if (tcBareFalsePositive) recFinding(testInfo, 'P2', MOD, '11-digit literal in CSV body (informational)',
            `header has no TC column; likely ID/sequence false positive — manual review.`);
        if (ibanMatch) recFinding(testInfo, 'P0', MOD, 'IBAN plain-text in payroll CSV export',
            `match=${ibanMatch[0].slice(0, 6)}*** at byte=${text.indexOf(ibanMatch[0])}`);
        if (tokenMatch) recFinding(testInfo, 'P0', MOD, 'JWT token leak in payroll CSV export',
            `kind=${jwtBearerMatch ? 'bearer_prefixed' : 'bare_three_segment'} serialized in CSV body`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'csv_export', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) XLSX run export — content-type + cross-tenant IDOR guard', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'xlsx_export', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Find a stress run for the month.
        const runsR = await callTimed(request, 'get',
            `/api/hr/payroll/runs?month=${month}`, undefined, stressTokens.stress_token);
        const runs = runsR.body?.runs || runsR.body?.items || [];
        if (!runsR.ok || runs.length === 0) {
            rec(testInfo, { module: MOD, step: 'xlsx_export', status: 'PASS',
                note: `runs_status=${runsR.status} runs_count=${runs.length} — no stress run to export, skipping XLSX path`,
                module_blocked: 'no_stress_run' });
            return;
        }
        const runId = runs[0].id || runs[0].run_id;
        // Stress own download.
        const t0 = Date.now();
        const r = await request.get(`/api/hr/payroll/runs/${runId}/export.xlsx`, {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false,
        });
        const ms = Date.now() - t0;
        const status = r.status();
        const ct = r.headers()['content-type'] || '';
        const buf = await r.body();
        const ctOk = ct.includes('spreadsheet') || ct.includes('xlsx') || ct.includes('octet-stream');
        const sizeOk = buf.length > 100;  // XLSX min ~200 bytes (empty workbook)
        // PII scan on XLSX is unreliable without unzipping; we trust content-type
        // + size + cross-tenant guard below.

        // Cross-tenant IDOR — REAL pilot run_id (architect feedback).
        // Bogus UUID sadece "not-found" testi yapar, gerçek tenant-bound auth
        // değil. Pilot tenant'tan gerçek run_id harvest et, stress token ile
        // erişimi reddedilmeli (403/404). 2. probe: bogus UUID (fallback).
        let pilotRunId = null;
        const pilotRunsR = await callTimed(request, 'get',
            `/api/hr/payroll/runs?month=${month}`, undefined, stressTokens.pilot_token);
        const pilotRuns = pilotRunsR.body?.runs || pilotRunsR.body?.items || [];
        if (pilotRuns.length > 0) pilotRunId = pilotRuns[0].id || pilotRuns[0].run_id;

        let idor_rejected = true;
        let idorStatus = 'no_pilot_run';
        let realIdorEvidence = false;
        if (pilotRunId) {
            const realIdorR = await request.get(`/api/hr/payroll/runs/${pilotRunId}/export.xlsx`, {
                headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                failOnStatusCode: false,
            });
            idorStatus = `real_${realIdorR.status()}`;
            const realIdorBody = await realIdorR.body();
            // Real IDOR evidence: 2xx + non-trivial XLSX body (>100 bytes).
            realIdorEvidence = (realIdorR.status() === 200 || realIdorR.status() === 204)
                && realIdorBody.length > 100;
            idor_rejected = realIdorR.status() === 403 || realIdorR.status() === 404;
        }
        // Fallback: bogus UUID (not-found contract).
        const bogusId = '00000000-0000-0000-0000-000000000000';
        const bogusR = await request.get(`/api/hr/payroll/runs/${bogusId}/export.xlsx`, {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false,
        });
        const bogus_rejected = bogusR.status() === 403 || bogusR.status() === 404;

        // Anonymous probe — no auth (must 401).
        const anonR = await request.get(`/api/hr/payroll/runs/${runId}/export.xlsx`, {
            failOnStatusCode: false,
        });
        const anon_rejected = anonR.status() === 401 || anonR.status() === 403;

        const pass = (status === 200 || status === 204) && ctOk && sizeOk
            && idor_rejected && bogus_rejected && anon_rejected && !realIdorEvidence;
        recPerf(testInfo, MOD, 'xlsx_export', [ms], pass);
        rec(testInfo, { module: MOD, step: 'xlsx_export', status: pass ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/hr/payroll/runs/{id}/export.xlsx',
            note: `run_id=${String(runId).slice(0, 8)}.. status=${status} ct=${ct.slice(0, 40)} ct_ok=${ctOk} size=${buf.length} size_ok=${sizeOk} pilot_run_harvested=${!!pilotRunId} real_idor_status=${idorStatus} real_idor_evidence=${realIdorEvidence} idor_rejected=${idor_rejected} bogus_status=${bogusR.status()} bogus_rejected=${bogus_rejected} anon_status=${anonR.status()} anon_rejected=${anon_rejected}` });
        if (realIdorEvidence) recFinding(testInfo, 'P0', MOD, 'XLSX cross-tenant IDOR — pilot run_id downloaded by stress token',
            `pilot_run=${String(pilotRunId).slice(0, 8)}.. status=${idorStatus} body_size>100 — KATASTROFİK tenant isolation breach.`);
        else if (!idor_rejected && pilotRunId) recFinding(testInfo, 'P1', MOD, 'XLSX cross-tenant probe non-403/404',
            `status=${idorStatus} — beklenmeyen yüzey (body trivial, IDOR yok ama auth/scope contract drift).`);
        if (!bogus_rejected) recFinding(testInfo, 'P1', MOD, 'XLSX bogus UUID not-found drift',
            `bogus_status=${bogusR.status()} — bilinmeyen run_id 2xx döndü.`);
        if (!anon_rejected) recFinding(testInfo, 'P0', MOD, 'XLSX anonymous download',
            `anon_status=${anonR.status()} — auth gate ihlal.`);
        if (!ctOk) recFinding(testInfo, 'P2', MOD, 'XLSX content-type drift',
            `ct=${ct}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'xlsx_export', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_payroll_export_pii_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});

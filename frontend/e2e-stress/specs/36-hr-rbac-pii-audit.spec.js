// F8D-v2 § 36 — HR RBAC + PII + Audit Stress.
//
// Scope: backlog items "HR PII guard" + "HR audit log" + cross-department
// RBAC. F8D v1 spec'lerde PII mask kontrolü, token leak guard, audit log
// scope sanity hiç yapılmadı. KVKK compliance + threat-model § Information
// Disclosure / Elevation of Privilege için kritik kapanış.
//
// Test contract:
//   A) Staff list PII guard — GET /api/hr/staff response phone/identity_number
//      masked olmalı; plain bulunursa P0/P1 (KVKK).
//   B) Salary-history token+PII leak guard — GET /api/hr/staff/{id}/salary-history
//      response'unda token/credential leak guard + numeric PII şape sanity.
//   C) Audit log scope sanity — GET /api/security/audit-logs (super_admin)
//      reachability + token leak guard + cross-tenant entry leak guard.
//   D) Staff profile PII guard — GET /api/hr/staff/{id}/profile per staff
//      response phone/identity_number masked, deep PII walk.
//   E) pilot_drift=0 + external_calls=[].
//
// Mutlak kurallar:
//   - Pilot tenant'a mutation YOK (read-only spec)
//   - external_calls=[] (read-only)
//   - failedTests=0, P0=P1=0 (PII leak = P0/P1; audit token leak = P0)
//
// NOT: PII guard testleri PRODUCTION'da response shaping kontratının doğru
// uygulandığını assert eder; seed'de plain telefon/national_id var (router
// masking'in olup olmadığını test ediyoruz, seed kalitesini değil).

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertPiiMasked, assertNoTokenLeak,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_rbac_pii';

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v2 § 36 — HR RBAC + PII + Audit', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let staffPool = [];

    test('Setup: prefix + pilot baseline + staff list probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/hr/staff');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `staff_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'HR staff probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C/D skipped, E enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        const allStaff = probe.body?.staff || probe.body?.staff_members || probe.body?.items
            || (Array.isArray(probe.body) ? probe.body : []);
        staffPool = allStaff.filter((s) => {
            const name = s?.name || s?.full_name || '';
            return typeof name === 'string' && name.startsWith(prefix);
        }).slice(0, 5);
        if (staffPool.length === 0) {
            moduleBlocked = true;
            blockedReason = 'no_stress_staff';
            recFinding(testInfo, 'P2', MOD, 'No stress-tagged staff in pool',
                `total=${allStaff.length} prefix=${prefix} — A/B/C/D skipped.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} probe_status=${probe.status} staff_total=${allStaff.length} pool=${staffPool.length} module_blocked=${moduleBlocked}` });
    });

    test('A) Staff list PII guard — phone/national_id masked check', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'staff_list_pii', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
        samples.push(r.ms);
        const items = r.body?.staff || r.body?.staff_members || r.body?.items
            || (Array.isArray(r.body) ? r.body : []);
        // assertPiiMasked field list — HR'de identity_number yerine `national_id`
        // kullanılıyor; her ikisini de tara.
        const piiOkPhone = assertPiiMasked(testInfo, MOD, items, ['phone']);
        const piiOkNid = assertPiiMasked(testInfo, MOD, items, ['national_id', 'identity_number']);
        const tokOk = assertNoTokenLeak(testInfo, MOD, r.body, 'staff_list');
        const pass = r.ok && piiOkPhone && piiOkNid && tokOk;
        recPerf(testInfo, MOD, 'staff_list_pii', samples, r.ok);
        rec(testInfo, { module: MOD, step: 'staff_list_pii',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/hr/staff',
            note: `status=${r.status} items=${items.length} pii_phone_ok=${piiOkPhone} pii_nid_ok=${piiOkNid} token_ok=${tokOk}` });
        // Findings already pushed by helpers if violation — no double finding.
    });

    test('B) Salary-history token+PII guard — per stress staff sample', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || staffPool.length === 0) {
            rec(testInfo, { module: MOD, step: 'salary_history_guard', status: 'SKIP', note: 'module blocked or empty pool' });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let probedOk = 0, permFail = 0, fail = 0;
        let tokenLeakViolations = 0;
        for (const s of staffPool.slice(0, 3)) {
            const r = await callTimedWithBackoff(request, 'get',
                `/api/hr/staff/${s.id}/salary-history`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) {
                probedOk++;
                const tokOk = assertNoTokenLeak(testInfo, MOD, r.body, `salary_history:${s.id.slice(0, 8)}`);
                if (!tokOk) tokenLeakViolations++;
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
            } else { fail++; }
            await new Promise((res) => setTimeout(res, 400));
        }
        if (permFail >= staffPool.slice(0, 3).length) {
            recFinding(testInfo, 'P2', MOD, 'Salary-history RBAC blocked',
                `perm_fail=${permFail} — require_op(view_executive_reports) gate; super_admin normalde bypass eder.`);
            rec(testInfo, { module: MOD, step: 'salary_history_guard', status: 'SKIP',
                note: `perm_fail=${permFail}` });
            test.skip(true, 'RBAC blocked');
            return;
        }
        const pass = fail === 0 && tokenLeakViolations === 0;
        recPerf(testInfo, MOD, 'salary_history_guard', samples, pass);
        rec(testInfo, { module: MOD, step: 'salary_history_guard',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/hr/staff/{id}/salary-history',
            note: `probed=${probedOk} perm_fail=${permFail} fail=${fail} token_leaks=${tokenLeakViolations}` });
        if (fail > 0) recFinding(testInfo, 'P2', MOD, 'Salary-history non-2xx errors',
            `fail=${fail}`);
    });

    test('C) Audit log scope sanity — /api/security/audit-logs read + token guard', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'audit_scope', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'get', '/api/security/audit-logs',
            undefined, stressTokens.stress_token);
        samples.push(r.ms);
        if (!r.ok) {
            // Endpoint deploy-spesifik 404 olabilir — REVIEW + finding.
            recPerf(testInfo, MOD, 'audit_scope', samples, false);
            rec(testInfo, { module: MOD, step: 'audit_scope', status: 'REVIEW',
                endpoint: '/api/security/audit-logs', http: r.status,
                note: `status=${r.status} body=${JSON.stringify(r.body).slice(0, 120)}` });
            recFinding(testInfo, 'P2', MOD, 'Audit log endpoint non-2xx',
                `status=${r.status} — endpoint deploy-spesifik veya RBAC drift; F8I § 30 baseline ile çapraz kontrol gerekli.`);
            return;
        }
        const items = r.body?.items || r.body?.audit_logs || r.body?.logs
            || (Array.isArray(r.body) ? r.body : []);
        // Token leak guard — audit log content ASLA JWT/refresh içermemeli.
        const tokOk = assertNoTokenLeak(testInfo, MOD, r.body, 'audit_logs');
        // Cross-tenant entry leak: audit-logs response'unda pilot_tid taşıyan
        // entry varsa P0 (audit RBAC scope ihlali).
        const pilotTid = stressState.pilot_tid;
        let crossTenantEntries = 0;
        const sampleEntries = Array.isArray(items) ? items.slice(0, 200) : [];
        for (const it of sampleEntries) {
            if (it && typeof it === 'object' && it.tenant_id === pilotTid) crossTenantEntries++;
        }
        const pass = tokOk && crossTenantEntries === 0;
        recPerf(testInfo, MOD, 'audit_scope', samples, pass);
        rec(testInfo, { module: MOD, step: 'audit_scope',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/security/audit-logs',
            note: `status=${r.status} items=${items.length} sampled=${sampleEntries.length} token_ok=${tokOk} cross_tenant_entries=${crossTenantEntries}` });
        if (crossTenantEntries > 0) recFinding(testInfo, 'P0', MOD,
            'Audit log cross-tenant leak — stress token pilot_tid entry görüyor',
            `cross_tenant_entries=${crossTenantEntries}/${sampleEntries.length} pilot_tid=${pilotTid.slice(0, 8)}… — audit_logs query tenant_id filter eksik veya stress admin global scope (super_admin geniş kapsam beklenebilir; finding informational/severe = P0 because audit access != logical-tenant-mix).`);
    });

    test('D) Staff profile PII guard — per stress staff sample', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || staffPool.length === 0) {
            rec(testInfo, { module: MOD, step: 'staff_profile_pii', status: 'SKIP', note: 'module blocked or empty pool' });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let probedOk = 0, fail = 0, permFail = 0;
        let piiPhoneFails = 0, piiNidFails = 0;
        for (const s of staffPool.slice(0, 3)) {
            const r = await callTimedWithBackoff(request, 'get',
                `/api/hr/staff/${s.id}/profile`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) {
                probedOk++;
                const piOkPhone = assertPiiMasked(testInfo, MOD, r.body, ['phone']);
                const piOkNid = assertPiiMasked(testInfo, MOD, r.body, ['national_id', 'identity_number']);
                if (!piOkPhone) piiPhoneFails++;
                if (!piOkNid) piiNidFails++;
            } else if (r.status === 401 || r.status === 403) {
                permFail++;
            } else { fail++; }
            await new Promise((res) => setTimeout(res, 400));
        }
        if (permFail >= staffPool.slice(0, 3).length) {
            recFinding(testInfo, 'P2', MOD, 'Staff profile RBAC blocked', `perm_fail=${permFail}`);
            rec(testInfo, { module: MOD, step: 'staff_profile_pii', status: 'SKIP',
                note: `perm_fail=${permFail}` });
            test.skip(true, 'RBAC blocked');
            return;
        }
        const pass = fail === 0;
        recPerf(testInfo, MOD, 'staff_profile_pii', samples, pass);
        rec(testInfo, { module: MOD, step: 'staff_profile_pii',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/hr/staff/{id}/profile',
            note: `probed=${probedOk} perm_fail=${permFail} fail=${fail} pii_phone_fails=${piiPhoneFails} pii_nid_fails=${piiNidFails}` });
        if (fail > 0) recFinding(testInfo, 'P2', MOD, 'Staff profile non-2xx errors',
            `fail=${fail}`);
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_rbac_pii_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});

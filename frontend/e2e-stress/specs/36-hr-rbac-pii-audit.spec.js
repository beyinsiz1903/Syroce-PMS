// F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit Stress.
//
// Scope: backlog items "Cross-dept RBAC" + "HR PII guard" + "HR audit log".
// F8D v1 spec'lerde sadece super_admin token kullanıldı; düşük-priv roller
// (front_desk/housekeeping/finance/sales) ile HR yüzeyleri TEST EDİLMEDİ.
// KVKK + privilege-escalation kapanışı:
//   • A) Per-role test user create (spec 30 pattern: team POST + login)
//   • B) 4-rol × 6-HR-endpoint RBAC matrisi (deny pattern)
//   • C) Staff list PII guard (super_admin) — phone/national_id masked
//   • D) Salary-history token+PII guard (super_admin)
//   • E) Audit log scope sanity + cross-tenant entry leak guard
//   • F) external_calls invariant + pilot_drift=0 + cleanup
//
// Mutlak kurallar:
//   - Pilot tenant'a mutation YOK (F baseline diff)
//   - external_calls=[] (read-only matrix + PII probes)
//   - failedTests=0, P0=P1=0 (PII leak P0, RBAC violation P1)
//   - Suite sonunda yaratılan user'lar idempotent DELETE edilir.
//     Audit log'lar ASLA silinmez (KVKK).
//
// Module-blocked doctrine (spec 30 mirror):
//   - Super_admin team POST 403/404 veya per-role login chain başarısız →
//     B/C/D/E test.skip + P2 informational; F pilot_drift bağımsız.
//
// Threat-model anchors:
//   - § Information Disclosure (HR staff PII, salary, audit log cross-tenant)
//   - § Elevation of Privilege (low-priv rol HR yüzeylerine erişebiliyorsa)
//   - § Tampering (low-priv rol HR write endpoint'lerine erişebiliyorsa —
//     bu spec read-only deny matrisi; write deny tier yine de güvende)

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertNoTokenLeak,
    assertHrPiiMasked,
} from '../fixtures/stress-helpers.js';

const MOD = 'hr_rbac_pii';

// Cross-department roller — tier-bağımsız temel set (spec 30 mirror).
const ROLES = ['front_desk', 'housekeeping', 'finance', 'sales'];

// HR-sensitive read endpoint matrisi. expectAuthorized:[] = HİÇBİR düşük-priv
// rol erişmemeli (super_admin only — view_executive_reports / view_hr).
// Backend'in finance rolüne payroll erişimi VERSE bile, cross-department
// deny doctrine: HR yüzeyleri tek otorite kanalından (HR yönetici/super_admin)
// geçer. Sapma → P1 informational + matrix violation kaydı.
//
// {endpoint, dynamic} — dynamic=true ise setup'ta {staff_id} fill edilir.
const HR_SENSITIVE = [
    { key: 'staff_list',      path: '/api/hr/staff',                              expectAuthorized: [] },
    { key: 'salary_history',  path: '/api/hr/staff/{sid}/salary-history',          expectAuthorized: [], dynamic: true },
    { key: 'payroll_month',   path: '/api/hr/payroll/{month}',                     expectAuthorized: [], dynamic: 'month' },
    { key: 'payroll_export',  path: '/api/hr/payroll/export?month={month}',         expectAuthorized: [], dynamic: 'month' },
    { key: 'leave_balance',   path: '/api/hr/leave-balance/{sid}',                  expectAuthorized: [], dynamic: true },
    { key: 'perf_list',       path: '/api/hr/performance',                          expectAuthorized: [] },
];

// HR WRITE endpoint deny matrisi — mutasyon yüzeyleri düşük-priv rollere
// KESİN deny olmalı (KVKK + finance immutability + privilege escalation).
// Her satır {method, path, body, dynamic, expectAuthorized}. dynamic=true →
// {sid} fill, dynamic='month' → {month} fill. body=null → boş body.
// Hepsi expectAuthorized=[]: front_desk/housekeeping/finance/sales hiçbiri
// HR mutasyonuna sahip değil. 2xx → P0 (write-side privilege escalation).
const HR_WRITE_DENY = [
    { method: 'post',   path: '/api/hr/staff',                                 body: () => ({ name: 'XX', email: 'noop@x.test', position: 'p', department: 'd', employment_type: 'full_time' }) },
    { method: 'put',    path: '/api/hr/staff/{sid}',                           body: () => ({ name: 'XX-mod' }), dynamic: true },
    { method: 'delete', path: '/api/hr/staff/{sid}',                           body: null, dynamic: true },
    { method: 'post',   path: '/api/hr/staff/{sid}/salary-change',              body: () => ({ new_salary: 1, effective_date: '2030-01-01', reason: 'noop' }), dynamic: true },
    { method: 'post',   path: '/api/hr/staff/{sid}/terminate',                  body: () => ({ termination_date: '2030-01-01', reason: 'noop' }), dynamic: true },
    { method: 'post',   path: '/api/hr/leave-balance',                          body: () => ({ staff_id: '00000000-0000-0000-0000-000000000000', year: 2030, annual_entitlement: 14, carry_over: 0, sick_entitlement: 7 }) },
    { method: 'post',   path: '/api/hr/performance',                            body: () => ({ staff_id: '00000000-0000-0000-0000-000000000000', period: '2030-Q1', rating: 3 }) },
];

function currentMonth() {
    const d = new Date();
    return `${d.getUTCFullYear()}-${String(d.getUTCMonth() + 1).padStart(2, '0')}`;
}

test.describe.configure({ mode: 'serial' });

test.describe('F8D-v2 § 36 — HR Cross-Department RBAC + PII + Audit', () => {
    let prefix = null;
    let pilotBefore = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let staffPool = [];
    let firstStaffId = null;
    let createdUsers = []; // {id, email, role, password}
    let roleTokens = {};   // role → bearer
    const MONTH = currentMonth();

    test('Setup: prefix + pilot baseline + staff pool + per-role test user create + login', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // HR staff list probe (super_admin) — staff pool + PII guard baseline.
        const probe = await withModuleProbe(request, stressTokens.stress_token, '/api/hr/staff');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `staff_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'HR staff probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — B/C/D/E skipped, F pilot_drift still enforced.`);
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
        firstStaffId = staffPool[0]?.id || allStaff[0]?.id || null;

        // Per-role test user create (spec 30 pattern).
        const stressTid = stressState.stress_tid;

        // Idempotent pre-cleanup: prior-run residue (prefix+rbacpi prefix-tag).
        const listR = await callTimed(request, 'get', '/api/admin/users', undefined, stressTokens.stress_token);
        let preCleaned = 0;
        if (listR.ok) {
            const users = Array.isArray(listR.body) ? listR.body
                : (listR.body?.users || listR.body?.items || listR.body?.data || []);
            for (const u of users) {
                const em = (u.email || '').toLowerCase();
                if (em.startsWith(prefix.toLowerCase() + 'hrpii_') && em.endsWith('@stress.test') && u.tenant_id === stressTid) {
                    const del = await callTimed(request, 'delete',
                        `/api/admin/tenants/${stressTid}/team/${u.id || u._id}`,
                        undefined, stressTokens.stress_token);
                    if (del.ok || del.status === 404) preCleaned++;
                }
            }
        }

        let createOk = 0, createFail = 0, firstFailDetail = null;
        for (const role of ROLES) {
            const email = `${prefix}hrpii_${role}@stress.test`.toLowerCase();
            const password = `Stress_${prefix}_${role}_Pw!2026`;
            const name = `Stress HR-RBAC ${role}`;
            const r = await callTimed(request, 'post',
                `/api/admin/tenants/${stressTid}/team`,
                { email, name, role, password },
                stressTokens.stress_token);
            if (r.ok && r.body?.user_id) {
                createOk++;
                createdUsers.push({ id: r.body.user_id, email, role, password });
            } else {
                createFail++;
                if (!firstFailDetail) firstFailDetail = `${role} → status=${r.status} body=${JSON.stringify(r.body).slice(0, 160)}`;
            }
        }
        if (createOk === 0) {
            moduleBlocked = true;
            blockedReason = `team_create_all_fail (${firstFailDetail})`;
            recFinding(testInfo, 'P2', MOD, 'Per-role test user creation failed for all roles',
                `${firstFailDetail || 'no detail'} — B matrix skipped; C/D/E still attempted under super_admin; F pilot_drift enforced.`);
        }

        // Login each created user.
        for (const u of createdUsers) {
            const r = await callTimed(request, 'post', '/api/auth/login',
                { email: u.email, password: u.password }, '');
            if (r.ok && r.body?.access_token) {
                roleTokens[u.role] = r.body.access_token;
            } else {
                recFinding(testInfo, 'P2', MOD, `Login failed for created user (${u.role})`,
                    `status=${r.status} body=${JSON.stringify(r.body).slice(0, 120)}`);
            }
        }

        const tokenRoles = Object.keys(roleTokens);
        const MIN_ROLES_REQUIRED = 3;
        if (!moduleBlocked && tokenRoles.length < MIN_ROLES_REQUIRED) {
            recFinding(testInfo, 'P1', MOD,
                'HR-RBAC matrix coverage eksik — minimum rol sayısı altında',
                `logged_in=${tokenRoles.length}/${ROLES.length} (min=${MIN_ROLES_REQUIRED}). Matrix kapsamı silently collapse oldu.`);
        }

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} staff_total=${allStaff.length} pool=${staffPool.length} first_sid=${firstStaffId?.slice(0,8)} month=${MONTH} pre_cleaned=${preCleaned} created=${createOk}/${ROLES.length} fail=${createFail} logged_in=${tokenRoles.join('|')} module_blocked=${moduleBlocked}` });
    });

    test('A) HR-RBAC matrix — 4 roles × 6 sensitive endpoints (cross-dept deny)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'rbac_matrix', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const tokenRoles = Object.keys(roleTokens);
        if (tokenRoles.length === 0) {
            rec(testInfo, { module: MOD, step: 'rbac_matrix', status: 'SKIP', note: 'no role tokens' });
            test.skip(true, 'no role tokens');
            return;
        }
        const samples = [];
        const violations = []; // {role, endpoint, status, expected:'deny'}
        const reviewMarks = []; // {role, endpoint, status}
        let totalChecks = 0;
        for (const ep of HR_SENSITIVE) {
            // Resolve dynamic placeholders.
            let url = ep.path;
            if (ep.dynamic === true) {
                if (!firstStaffId) continue;
                url = url.replace('{sid}', firstStaffId);
            } else if (ep.dynamic === 'month') {
                url = url.replace('{month}', MONTH);
            }
            for (const role of tokenRoles) {
                totalChecks++;
                const r = await callTimed(request, 'get', url, undefined, roleTokens[role]);
                samples.push(r.ms);
                const isAuthorized = ep.expectAuthorized.includes(role);
                // expectAuthorized=[] olduğunda deny beklenir; 2xx = P1 violation.
                if (!isAuthorized && r.status >= 200 && r.status < 300) {
                    violations.push({ role, endpoint: ep.key, url, status: r.status });
                } else if (isAuthorized && (r.status === 401 || r.status === 403)) {
                    // Beklenen authorized rol reject edildi — REVIEW.
                    reviewMarks.push({ role, endpoint: ep.key, status: r.status, kind: 'unexpected_deny' });
                }
                // 404 = endpoint deploy yok (her zaman PASS as deny analog).
                // 5xx = REVIEW (router error).
                if (r.status >= 500) {
                    reviewMarks.push({ role, endpoint: ep.key, status: r.status, kind: '5xx' });
                }
                await new Promise((res) => setTimeout(res, 300));
            }
        }
        const pass = violations.length === 0;
        recPerf(testInfo, MOD, 'rbac_matrix', samples, pass);
        rec(testInfo, { module: MOD, step: 'rbac_matrix',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '4 roles × 6 HR-sensitive endpoints',
            note: `total_checks=${totalChecks} violations=${violations.length} reviews=${reviewMarks.length} roles=${tokenRoles.join('|')} viol_sample=${JSON.stringify(violations.slice(0, 5))}` });
        if (violations.length > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Cross-department RBAC violation — düşük-priv rol HR yüzeyine 2xx aldı',
                `count=${violations.length}/${totalChecks} sample=${JSON.stringify(violations.slice(0, 5))}. Spec doctrine: tüm low-priv roller HR endpoint'lerinden deny (403/404). Backend gate'ini view_hr/view_executive_reports tek otoriteye bağla.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'rbac_matrix', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('A2) HR WRITE deny matrix — 4 roles × 7 mutation endpoints (cross-dept escalation guard)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'rbac_write_matrix', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const tokenRoles = Object.keys(roleTokens);
        if (tokenRoles.length === 0) {
            rec(testInfo, { module: MOD, step: 'rbac_write_matrix', status: 'SKIP', note: 'no role tokens' });
            test.skip(true, 'no role tokens');
            return;
        }
        const samples = [];
        const writeViolations = []; // {role, endpoint, method, status} — 2xx = P0
        const authzAmbiguous = []; // {role, endpoint, status} — non-401/403/2xx ambiguous
        let totalChecks = 0, accidentalSuccess = 0;
        // Resolve gerçek seed staff_id (architect iter-5 directive): sahte
        // UUID payload validation/not-found ile maskelenebiliyor; gerçek
        // staff_id ile authorization gate'i bypass denenir, böylece 401/403
        // yanıtı explicit auth-denied olur, 404/422 değil. Seed staff'lar
        // pilot_token'la listelenebilir (super_admin scope), stress tenant'ta.
        let realStaffId = '00000000-0000-0000-0000-000000000000';
        try {
            const sl = await callTimed(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
            if (sl.ok) {
                const list = sl.body?.staff || sl.body?.items || sl.body || [];
                if (Array.isArray(list) && list.length > 0 && (list[0].id || list[0]._id)) {
                    realStaffId = list[0].id || list[0]._id;
                }
            }
        } catch (_) { /* fallback to fake UUID */ }
        for (const ep of HR_WRITE_DENY) {
            let url = ep.path;
            if (ep.dynamic === true) {
                // GERÇEK staff_id (iter-5): authorization gate'i bypass için
                // valid resource gerekir; aksi takdirde 404 auth ambiguity
                // yaratır. Delete payload'ları için bu kaynak hedef alınır
                // ancak düşük-priv token kullanıldığı için 401/403 BEKLENIR
                // ve gerçek delete asla olmaz.
                url = url.replace('{sid}', realStaffId);
            }
            for (const role of tokenRoles) {
                totalChecks++;
                const body = typeof ep.body === 'function' ? ep.body() : ep.body;
                // Real-resource payload: staff_id'yi de gerçek olanla doldur.
                if (body && body.staff_id === '00000000-0000-0000-0000-000000000000') {
                    body.staff_id = realStaffId;
                }
                const r = await callTimed(request, ep.method, url, body, roleTokens[role]);
                samples.push(r.ms);
                if (r.status >= 200 && r.status < 300) {
                    accidentalSuccess++;
                    writeViolations.push({ role, endpoint: ep.path, method: ep.method, status: r.status });
                } else if (r.status === 401 || r.status === 403) {
                    // Expected: explicit auth denial → PASS for this check.
                } else {
                    // Non-2xx but also non-401/403 (404/422/500) → ambiguous.
                    // Spec 36 RBAC matrisi explicit auth denial bekler;
                    // bu ambiguity authz defect'i maskeleyebilir → P2 review.
                    authzAmbiguous.push({ role, endpoint: ep.path, method: ep.method, status: r.status });
                }
                await new Promise((res) => setTimeout(res, 250));
            }
        }
        const pass = writeViolations.length === 0;
        recPerf(testInfo, MOD, 'rbac_write_matrix', samples, pass);
        rec(testInfo, { module: MOD, step: 'rbac_write_matrix',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '4 roles × 7 HR mutation endpoints',
            note: `total_checks=${totalChecks} write_violations=${writeViolations.length} accidental_2xx=${accidentalSuccess} authz_ambiguous=${authzAmbiguous.length} real_sid_resolved=${realStaffId !== '00000000-0000-0000-0000-000000000000'} roles=${tokenRoles.join('|')} viol_sample=${JSON.stringify(writeViolations.slice(0, 5))}` });
        if (writeViolations.length > 0) {
            // WRITE-side violation = P0 privilege escalation (mutate-without-auth).
            recFinding(testInfo, 'P0', MOD,
                'HR WRITE privilege escalation — düşük-priv rol HR mutation endpoint\'inde 2xx',
                `count=${writeViolations.length}/${totalChecks} sample=${JSON.stringify(writeViolations.slice(0, 5))}. KVKK + finance immutability + privilege escalation hattının tam ihlali. Backend gate'leri require_op(...) ile sıkılaştır.`);
        }
        if (authzAmbiguous.length > 0) {
            // Non-401/403 non-2xx → authz vs validation/not-found ambiguity.
            // Architect iter-5 directive: explicit auth denial bekleniyor.
            recFinding(testInfo, 'P2', MOD,
                'HR WRITE authz ambiguity — non-401/403 non-2xx response',
                `count=${authzAmbiguous.length}/${totalChecks} sample=${JSON.stringify(authzAmbiguous.slice(0, 5))}. Validation/not-found defect'i authz gap'i maskeleyebilir; gerçek-resource payload'la tekrar denenmeli.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'rbac_write_matrix', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) Staff list PII guard — phone/national_id/TC/IBAN masked', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'staff_list_pii', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        const r = await callTimedWithBackoff(request, 'get', '/api/hr/staff', undefined, stressTokens.stress_token);
        samples.push(r.ms);
        const piiOk = assertHrPiiMasked(testInfo, MOD, r.body, ['national_id', 'identity_number', 'tc_kimlik']);
        const tokOk = assertNoTokenLeak(testInfo, MOD, r.body, 'staff_list');
        const pass = r.ok && piiOk && tokOk;
        const items = r.body?.staff || r.body?.staff_members || r.body?.items
            || (Array.isArray(r.body) ? r.body : []);
        recPerf(testInfo, MOD, 'staff_list_pii', samples, r.ok);
        rec(testInfo, { module: MOD, step: 'staff_list_pii',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/hr/staff',
            note: `status=${r.status} items=${items.length} pii_ok=${piiOk} token_ok=${tokOk}` });
    });

    test('C) Salary-history token+PII guard — per stress staff sample', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || staffPool.length === 0) {
            rec(testInfo, { module: MOD, step: 'salary_history_guard', status: 'SKIP', note: 'module blocked or empty pool' });
            test.skip(true, 'module blocked');
            return;
        }
        const samples = [];
        let probedOk = 0, permFail = 0, fail = 0;
        let tokenLeakViolations = 0, piiViolations = 0;
        for (const s of staffPool.slice(0, 3)) {
            const r = await callTimedWithBackoff(request, 'get',
                `/api/hr/staff/${s.id}/salary-history`, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) {
                probedOk++;
                const tokOk = assertNoTokenLeak(testInfo, MOD, r.body, `salary_history:${s.id.slice(0, 8)}`);
                const piiOk = assertHrPiiMasked(testInfo, MOD, r.body, ['iban', 'bank_iban']);
                if (!tokOk) tokenLeakViolations++;
                if (!piiOk) piiViolations++;
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
        const pass = fail === 0 && tokenLeakViolations === 0 && piiViolations === 0;
        recPerf(testInfo, MOD, 'salary_history_guard', samples, pass);
        rec(testInfo, { module: MOD, step: 'salary_history_guard',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/hr/staff/{id}/salary-history',
            note: `probed=${probedOk} perm_fail=${permFail} fail=${fail} token_leaks=${tokenLeakViolations} pii_leaks=${piiViolations}` });
    });

    test('D) Audit log scope sanity — read + token guard + cross-tenant leak', async ({ request, stressTokens, stressState }, testInfo) => {
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
            recPerf(testInfo, MOD, 'audit_scope', samples, false);
            rec(testInfo, { module: MOD, step: 'audit_scope', status: 'REVIEW',
                endpoint: '/api/security/audit-logs', http: r.status,
                note: `status=${r.status} body=${JSON.stringify(r.body).slice(0, 120)}` });
            recFinding(testInfo, 'P2', MOD, 'Audit log endpoint non-2xx',
                `status=${r.status} — endpoint deploy-spesifik veya RBAC drift.`);
            return;
        }
        const items = r.body?.items || r.body?.audit_logs || r.body?.logs
            || (Array.isArray(r.body) ? r.body : []);
        const tokOk = assertNoTokenLeak(testInfo, MOD, r.body, 'audit_logs');
        const pilotTid = stressState.pilot_tid;
        let crossTenantEntries = 0;
        const sampleEntries = Array.isArray(items) ? items.slice(0, 200) : [];
        for (const it of sampleEntries) {
            if (it && typeof it === 'object' && it.tenant_id === pilotTid) crossTenantEntries++;
        }
        // Recent HR mutation presence probe — seed'de yaratılan stress tenant
        // HR rows (departments/positions/staff inserts) audit log'da
        // görünmeli. Backend tüm HR insert path'lerinde audit yazmıyorsa P2
        // informational (audit coverage drift'i için forward-compat).
        const stressTid = stressState.stress_tid;
        const HR_ACTION_HINTS = ['hr_', 'staff', 'department', 'position', 'leave', 'shift', 'performance', 'payroll'];
        let hrMutationEntries = 0;
        for (const it of sampleEntries) {
            if (!it || typeof it !== 'object') continue;
            const tid = it.tenant_id;
            const action = String(it.action || it.event_type || it.action_type || '').toLowerCase();
            if (tid === stressTid && HR_ACTION_HINTS.some((h) => action.includes(h))) hrMutationEntries++;
        }
        const pass = tokOk && crossTenantEntries === 0;
        recPerf(testInfo, MOD, 'audit_scope', samples, pass);
        rec(testInfo, { module: MOD, step: 'audit_scope',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: '/api/security/audit-logs',
            note: `status=${r.status} items=${items.length} sampled=${sampleEntries.length} token_ok=${tokOk} cross_tenant_entries=${crossTenantEntries} hr_mutation_entries_for_stress_tid=${hrMutationEntries}` });
        if (crossTenantEntries > 0) recFinding(testInfo, 'P0', MOD,
            'Audit log cross-tenant leak — stress token pilot_tid entry görüyor',
            `cross_tenant_entries=${crossTenantEntries}/${sampleEntries.length} pilot_tid=${pilotTid.slice(0, 8)}…`);
        if (hrMutationEntries === 0) recFinding(testInfo, 'P2', MOD,
            'HR mutation audit coverage drift — stress tenant için son HR action entry yok',
            `sampled=${sampleEntries.length} stress_tid=${stressTid.slice(0, 8)}… — backend HR insert path'leri audit log yazmıyor olabilir; KVKK forensic eksikliği informational.`);
    });

    test('E) Cleanup created users (idempotent DELETE; audit logs untouched)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (createdUsers.length === 0) {
            rec(testInfo, { module: MOD, step: 'cleanup_users', status: 'SKIP', note: 'no users created' });
            return;
        }
        const stressTid = stressState.stress_tid;
        let delOk = 0, delFail = 0;
        for (const u of createdUsers) {
            const del = await callTimed(request, 'delete',
                `/api/admin/tenants/${stressTid}/team/${u.id}`,
                undefined, stressTokens.stress_token);
            if (del.ok || del.status === 404) delOk++; else delFail++;
            await new Promise((res) => setTimeout(res, 250));
        }
        rec(testInfo, { module: MOD, step: 'cleanup_users',
            status: delFail === 0 ? 'PASS' : 'REVIEW',
            note: `del_ok=${delOk}/${createdUsers.length} del_fail=${delFail} (audit_logs preserved per KVKK)` });
        if (delFail > 0) recFinding(testInfo, 'P2', MOD, 'Test user cleanup partial fail',
            `del_fail=${delFail}/${createdUsers.length} — next run pre-cleanup absorbs residue.`);
    });

    test('F) external_calls invariant + pilot_drift=0', async ({ request, stressTokens, stressState }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'hr_rbac_pii_done', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: extOk ? 'PASS' : 'FAIL',
            note: 'pilot_drift+external_calls verified' });
        expect(extOk).toBe(true);
    });
});

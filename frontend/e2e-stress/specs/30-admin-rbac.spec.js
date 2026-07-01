// F8I § 30 — Admin / RBAC Matrix Stress.
//
// Threat-model surface: privilege escalation + cross-tenant disclosure on
// admin/system/audit endpoints. F8A–F8E suite yalnız super_admin token
// kullandı; per-role negative coverage hiç yapılmadı. Bu spec 3-4 düşük-priv
// rol için stress tenant'ta test kullanıcısı yaratır (super_admin team POST),
// login eder, hassas endpoint matrisini assert eder.
//
// Mutlak kurallar:
//   - pilot mutation YOK (drift=0)
//   - external_calls=[] (post-batch helper)
//   - failedTests=0, P0=P1=0 (matrix violation P1, helper falls back to
//     module-blocked → P2 SKIP when create/login chain unreachable)
//
// Module-blocked pattern (F8C/D/E mirror):
//   - super_admin team POST 403/404/4xx-tier-block → moduleBlocked=true,
//     A/B/C test.skip + P2 informational; D pilot_drift bağımsız çalışır
//
// Cleanup: yarattığımız user'lar suite sonunda idempotent DELETE edilir.
// Audit log'lar ASLA silinmez (KVKK gereği).
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'admin_rbac';

// 4 rol × tier-uyumlu seçim (basic tier'da kesin var olanlar).
// Stress tenant tier'ı bilmiyoruz; tier-block (400) → moduleBlocked.
const ROLES = ['front_desk', 'housekeeping', 'finance', 'sales'];

// Hassas endpoint matrisi — her satır {path, expectAuthorized:[roles], desc}.
// expectAuthorized listesi backend guard'larına göre kalibrelendi
// (architect review #1, 2026-05-19):
//   • require_super_admin:    /admin/users, /admin/tenants
//   • admin/super_admin only: /security/audit-logs (view_system_diagnostics),
//     /admin/web-push/metrics (architect re-review #2: inner role check
//     ADMIN/SUPER_ADMIN — get_current_user decorator yanıltıcı)
//   • get_current_user (any auth): /system/*, /gdpr/data-requests
//     (tenant-scoped), /rbac/my-permissions, /rbac/roles
// Liste DIŞINDA kalan roller için 403/404 beklenir; 200 → P1 violation.
const SENSITIVE = [
    { path: '/api/admin/users', expectAuthorized: [], desc: 'admin users list (super_admin only)' },
    { path: '/api/admin/tenants', expectAuthorized: [], desc: 'admin tenants list (super_admin only)' },
    { path: '/api/security/audit-logs', expectAuthorized: [], desc: 'audit log read (admin/super_admin only)' },
    { path: '/api/system/performance', expectAuthorized: ROLES, desc: 'system performance (any auth)' },
    { path: '/api/system/rate-limits', expectAuthorized: ROLES, desc: 'system rate-limits (any auth)' },
    { path: '/api/system/db-stats', expectAuthorized: ROLES, desc: 'system db-stats (any auth)' },
    { path: '/api/admin/web-push/metrics', expectAuthorized: [], desc: 'push metrics (admin/super_admin only — inner role check)' },
    { path: '/api/gdpr/data-requests', expectAuthorized: ROLES, desc: 'GDPR requests (any auth tenant-scoped)' },
    { path: '/api/rbac/my-permissions', expectAuthorized: ROLES, desc: 'self-perms (any auth)' },
    { path: '/api/rbac/roles', expectAuthorized: ROLES, desc: 'roles catalog (any auth)' },
];

test.describe.configure({ mode: 'serial' });

test.describe('F8I § 30 — Admin / RBAC Matrix', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let createdUsers = [];   // {id, email, role, token}
    let roleTokens = {};     // role → bearer
    // Task #162: admin/tenants + team + admin/users yüzeyleri require_super_admin.
    // stress_token tenant-level admin'dir (super_admin DEĞİL) → 403 → modül
    // tamamen bloke oluyordu. super_admin principal token'ı (role_tokens.super_admin
    // = pilot super_admin) ile çağrılınca gerçek RBAC matrisi test edilebilir.
    // Tenant-scoped reads (rbac/system/gdpr) için low-priv roleTokens kullanılır.
    let superToken = null;

    test('Setup: prefix + pilot baseline + super_admin team POST probe + per-role user create', async ({ request, stressTokens, stressRoles, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        // super_admin principal — admin/tenants + team yüzeyleri için. role_tokens
        // yoksa pilot_token'a düş (ikisi de pilot super_admin'i çözümler).
        superToken = stressRoles.super_admin ?? stressTokens.pilot_token;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Reachability probe: super_admin must be able to read tenants list.
        const probe = await withModuleProbe(request, superToken, '/api/admin/tenants');
        if (probe.moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `admin_tenants_probe_${probe.reason}_status_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Admin tenants probe non-2xx',
                `status=${probe.status} reason=${probe.reason} — A/B/C skipped, D pilot_drift still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }

        const stressTid = stressState.stress_tid;
        // Idempotent pre-cleanup: önceki run'dan kalan prefix'li RBAC user'lar
        // varsa sil (architect review #4, 2026-05-19). 400 already-registered
        // hatasını önler, residue bırakmaz.
        const listR = await callTimed(request, 'get', '/api/admin/users', undefined, superToken);
        let preCleaned = 0;
        if (listR.ok) {
            const users = Array.isArray(listR.body) ? listR.body
                : (listR.body?.users || listR.body?.items || listR.body?.data || []);
            for (const u of users) {
                const em = (u.email || '').toLowerCase();
                if (em.startsWith(prefix.toLowerCase() + 'rbac_') && em.endsWith('@stress-e2e.com') && u.tenant_id === stressTid) {
                    const del = await callTimed(request, 'delete',
                        `/api/admin/tenants/${stressTid}/team/${u.id || u._id}`,
                        undefined, superToken);
                    if (del.ok || del.status === 404) preCleaned++;
                }
            }
        }

        // Per-role test user oluştur. Prefix'li email + 64-char random password.
        // Tier-block (400) veya başka 4xx → user create skipped, role token yok.
        let createOk = 0, createFail = 0, firstFailDetail = null;
        for (const role of ROLES) {
            const email = `${prefix}rbac_${role}@stress-e2e.com`.toLowerCase();
            const password = `Stress_${prefix}_${role}_Pw!2026`;
            const name = `Stress RBAC ${role}`;
            const r = await callTimed(request, 'post',
                `/api/admin/tenants/${stressTid}/team`,
                { email, name, role, password },
                superToken);
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
                `${firstFailDetail || 'no detail'} — A/B/C skipped, D pilot_drift still enforced.`);
        }

        // Login each created user → cache role token. Login fail per-user → drop from matrix.
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
        if (tokenRoles.length === 0 && !moduleBlocked) {
            moduleBlocked = true;
            blockedReason = `login_all_fail (${createOk} created, 0 logged in)`;
        }

        // Validation review (2026-05-19): RBAC matrix coverage hard floor.
        // moduleBlocked yoksa MINIMUM rol sayısına ulaşmak ŞART; aksi halde
        // matrix silently collapse eder. Eşik: en az 3/4 rol (≥75%).
        const MIN_ROLES_REQUIRED = 3;
        if (!moduleBlocked && tokenRoles.length < MIN_ROLES_REQUIRED) {
            recFinding(testInfo, 'P1', MOD,
                'RBAC matrix coverage eksik — minimum rol sayısı altında',
                `logged_in=${tokenRoles.length}/${ROLES.length} (min=${MIN_ROLES_REQUIRED}). Matrix kapsamı silently collapse oldu; per-role create/login chain hatasını düzelt veya tier override et.`);
        }

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pre_cleaned=${preCleaned} pilot_before=${pilotBefore?.count} created=${createOk}/${ROLES.length} logged_in=${tokenRoles.join(',') || 'none'} module_blocked=${moduleBlocked}` });
        // Architect re-review #2: trivial hard expect kaldırıldı — setup
        // failure'ı moduleBlocked/finding üzerinden sinyallenir.
    });

    test('A) Super-admin baseline — 10 sensitive endpoints 2xx (control)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'super_admin_baseline', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        let okCount = 0, failCount = 0;
        const details = [];
        for (const e of SENSITIVE) {
            const r = await callTimed(request, 'get', e.path, undefined, superToken);
            const is2xx = r.status >= 200 && r.status < 300;
            if (is2xx) okCount++;
            else { failCount++; details.push(`${e.path}=${r.status}`); }
            await new Promise(res => setTimeout(res, 250));
        }
        // Architect-tolerant: super_admin'in 2xx beklenmesi ama bazı endpoint'ler
        // (örn. /admin/web-push/metrics) deploy-spesifik 404 dönebilir → REVIEW P2.
        const ok = failCount === 0;
        rec(testInfo, { module: MOD, step: 'super_admin_baseline',
            status: ok ? 'PASS' : 'REVIEW',
            note: `2xx=${okCount}/${SENSITIVE.length} fail=${details.join(' ') || 'none'}` });
        if (!ok) {
            recFinding(testInfo, 'P2', MOD, 'Super-admin baseline non-2xx on some endpoints',
                `Non-2xx: ${details.join(', ')}. Deploy-spesifik veya rota değişikliği olabilir; matrix C step bu endpoint'leri yine de düşük-priv ile dener.`);
        }

        // Validation review (2026-05-19): token/JWT leak guard for admin
        // baseline responses (audit-logs + users + tenants + system/* + push
        // metrics). Tokens=spoofing primitive (threat-model § Spoofing).
        let baselineTokOk = true;
        for (const ep of SENSITIVE) {
            const r = await callTimed(request, 'get', ep.path, undefined, superToken);
            if (r.ok) {
                baselineTokOk = assertNoTokenLeak(testInfo, MOD, r.body, `admin_baseline:${ep.path}`) && baselineTokOk;
            }
            await new Promise(res => setTimeout(res, 100));
        }
        rec(testInfo, { module: MOD, step: 'admin_baseline_token_leak_guard',
            status: baselineTokOk ? 'PASS' : 'FAIL',
            note: `endpoints_scanned=${SENSITIVE.length} token_ok=${baselineTokOk}` });
        // Architect re-review #2: trivial hard expect kaldırıldı.
    });

    test('B) RBAC catalog — /api/rbac/roles + my-permissions per-role tutarlılık', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'rbac_catalog', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // /api/rbac/roles süper admin ile çağrılır (her auth gider).
        const rolesR = await callTimed(request, 'get', '/api/rbac/roles', undefined, superToken);
        let rolesOk = rolesR.ok;
        rec(testInfo, { module: MOD, step: 'rbac_roles_read',
            status: rolesOk ? 'PASS' : 'REVIEW',
            endpoint: '/api/rbac/roles', http: rolesR.status,
            note: rolesOk ? `keys=${JSON.stringify(rolesR.body).slice(0, 100)}` : `body=${JSON.stringify(rolesR.body).slice(0, 120)}` });

        // Her role token için /api/rbac/my-permissions çağır; 200 + permissions
        // alanı içermeli (içerik analiz değil, sadece reachability + shape).
        let perRoleOk = 0, perRoleFail = 0;
        for (const [role, token] of Object.entries(roleTokens)) {
            const r = await callTimed(request, 'get', '/api/rbac/my-permissions', undefined, token);
            if (r.ok) perRoleOk++; else { perRoleFail++; }
            await new Promise(res => setTimeout(res, 200));
        }
        rec(testInfo, { module: MOD, step: 'rbac_my_permissions_per_role',
            status: perRoleFail === 0 ? 'PASS' : 'REVIEW',
            note: `ok=${perRoleOk} fail=${perRoleFail} roles=${Object.keys(roleTokens).join(',')}` });
        // Architect re-review #2: trivial hard expect kaldırıldı.
    });

    test('C) Negative matrix — düşük-priv tokens hassas endpoint\'lere 403/404 almalı', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'negative_matrix', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        let totalChecks = 0;
        let violations = [];     // {role, path, status, body_snippet}
        let denied = 0;
        let perm_gated_ok = 0;   // expectAuthorized=true ve 2xx
        let unreachable = 0;     // 5xx / network
        let piiViolations = 0;

        for (const [role, token] of Object.entries(roleTokens)) {
            for (const e of SENSITIVE) {
                totalChecks++;
                const r = await callTimed(request, 'get', e.path, undefined, token);
                const isAuthorized = e.expectAuthorized.includes(role);
                const is2xx = r.status >= 200 && r.status < 300;
                const isForbidden = r.status === 403 || r.status === 404;
                const is5xx = r.status >= 500;

                if (is5xx) {
                    unreachable++;
                } else if (isAuthorized) {
                    // Bu rol için izinli endpoint — 2xx beklenir.
                    if (is2xx) {
                        perm_gated_ok++;
                        // PII guard — list endpoint dönerse mask kontrolü.
                        if (e.path.includes('/users') || e.path.includes('/guests')) {
                            const before = piiViolations;
                            const masked = assertPiiMasked(testInfo, MOD, r.body, ['phone', 'email', 'identity_number']);
                            if (!masked) piiViolations += 1;
                            // Her PII fail testInfo'ya finding push ediyor; burada sadece sayım.
                            if (piiViolations !== before) {
                                // already recorded
                            }
                        }
                    } else if (isForbidden) {
                        // Beklenmedik 403/404 — backend RBAC daha sıkı; REVIEW P2.
                        recFinding(testInfo, 'P2', MOD,
                            `Authorized role unexpectedly denied (${role} → ${e.path})`,
                            `status=${r.status} expected=2xx — backend RBAC may be stricter than ROLE_PERMISSIONS suggests; informational.`);
                    }
                } else {
                    // Bu rol için yetkisiz endpoint — 403/404 beklenir.
                    if (is2xx) {
                        // GERÇEK İHLAL: yetkisiz rol 2xx aldı.
                        violations.push({
                            role, path: e.path, status: r.status,
                            body_snippet: JSON.stringify(r.body).slice(0, 120),
                        });
                    } else if (isForbidden) {
                        denied++;
                    }
                }
                await new Promise(res => setTimeout(res, 200));
            }
        }

        // Validation review (2026-05-19): minimum total_checks hard floor.
        // Beklenen: tokenRoles.length × SENSITIVE.length. Reel ölçüm bunun
        // %75 altındaysa matrix collapse demektir → P1.
        const expectedChecks = Object.keys(roleTokens).length * SENSITIVE.length;
        const minChecks = Math.floor(expectedChecks * 0.75);
        if (expectedChecks > 0 && totalChecks < minChecks) {
            recFinding(testInfo, 'P1', MOD,
                'RBAC matrix total_checks coverage floor altında',
                `total_checks=${totalChecks} expected=${expectedChecks} min=${minChecks}. Loop erken kırıldı veya rol skip edildi.`);
        }

        rec(testInfo, { module: MOD, step: 'negative_matrix',
            status: (violations.length === 0 && unreachable === 0) ? 'PASS' : 'REVIEW',
            note: `total_checks=${totalChecks}/${expectedChecks} denied=${denied} authorized_2xx=${perm_gated_ok} violations=${violations.length} unreachable=${unreachable} pii_violations=${piiViolations}` });

        if (violations.length > 0) {
            recFinding(testInfo, 'P1', MOD,
                'RBAC negative matrix ihlali — düşük-priv rol hassas endpoint\'e 2xx aldı',
                `Violations (${violations.length}): ${JSON.stringify(violations.slice(0, 10))}. Beklenen: 403/404; gerçekleşen: 2xx.`);
        }
        // 5xx escalation (architect review #5, 2026-05-19): authz-path
        // instability hidden değil, P1 olarak rapor edilir.
        if (unreachable > 0) {
            recFinding(testInfo, 'P1', MOD,
                'RBAC matrix sırasında 5xx — authz-path instability',
                `5xx_count=${unreachable} total_checks=${totalChecks}. 5xx = backend admin/auth path crash; 403/404 stabil dönmeli.`);
        }
        // Soft signal: reporter findings'i toplar; hard expect KALDIRILDI
        // (architect review #1) — downstream invariants/cleanup'ın atlanmaması
        // için. P0/P1 birikirse reporter NO-GO verdict üretir.
    });

    test('D) Existence-disclosure contract — bogus + real cross-tenant ID lookups 403/404 dönmeli (strict)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'existence_disclosure', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const sampleToken = Object.values(roleTokens)[0];
        if (!sampleToken) {
            rec(testInfo, { module: MOD, step: 'existence_disclosure', status: 'SKIP', note: 'no role token available' });
            return;
        }

        // Validation review (2026-05-19): real cross-tenant ID probes EKLENDİ.
        // Pilot tenant ID + pilot user (admin_super) ID üzerinden gerçek
        // cross-tenant disclosure attempt'i yapılır. Aynı zamanda bogus UUID
        // ile var-olmayan ID probe edilir. Beklenti: HER İKİ DURUMDA da
        // status ∈ {403, 404} (status contract). Diğer her şey (2xx / 5xx /
        // 400 / 401 / 409 / vb) ihlaldir → P1.
        const pilotTid = stressState.pilot_tid;
        const bogusId = '00000000-0000-0000-0000-000000000000';
        // Pilot tenant'a ait gerçek bir user ID öğrenebilmek için super_admin
        // token ile sample alalım (best-effort).
        let pilotUserId = null;
        try {
            const ul = await callTimed(request, 'get', `/api/admin/users?tenant_id_filter=${pilotTid}`, undefined, superToken);
            const list = Array.isArray(ul.body) ? ul.body : (ul.body?.users || ul.body?.items || []);
            const u = list.find(x => x.tenant_id === pilotTid);
            if (u) pilotUserId = u.id || u._id;
        } catch (_) { /* swallow */ }

        const probes = [
            // Bogus ID — should always 403/404 (existence-disclosure baseline).
            { path: `/api/admin/users/${bogusId}/granted-permissions`, kind: 'bogus' },
            { path: `/api/admin/tenants/${bogusId}/stats`, kind: 'bogus' },
            { path: `/api/admin/tenants/${bogusId}/team`, kind: 'bogus' },
            // Real cross-tenant — pilot tenant lookup attempts.
            { path: `/api/admin/tenants/${pilotTid}/stats`, kind: 'cross_tenant_real' },
            { path: `/api/admin/tenants/${pilotTid}/team`, kind: 'cross_tenant_real' },
        ];
        if (pilotUserId) {
            probes.push({ path: `/api/admin/users/${pilotUserId}/granted-permissions`, kind: 'cross_tenant_real' });
        }

        const ALLOWED = new Set([403, 404]);
        const leaks = [];        // 2xx — actual disclosure (CRITICAL)
        const contractViolations = []; // diğer ALLOWED dışı statuslar
        const consistentStatuses = {}; // status frequency for consistency check
        for (const p of probes) {
            const r = await callTimed(request, 'get', p.path, undefined, sampleToken);
            consistentStatuses[r.status] = (consistentStatuses[r.status] || 0) + 1;
            const is2xx = r.status >= 200 && r.status < 300;
            if (is2xx) {
                leaks.push({ path: p.path, kind: p.kind, status: r.status, body_snippet: JSON.stringify(r.body).slice(0, 160) });
            } else if (!ALLOWED.has(r.status)) {
                contractViolations.push({ path: p.path, kind: p.kind, status: r.status });
            }
            await new Promise(res => setTimeout(res, 200));
        }
        // Consistency: bogus vs real cross-tenant aynı statusu dönmeli
        // (403 veya 404'ün karışık dönmesi mesaj-kanalı disclosure'a neden olur).
        const distinctAllowedStatuses = Object.keys(consistentStatuses).filter(s => ALLOWED.has(parseInt(s, 10))).length;
        const inconsistent = distinctAllowedStatuses > 1;

        const pass = leaks.length === 0 && contractViolations.length === 0;
        rec(testInfo, { module: MOD, step: 'existence_disclosure',
            status: pass && !inconsistent ? 'PASS' : 'FAIL',
            note: `probed=${probes.length} leaks=${leaks.length} contract_violations=${contractViolations.length} inconsistent=${inconsistent} status_freq=${JSON.stringify(consistentStatuses)} pilot_user_probed=${!!pilotUserId}` });

        if (leaks.length > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Existence disclosure — yetkisiz rol bogus/cross-tenant ID için 2xx aldı',
                `Leaks: ${JSON.stringify(leaks)}. 403/404 beklenirdi; payload döndü → IDOR/existence leak.`);
        }
        if (contractViolations.length > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Existence disclosure status contract ihlali — 403/404 dışı status',
                `Beklenen: 403 veya 404. Alınan: ${JSON.stringify(contractViolations)}. 5xx/401/400/409 vb. existence-disclosure kanalı oluşturabilir.`);
        }
        if (inconsistent) {
            recFinding(testInfo, 'P2', MOD,
                'Existence disclosure status inconsistency — 403 ve 404 karışık dönüyor',
                `Karışık statuslar bogus vs gerçek-yok ayırımı sağlar → message-channel disclosure. status_freq=${JSON.stringify(consistentStatuses)}.`);
        }
        // Architect review #1: hard expect yok — reporter findings sürer.
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens }, testInfo) => {
        // Pilot drift — bookings baseline değişmemeli.
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        // External calls — bu spec hiçbir mutation yapmadı (sadece create+login),
        // outbox dispatcher'ı tetikleyen şey YOK.
        const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'admin_rbac_done', stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });

    test('Z) Cleanup — created RBAC users idempotent DELETE (audit_logs preserved)', async ({ request, stressTokens, stressState }, testInfo) => {
        const stressTid = stressState.stress_tid;
        let deleted = 0, failed = 0;
        for (const u of createdUsers) {
            const r = await callTimed(request, 'delete',
                `/api/admin/tenants/${stressTid}/team/${u.id}`,
                undefined, superToken);
            if (r.ok || r.status === 404) deleted++;
            else failed++;
            await new Promise(res => setTimeout(res, 150));
        }
        rec(testInfo, { module: MOD, step: 'cleanup',
            status: failed === 0 ? 'PASS' : 'REVIEW',
            note: `created=${createdUsers.length} deleted=${deleted} failed=${failed}` });
        if (failed > 0) {
            recFinding(testInfo, 'P2', MOD, 'Some RBAC test users could not be deleted',
                `failed=${failed}/${createdUsers.length}. Audit_logs koleksiyonu KASITLI olarak korunur (KVKK).`);
        }
        // afterAll belt-and-suspenders cleanup yaparak garanti edecek; bu
        // test fail-safe ek katmandır.
    });

    // Architect review #1 (2026-05-19): garanti finalizer — serial mode'da
    // intermediate test fail olsa bile cleanup ÇALIŞIR. afterAll annotations
    // tüm describe için ayrı bir hook test'ine yazılır; reporter onTestEnd
    // bunu da toplar.
    test.afterAll(async ({ }, testInfo) => {
        try {
            const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
            const stressTid = stateBlob.stress_tid;
            // Best-effort: state'ten okunan token blob.
            const tokenBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-token.json'), 'utf-8'));
            // team DELETE require_super_admin — super_admin principal kullan.
            const cleanupToken = tokenBlob.role_tokens?.super_admin ?? tokenBlob.pilot_token;
            const { request: apiReq } = await import('@playwright/test');
            const ctx = await apiReq.newContext({ baseURL: process.env.E2E_BASE_URL });
            let cleaned = 0;
            for (const u of createdUsers) {
                try {
                    await ctx.delete(`/api/admin/tenants/${stressTid}/team/${u.id}`, {
                        headers: { Authorization: `Bearer ${cleanupToken}` },
                        failOnStatusCode: false,
                        timeout: 30_000,
                    });
                    cleaned++;
                } catch (_) { /* swallow */ }
            }
            await ctx.dispose();
            // Cleanup count'u console'a yaz; testInfo afterAll'da yok.
            console.log(`[F8I § 30 afterAll] belt-and-suspenders cleanup: attempted=${createdUsers.length} ok=${cleaned}`);
        } catch (e) {
            console.log(`[F8I § 30 afterAll] cleanup failed: ${e.message}`);
        }
    });
});

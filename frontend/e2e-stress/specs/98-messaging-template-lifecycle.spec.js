// ─────────────────────────────────────────────────────────────────────────
// F9C § 98 — Messaging Template Lifecycle Deep Stress (Spec 2/7).
// ─────────────────────────────────────────────────────────────────────────
//
// Scope (TEST_COVERAGE_GAP_MAP_20260527.md §3.1 — messaging modülü 159
//   endpoint ZERO/PARTIAL idi; pilot otel SMS/email template oluşturuyor →
//   G7 HIGH risk):
//   Backend: backend/routers/messaging.py  (prefix=/api/messaging-center)
//   Yüzey:
//     A) GET    /api/messaging-center/templates           (list + module probe)
//     B) POST   /api/messaging-center/templates           (create, tagged)
//     C) GET    /api/messaging-center/templates           (list after create — verify tenant scope + presence)
//     D) PUT    /api/messaging-center/templates/{id}      (update body)
//     E) POST   /api/messaging-center/templates           (template-injection payload — must store-as-data, no exec/leak)
//     F) GET    /api/messaging-center/providers           (provider list — credentials_encrypted projection check)
//     G) POST   /api/messaging-center/settings/test-connection  (sandbox: no real outbound)
//     H) GET    /api/messaging-center/metrics             (read-only metrics)
//     I) GET    /api/messaging-center/delivery-logs       (PII/role-gated read)
//     J) IDOR   PUT /templates/{stress_id} with PILOT token → 4xx (no cross-tenant update)
//     J2) IDOR  DELETE /templates/{stress_id} with PILOT token → 4xx
//     J3) IDOR  PUT /templates/{pilot_id} with STRESS token → 4xx (canonical doctrine direction;
//               harvest real pilot template id first with pilot token, bogus UUID fallback)
//     J4) IDOR  DELETE /templates/{pilot_id} with STRESS token → 4xx (doctrine direction)
//     D2) DELETE lifecycle — stress deletes own template, then GET 404 + idempotent re-DELETE 404
//     A1) AUTOMATION RULES CRUD — list triggers + create rule + update + delete (tenant-scoped, idempotent)
//     S1) SCHEDULER STATUS probe — GET /scheduler/status (read-only, no start/stop)
//     K) ANON   GET /templates (headerless) → 401/403 (PUBLIC SURFACE LEAK guard)
//     L) PII/TOKEN LEAK SCAN — assertNoTokenLeak on every response body
//     M) INVARIANT — assertNoExternalCallsPostBatch (external_calls=[])
//     N) INVARIANT — assertPilotDriftZero (booking count + pilot template prefix scan)
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = [] (assertNoExternalCallsPostBatch)
//   - pilot mutation = 0 (assertPilotDriftZero primary + supplemental)
//   - P0 = P1 = 0; 5xx = 0; PII/token leak = 0
//   - skip-as-pass YOK; module-blocked → test.skip(true, reason)
//   - DESTRUCTIVE OUTBOUND ÇAĞRI YOK: POST /send + POST /send-template
//     deliberately omitted — provider sandbox=True bile olsa outbox
//     dispatcher path'i kapsam dışı (cleanup riski + delivery-log noise).
//     G (test-connection) sadece is_sandbox=True provider'da non-2xx
//     döndüğünde REVIEW; gerçek transport sandbox handler içinde tutulur.
//   - Tüm template name + body_template `${prefix}_F9C_MSG` ile tag'lenir;
//     afterAll DELETE /templates/{id} idempotent.
//   - IDOR doktrin: REAL stress template id ile pilot token PUT/DELETE dene
//     (real-id-first, no bogus-only). 200/204 = P0 cross-tenant breach.
//
// Reporter satırı: `messaging_template`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertNoTokenLeak, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'messaging_template';
const SUB_PREFIX = 'F9C_MSG';
const GAP_MS = 1500;
const BASE = '/api/messaging-center';

test.describe.configure({ mode: 'serial' });

test.describe('F9C § 98 — Messaging Template Lifecycle', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBookingBaseline = null;
    const createdTemplateIds = [];
    const createdAutomationRuleIds = [];

    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }
    function taggedName(label) {
        return `${prefix}_${SUB_PREFIX}_${label}`;
    }
    function leakScan(testInfo, body, label) {
        // Template-creation responses legitimately echo subject/body_template;
        // no token-issuance fields in messaging surface.
        assertNoTokenLeak(testInfo, MOD, body, label, { allowedTokenKeys: [], allowedJwtPaths: [] });
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: stress token + module probe + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        // Pilot baseline: bookings count snapshot for drift gate N.
        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBookingBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;
        }

        // Module probe: GET /templates with stress token.
        const probe = await callTimed(
            request, 'get', `${BASE}/templates`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (probe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Messaging module 5xx on setup probe',
                `GET ${BASE}/templates → ${probe.status}; body=${JSON.stringify(probe.body || {}).slice(0, 200)}`);
            expect(probe.status, 'Messaging setup 5xx').toBeLessThan(500);
        }
        // Architect F9C doctrine: any non-2xx → module-blocked (not just 401/403/404/501).
        if (probe.status < 200 || probe.status >= 300) {
            moduleBlocked = true;
            blockedReason = `setup_probe_${probe.status}`;
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'REVIEW',
                http: probe.status, note: 'Module blocked / not deployed — A-I SKIP, J/J2/K independent.',
            });
            recFinding(testInfo, 'P2', MOD,
                `Messaging module blocked at setup (${probe.status})`,
                'B-I lifecycle SKIP; security probes (J/J2/K) bağımsız çalışır.');
            return;
        }
        leakScan(testInfo, probe.body, 'setup_probe_list');
        rec(testInfo, {
            module: MOD, step: 'module_probe', status: 'PASS',
            http: probe.status, note: 'GET templates 2xx — lifecycle aktif.',
        });
    });

    // ──────────────────────────────────────────────────────────────
    // B) CREATE — stress-tenant scoped, tagged for cleanup
    test('B) Create template — stress-tenant scoped', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'B_create', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const payload = {
            name: taggedName('B_create'),
            category: 'rezervasyon_onay',
            channel: 'email',
            subject: `${prefix} ${SUB_PREFIX} subject`,
            body_template: `Merhaba {{misafir_adi}}, ${prefix} ${SUB_PREFIX} body. Konfirmasyon: {{konfirmasyon_no}}.`,
            variables: ['misafir_adi', 'konfirmasyon_no'],
        };
        const r = await callTimed(
            request, 'post', `${BASE}/templates`, payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('B_create') } },
        );
        recPerf(testInfo, MOD, 'B_create', [r.ms], r.status >= 200 && r.status < 300);

        if ([403, 404, 501].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'B_create', status: 'REVIEW', http: r.status, note: 'create endpoint not deployed / role denied' });
            recFinding(testInfo, 'P2', MOD, `POST ${BASE}/templates not available`, `status=${r.status}`);
            return;
        }
        expect(r.status, `B_create unexpected status=${r.status}`).toBeLessThan(500);
        expect(r.status, `B_create non-2xx status=${r.status}`).toBeGreaterThanOrEqual(200);
        expect(r.status).toBeLessThan(300);

        const tmpl = r.body || {};
        expect(tmpl.id, 'created template id yok').toBeTruthy();
        expect(tmpl.tenant_id, 'template tenant_id yok').toBeTruthy();
        createdTemplateIds.push(tmpl.id);
        leakScan(testInfo, tmpl, 'B_create_response');

        rec(testInfo, {
            module: MOD, step: 'B_create', status: 'PASS',
            http: r.status, note: `created template_id=${tmpl.id}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // C) LIST AFTER CREATE — verify tenant scope + created template present
    test('C) List templates — tenant scope + created presence', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdTemplateIds.length === 0 ? 'no_template_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'C_list', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const r = await callTimed(
            request, 'get', `${BASE}/templates`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `C_list 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `C_list non-200 status=${r.status}`, `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'C_list', status: 'REVIEW', http: r.status });
            return;
        }
        leakScan(testInfo, r.body, 'C_list_response');
        const items = (r.body && r.body.templates) || [];
        expect(Array.isArray(items), 'C_list templates array değil').toBe(true);

        // Tenant scoping invariant: every returned template must carry tenant_id.
        for (const it of items) {
            expect(it.tenant_id, `C_list item tenant_id yok: ${JSON.stringify(it).slice(0, 100)}`).toBeTruthy();
        }
        // Created template must surface here.
        const found = items.find(t => t.id === createdTemplateIds[0]);
        expect(found, `C_list created template ${createdTemplateIds[0]} not present in own-tenant list`).toBeTruthy();

        rec(testInfo, {
            module: MOD, step: 'C_list', status: 'PASS',
            http: r.status, note: `items=${items.length} created_present=true`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // D) UPDATE — PUT /templates/{id} (mutate name + body)
    test('D) Update template body', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdTemplateIds.length === 0 ? 'no_template_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'D_update', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const id = createdTemplateIds[0];
        const newBody = `Updated ${prefix} ${SUB_PREFIX} body. {{misafir_adi}} {{konfirmasyon_no}} {{tarih}}.`;
        const r = await callTimed(
            request, 'put', `${BASE}/templates/${id}`,
            { body_template: newBody, variables: ['misafir_adi', 'konfirmasyon_no', 'tarih'] },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('D_update') } },
        );
        expect(r.status, `D_update 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD,
                `D_update non-200 status=${r.status}`,
                `template_id=${id} body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'D_update', status: 'REVIEW', http: r.status });
            return;
        }
        leakScan(testInfo, r.body, 'D_update_response');
        expect(r.body?.success, 'D_update success flag yok').toBe(true);
        rec(testInfo, { module: MOD, step: 'D_update', status: 'PASS', http: r.status });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // E) TEMPLATE INJECTION — create with payload designed to detect server-side
    //    template execution / XSS / SSTI; expect store-as-data only.
    test('E) Template-injection payload stored-as-data (no exec/leak)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'E_injection', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        // SSTI sentinels: Jinja2 {{7*7}}, ERB <%= %>, Mustache section, raw JWT-shape
        // sentinel (must NOT be reflected back as a decoded value). Backend should
        // persist these as literal strings — never evaluate.
        const sentinel = `INJ_${Date.now()}_${cryptoRandomUUID().slice(0, 8)}`;
        const payload = {
            name: taggedName('E_injection'),
            category: 'rezervasyon_onay',
            channel: 'email',
            subject: `${sentinel} {{7*7}} <%= 7*7 %>`,
            body_template: `${sentinel} {{7*7}} {{config}} <%= File.read('/etc/passwd') %> eyJhbGciOiJIUzI1NiJ9.fake.fake_sentinel`,
            variables: [],
        };
        const r = await callTimed(
            request, 'post', `${BASE}/templates`, payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('E_injection') } },
        );
        expect(r.status, `E_injection 5xx status=${r.status}`).toBeLessThan(500);

        if (r.status >= 200 && r.status < 300 && r.body?.id) {
            createdTemplateIds.push(r.body.id);
            // Backend MUST NOT have evaluated the SSTI payload — verify exact
            // sentinel is echoed back literally (no `49`/`config dump`/file content).
            const subj = r.body?.subject ?? '';
            const tmpl = r.body?.body_template ?? '';
            expect(subj.includes('{{7*7}}'), `E_injection: subject SSTI evaluated → ${subj.slice(0, 120)}`).toBe(true);
            expect(tmpl.includes('{{7*7}}'), 'E_injection: body SSTI evaluated').toBe(true);
            expect(tmpl.includes(sentinel), 'E_injection: sentinel missing → backend mutated payload').toBe(true);
            // The fake JWT-shape literal is part of the user-submitted body and
            // is therefore an expected echo, NOT a leak. We deliberately do NOT
            // run assertNoTokenLeak here because it would FP on our own input.
            // Instead, explicitly assert no REAL secret material was injected
            // by the backend (e.g. config dump shouldn't include the literal
            // string "JWT_SECRET" or env var values).
            const combined = `${subj}\n${tmpl}`;
            for (const forbidden of ['JWT_SECRET', 'MONGO_URL', 'SECRET_KEY', 'BEGIN PRIVATE KEY']) {
                expect(combined.includes(forbidden), `E_injection: backend leaked '${forbidden}' into stored template`).toBe(false);
            }
            rec(testInfo, {
                module: MOD, step: 'E_injection', status: 'PASS',
                http: r.status, note: 'payload stored-as-data; SSTI not evaluated; no secret leak',
            });
        } else if (r.status === 400 || r.status === 422) {
            // Backend rejected the payload outright — also acceptable.
            rec(testInfo, {
                module: MOD, step: 'E_injection', status: 'PASS',
                http: r.status, note: 'payload rejected by validation (acceptable)',
            });
        } else {
            recFinding(testInfo, 'P2', MOD, `E_injection unexpected status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'E_injection', status: 'REVIEW', http: r.status });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // F) PROVIDERS LIST — credentials_encrypted MUST NOT be in response.
    test('F) GET /providers — no credentials leak', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'F_providers', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', `${BASE}/providers`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `F_providers 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `F_providers non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'F_providers', status: 'REVIEW', http: r.status });
            return;
        }
        // Backend projection excludes credentials_encrypted — verify.
        // Round-2 architect fix: shallow hasOwnProperty would miss nested
        // leaks like credentials.smtp_password. Walk the entire provider
        // payload recursively and hard-fail on ANY forbidden key at ANY depth.
        const providers = r.body?.providers || [];
        const FORBIDDEN_KEYS = new Set([
            'credentials_encrypted',
            'smtp_password',
            'access_token',
            'app_secret',
            'webhook_verify_token',
        ]);
        function scanForbidden(node, pathParts, hits) {
            if (node == null || hits.length >= 10) return;
            if (Array.isArray(node)) {
                node.forEach((v, i) => scanForbidden(v, [...pathParts, `[${i}]`], hits));
                return;
            }
            if (typeof node === 'object') {
                for (const [k, v] of Object.entries(node)) {
                    if (FORBIDDEN_KEYS.has(k)) {
                        hits.push({ key: k, path: [...pathParts, k].join('.') });
                    }
                    scanForbidden(v, [...pathParts, k], hits);
                }
            }
        }
        for (const p of providers) {
            const hits = [];
            scanForbidden(p, [`provider(${p.provider_type ?? 'unknown'})`], hits);
            if (hits.length > 0) {
                for (const h of hits) {
                    recFinding(testInfo, 'P0', MOD,
                        `F_providers: forbidden credential key '${h.key}' present at ${h.path}`,
                        `provider_type=${p.provider_type}`);
                }
                expect(hits.length, `F_providers: forbidden credential keys leaked: ${hits.map(h => h.path).join(', ')}`).toBe(0);
            }
        }
        leakScan(testInfo, r.body, 'F_providers_response');
        rec(testInfo, { module: MOD, step: 'F_providers', status: 'PASS', http: r.status, note: `providers=${providers.length}` });
    });

    // ──────────────────────────────────────────────────────────────
    // F2) POST /providers/health-check — read-only diagnostic probe.
    //     The endpoint is POST by FastAPI route shape but is semantically
    //     read-only (calls into provider.check() health probes). We accept
    //     200/202 with a `results` map, 401/403/404 if RBAC denies the
    //     stress role view_system_diagnostics, and treat anything else as
    //     REVIEW. NO mutating outcome is asserted. external_calls=[] is
    //     enforced by the suite-level fixture; this test additionally
    //     leak-scans the response for credentials.
    test('F2) POST /providers/health-check read-only probe', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'F2_providers_health_check', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'post', `${BASE}/providers/health-check`, {},
            stressTokens.stress_token, { timeout: 15_000 },
        );
        expect(r.status, `F2_providers_health_check 5xx status=${r.status}`).toBeLessThan(500);
        if ([401, 403].includes(r.status)) {
            // RBAC deny on view_system_diagnostics is acceptable for the
            // stress role — record as PASS (boundary held) not REVIEW.
            rec(testInfo, { module: MOD, step: 'F2_providers_health_check', status: 'PASS', http: r.status, note: 'rbac_deny_acceptable' });
            return;
        }
        if (r.status === 404) {
            // Endpoint absent on this deploy → REVIEW (coverage gap), not PASS.
            recFinding(testInfo, 'P2', MOD, `F2_providers_health_check 404 — endpoint missing on this deploy`, '');
            rec(testInfo, { module: MOD, step: 'F2_providers_health_check', status: 'REVIEW', http: r.status });
            return;
        }
        if (r.status >= 200 && r.status < 300) {
            // Credential leak guard — same FORBIDDEN_KEYS as F.
            const FORBIDDEN_KEYS = new Set([
                'credentials_encrypted', 'smtp_password', 'access_token',
                'app_secret', 'webhook_verify_token',
            ]);
            function walk(node, parts, hits) {
                if (node == null || hits.length >= 10) return;
                if (Array.isArray(node)) {
                    node.forEach((v, i) => walk(v, [...parts, `[${i}]`], hits));
                    return;
                }
                if (typeof node === 'object') {
                    for (const [k, v] of Object.entries(node)) {
                        if (FORBIDDEN_KEYS.has(k)) hits.push([...parts, k].join('.'));
                        walk(v, [...parts, k], hits);
                    }
                }
            }
            const hits = [];
            walk(r.body, ['health'], hits);
            if (hits.length > 0) {
                for (const h of hits) {
                    recFinding(testInfo, 'P0', MOD,
                        `F2_providers_health_check: forbidden credential key leaked at ${h}`, '');
                }
                expect(hits.length, `F2_providers_health_check: leaked keys ${hits.join(', ')}`).toBe(0);
            }
            leakScan(testInfo, r.body, 'F2_providers_health_check_response');
            const resultsCount = Array.isArray(r.body?.results)
                ? r.body.results.length
                : (typeof r.body?.results === 'object' && r.body.results ? Object.keys(r.body.results).length : 0);
            rec(testInfo, { module: MOD, step: 'F2_providers_health_check', status: 'PASS', http: r.status, note: `results=${resultsCount}` });
            return;
        }
        recFinding(testInfo, 'P2', MOD, `F2_providers_health_check unexpected status=${r.status}`, '');
        rec(testInfo, { module: MOD, step: 'F2_providers_health_check', status: 'REVIEW', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // G) test-connection — sandbox path, NO real outbound expected.
    test('G) POST /settings/test-connection — sandbox safe', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'G_test_conn', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'post', `${BASE}/settings/test-connection`, {},
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('G_test_conn') } },
        );
        expect(r.status, `G_test_conn 5xx status=${r.status}`).toBeLessThan(500);
        // Acceptable: 200 (sandbox results) or 403 (RBAC denies stress token).
        // M invariant will independently catch any real external dispatch.
        if (r.status === 200 || r.status === 403) {
            leakScan(testInfo, r.body, 'G_test_conn_response');
            rec(testInfo, { module: MOD, step: 'G_test_conn', status: 'PASS', http: r.status });
        } else {
            recFinding(testInfo, 'P2', MOD, `G_test_conn non-200/403 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'G_test_conn', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // H) METRICS read-only
    test('H) GET /metrics read-only', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'H_metrics', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', `${BASE}/metrics?days=7`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `H_metrics 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `H_metrics non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'H_metrics', status: 'REVIEW', http: r.status });
            return;
        }
        leakScan(testInfo, r.body, 'H_metrics_response');
        rec(testInfo, { module: MOD, step: 'H_metrics', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // I) DELIVERY LOGS — PII gated (view_guest_list permission).
    test('I) GET /delivery-logs — RBAC + PII guard', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'I_delivery_logs', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', `${BASE}/delivery-logs?limit=10`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `I_delivery_logs 5xx`).toBeLessThan(500);
        // Acceptable: 200 (admin-grade) or 403 (RBAC denies). Both prove the
        // route is reachable; PII surface is gated.
        if (r.status === 200) {
            leakScan(testInfo, r.body, 'I_delivery_logs_response');
            const logs = r.body?.logs || [];
            // Tenant scoping invariant — read-only walk.
            for (const log of logs) {
                if (log.tenant_id != null) {
                    // Best-effort: cannot dereference stress_tid here without
                    // stressState; rely on B–D tenant_id checks. Just assert
                    // truthy when present.
                    expect(log.tenant_id, 'delivery log tenant_id falsy').toBeTruthy();
                }
            }
            rec(testInfo, { module: MOD, step: 'I_delivery_logs', status: 'PASS', http: r.status, note: `logs=${logs.length}` });
        } else if (r.status === 403) {
            rec(testInfo, { module: MOD, step: 'I_delivery_logs', status: 'PASS', http: r.status, note: 'RBAC denied (view_guest_list gate)' });
        } else {
            recFinding(testInfo, 'P2', MOD, `I_delivery_logs unexpected status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'I_delivery_logs', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // J) IDOR — cross-tenant PUT with PILOT token on STRESS template id.
    //    Real-id-first doctrine: bogus UUID fallback only if no template
    //    was created. 2xx = P0 cross-tenant tampering breach.
    test('J) IDOR cross-tenant PUT (pilot→stress template) → 4xx', async ({ request, stressTokens }, testInfo) => {
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'J_idor_put', status: 'SKIP', note: 'pilot_token yok' });
            test.skip(true, 'pilot_token yok');
        }
        const targetId = createdTemplateIds[0] || `bogus-${cryptoRandomUUID()}`;
        const probeKind = createdTemplateIds[0] ? 'real_stress_template_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'put', `${BASE}/templates/${targetId}`,
            { body_template: 'IDOR_BREACH_ATTEMPT' },
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        expect(r.status, `J_idor_put 5xx status=${r.status}`).toBeLessThan(500);
        // Round-2 architect fix: ANY 2xx (200/201/202/204) on a REAL stress
        // template id with PILOT token is a P0 cross-tenant tampering breach.
        // Previous "200+success=true only" gate would let 204 No Content or
        // 200+success=false slip past as REVIEW. Doctrine: real-id 2xx == P0.
        const is2xx = r.status >= 200 && r.status < 300;
        if (is2xx && probeKind === 'real_stress_template_id') {
            recFinding(testInfo, 'P0', MOD,
                `IDOR boundary breach: cross-tenant PUT returned ${r.status} on real stress template id`,
                `target_id=${targetId} response=${JSON.stringify(r.body).slice(0, 200)}`);
            expect(false, `J_idor_put: pilot token reached stress template ${targetId} (status=${r.status})`).toBe(true);
        }
        if ([404, 403, 401].includes(r.status) && probeKind === 'real_stress_template_id') {
            rec(testInfo, { module: MOD, step: 'J_idor_put', status: 'PASS', http: r.status, note: `${probeKind} rejected ${r.status}` });
        } else if ([404, 403, 401].includes(r.status) && probeKind === 'bogus_uuid_fallback') {
            // Doctrine: bogus fallback never produces a clean PASS — even a
            // 401/403/404 here means the real cross-tenant boundary was
            // not exercised, so the row must surface as REVIEW (not PASS).
            recFinding(testInfo, 'P2', MOD,
                `J_idor_put bogus-UUID fallback (no stress template existed) — boundary not exercised`,
                `status=${r.status} — re-run after B_create succeeds to get authoritative coverage`);
            rec(testInfo, { module: MOD, step: 'J_idor_put', status: 'REVIEW', http: r.status, note: 'bogus_fallback_not_authoritative' });
        } else if (is2xx && probeKind === 'bogus_uuid_fallback') {
            recFinding(testInfo, 'P2', MOD, `J_idor_put bogus UUID returned ${r.status} — unexpected`,
                `body=${JSON.stringify(r.body).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'J_idor_put', status: 'REVIEW', http: r.status });
        } else {
            recFinding(testInfo, 'P2', MOD, `J_idor_put unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J_idor_put', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // J2) IDOR — cross-tenant DELETE with PILOT token.
    test('J2) IDOR cross-tenant DELETE (pilot→stress template) → 4xx', async ({ request, stressTokens }, testInfo) => {
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'J2_idor_del', status: 'SKIP', note: 'pilot_token yok' });
            test.skip(true, 'pilot_token yok');
        }
        const targetId = createdTemplateIds[0] || `bogus-${cryptoRandomUUID()}`;
        const probeKind = createdTemplateIds[0] ? 'real_stress_template_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'delete', `${BASE}/templates/${targetId}`, null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        expect(r.status, `J2_idor_del 5xx status=${r.status}`).toBeLessThan(500);
        // Round-2 architect fix: ANY 2xx (200/201/202/204) on a REAL stress
        // template id with PILOT token is a P0 cross-tenant DELETE breach.
        // Mirrors J_idor_put logic — DELETE often returns 204 No Content on
        // success, which the previous "200+success=true only" gate missed.
        const is2xx = r.status >= 200 && r.status < 300;
        if (is2xx && probeKind === 'real_stress_template_id') {
            recFinding(testInfo, 'P0', MOD,
                `IDOR boundary breach: cross-tenant DELETE returned ${r.status} on real stress template id`,
                `target_id=${targetId} response=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            expect(false, `J2_idor_del: pilot token reached stress template ${targetId} (status=${r.status})`).toBe(true);
        }
        if ([404, 403, 401].includes(r.status) && probeKind === 'real_stress_template_id') {
            rec(testInfo, { module: MOD, step: 'J2_idor_del', status: 'PASS', http: r.status, note: `${probeKind} rejected ${r.status}` });
        } else if ([404, 403, 401].includes(r.status) && probeKind === 'bogus_uuid_fallback') {
            recFinding(testInfo, 'P2', MOD,
                `J2_idor_del bogus-UUID fallback (no stress template existed) — boundary not exercised`,
                `status=${r.status} — re-run after B_create succeeds for authoritative coverage`);
            rec(testInfo, { module: MOD, step: 'J2_idor_del', status: 'REVIEW', http: r.status, note: 'bogus_fallback_not_authoritative' });
        } else if (is2xx && probeKind === 'bogus_uuid_fallback') {
            recFinding(testInfo, 'P2', MOD, `J2_idor_del bogus UUID returned ${r.status} — unexpected`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'J2_idor_del', status: 'REVIEW', http: r.status });
        } else {
            recFinding(testInfo, 'P2', MOD, `J2_idor_del unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J2_idor_del', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // J3) IDOR — STRESS token attempting PUT on PILOT template (doctrine direction).
    //     Harvest pilot template id first with pilot token; bogus UUID fallback.
    //     2xx on real pilot id = P0 cross-tenant tampering breach.
    test('J3) IDOR doctrine PUT (stress→pilot template) → 4xx', async ({ request, stressTokens }, testInfo) => {
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'J3_idor_put_doctrine', status: 'SKIP', note: 'pilot_token yok' });
            test.skip(true, 'pilot_token yok');
        }
        // Harvest a real pilot template id (read-only with pilot token).
        let pilotTemplateId = null;
        const harvest = await callTimed(
            request, 'get', `${BASE}/templates`, null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        if (harvest.status === 200 && Array.isArray(harvest.body?.templates) && harvest.body.templates.length > 0) {
            const first = harvest.body.templates.find(t => t.id) || null;
            pilotTemplateId = first?.id || null;
        }
        const targetId = pilotTemplateId || `bogus-${cryptoRandomUUID()}`;
        const probeKind = pilotTemplateId ? 'real_pilot_template_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'put', `${BASE}/templates/${targetId}`,
            { body_template: 'IDOR_BREACH_ATTEMPT_DOCTRINE_DIRECTION' },
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `J3_idor_put_doctrine 5xx status=${r.status}`).toBeLessThan(500);
        const is2xx = r.status >= 200 && r.status < 300;
        if (is2xx && probeKind === 'real_pilot_template_id') {
            recFinding(testInfo, 'P0', MOD,
                `IDOR doctrine-direction breach: stress token PUT pilot template returned ${r.status}`,
                `target_id=${targetId} response=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            expect(false, `J3_idor_put_doctrine: stress token reached pilot template ${targetId} (status=${r.status})`).toBe(true);
        }
        if ([404, 403, 401].includes(r.status) && probeKind === 'real_pilot_template_id') {
            rec(testInfo, { module: MOD, step: 'J3_idor_put_doctrine', status: 'PASS', http: r.status, note: `${probeKind} rejected ${r.status}` });
        } else if ([404, 403, 401].includes(r.status) && probeKind === 'bogus_uuid_fallback') {
            // Doctrine: bogus fallback never produces a clean PASS — even a
            // 401/403/404 means the real cross-tenant boundary was not
            // exercised against a live pilot object, so this is REVIEW.
            recFinding(testInfo, 'P2', MOD,
                `J3_idor_put_doctrine bogus-UUID fallback (pilot has no template) — boundary not exercised`,
                `status=${r.status} — seed a pilot template so the doctrine direction can probe a real id`);
            rec(testInfo, { module: MOD, step: 'J3_idor_put_doctrine', status: 'REVIEW', http: r.status, note: 'bogus_fallback_not_authoritative' });
        } else if (is2xx && probeKind === 'bogus_uuid_fallback') {
            recFinding(testInfo, 'P2', MOD, `J3_idor_put_doctrine bogus UUID returned ${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'J3_idor_put_doctrine', status: 'REVIEW', http: r.status });
        } else {
            recFinding(testInfo, 'P2', MOD, `J3_idor_put_doctrine unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J3_idor_put_doctrine', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // J4) IDOR — STRESS token attempting DELETE on PILOT template (doctrine direction).
    test('J4) IDOR doctrine DELETE (stress→pilot template) → 4xx', async ({ request, stressTokens }, testInfo) => {
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'J4_idor_del_doctrine', status: 'SKIP', note: 'pilot_token yok' });
            test.skip(true, 'pilot_token yok');
        }
        let pilotTemplateId = null;
        const harvest = await callTimed(
            request, 'get', `${BASE}/templates`, null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        if (harvest.status === 200 && Array.isArray(harvest.body?.templates) && harvest.body.templates.length > 0) {
            const first = harvest.body.templates.find(t => t.id) || null;
            pilotTemplateId = first?.id || null;
        }
        const targetId = pilotTemplateId || `bogus-${cryptoRandomUUID()}`;
        const probeKind = pilotTemplateId ? 'real_pilot_template_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'delete', `${BASE}/templates/${targetId}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `J4_idor_del_doctrine 5xx status=${r.status}`).toBeLessThan(500);
        const is2xx = r.status >= 200 && r.status < 300;
        if (is2xx && probeKind === 'real_pilot_template_id') {
            recFinding(testInfo, 'P0', MOD,
                `IDOR doctrine-direction DELETE breach: stress token DELETE pilot template returned ${r.status}`,
                `target_id=${targetId} response=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            expect(false, `J4_idor_del_doctrine: stress token DELETED pilot template ${targetId}`).toBe(true);
        }
        if ([404, 403, 401].includes(r.status) && probeKind === 'real_pilot_template_id') {
            rec(testInfo, { module: MOD, step: 'J4_idor_del_doctrine', status: 'PASS', http: r.status, note: `${probeKind} rejected ${r.status}` });
        } else if ([404, 403, 401].includes(r.status) && probeKind === 'bogus_uuid_fallback') {
            recFinding(testInfo, 'P2', MOD,
                `J4_idor_del_doctrine bogus-UUID fallback (pilot has no template) — boundary not exercised`,
                `status=${r.status} — seed a pilot template for authoritative coverage`);
            rec(testInfo, { module: MOD, step: 'J4_idor_del_doctrine', status: 'REVIEW', http: r.status, note: 'bogus_fallback_not_authoritative' });
        } else if (is2xx && probeKind === 'bogus_uuid_fallback') {
            recFinding(testInfo, 'P2', MOD, `J4_idor_del_doctrine bogus UUID returned ${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'J4_idor_del_doctrine', status: 'REVIEW', http: r.status });
        } else {
            recFinding(testInfo, 'P2', MOD, `J4_idor_del_doctrine unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J4_idor_del_doctrine', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // D2) DELETE LIFECYCLE — stress deletes one of its own templates, then
    //     verifies GET returns 404 and a second DELETE is idempotent (404, not 5xx).
    //     This is a POSITIVE assertion that the documented DELETE contract
    //     actually works for the owning tenant — the afterAll sweep alone does
    //     not exercise the post-delete read-back or idempotency guarantees.
    test('D2) DELETE lifecycle — own template hard-delete + idempotent re-DELETE', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdTemplateIds.length === 0 ? 'no_template_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'D2_delete_lifecycle', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        // Create a dedicated throwaway template so D2 doesn't disturb the
        // template the IDOR tests target via createdTemplateIds[0].
        const payload = {
            name: taggedName('D2_delete'),
            category: 'rezervasyon_onay',
            channel: 'email',
            subject: `${prefix} ${SUB_PREFIX} D2 subject`,
            body_template: `D2 delete-lifecycle ${prefix} ${SUB_PREFIX} body.`,
            variables: [],
        };
        const created = await callTimed(
            request, 'post', `${BASE}/templates`, payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('D2_create') } },
        );
        if (!(created.status >= 200 && created.status < 300) || !created.body?.id) {
            rec(testInfo, { module: MOD, step: 'D2_delete_lifecycle', status: 'SKIP',
                note: `create-for-delete failed status=${created.status}` });
            test.skip(true, `D2 create-for-delete failed status=${created.status}`);
        }
        const tid = created.body.id;
        // Track for safety-net cleanup in case any of the steps below fails
        // before our explicit DELETE — afterAll will idempotently sweep it.
        createdTemplateIds.push(tid);

        // First DELETE — must return 2xx.
        const del1 = await callTimed(
            request, 'delete', `${BASE}/templates/${tid}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(del1.status, `D2 first DELETE 5xx status=${del1.status}`).toBeLessThan(500);
        expect(del1.status, `D2 first DELETE non-2xx status=${del1.status}`).toBeGreaterThanOrEqual(200);
        expect(del1.status, `D2 first DELETE non-2xx status=${del1.status}`).toBeLessThan(300);

        // Read-back: GET should now 404 (or list should not contain id).
        const after = await callTimed(
            request, 'get', `${BASE}/templates`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (after.status === 200 && Array.isArray(after.body?.templates)) {
            const stillPresent = after.body.templates.find(t => t.id === tid);
            expect(stillPresent, `D2 deleted template ${tid} still present in list — soft delete leak`).toBeFalsy();
        }

        // Second DELETE — idempotency contract: must be 404 (or 2xx no-op),
        // never 5xx. 404 is the documented behaviour per messaging.py:387.
        const del2 = await callTimed(
            request, 'delete', `${BASE}/templates/${tid}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(del2.status, `D2 second DELETE 5xx status=${del2.status}`).toBeLessThan(500);
        if (![404, 200, 204].includes(del2.status)) {
            recFinding(testInfo, 'P2', MOD,
                `D2 re-DELETE unexpected status=${del2.status} (expected 404 idempotent)`,
                `template_id=${tid}`);
        }
        rec(testInfo, {
            module: MOD, step: 'D2_delete_lifecycle', status: 'PASS',
            http: del1.status, note: `delete=${del1.status} readback_ok re-delete=${del2.status}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // A1) AUTOMATION RULES CRUD — list triggers + create rule + update + delete.
    //     Tenant-scoped, idempotent, tagged for cleanup. Uses a template id we
    //     created earlier (createdTemplateIds[0]). Skip if no template.
    test('A1) Automation rules CRUD (list triggers + create + update + delete)', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdTemplateIds.length === 0 ? 'no_template_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'A1_automation_crud', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        // A1.1 — list triggers
        const triggers = await callTimed(
            request, 'get', `${BASE}/automation/triggers`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(triggers.status, `A1.1 triggers 5xx status=${triggers.status}`).toBeLessThan(500);
        if (triggers.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `A1.1 triggers non-200 status=${triggers.status}`, '');
            rec(testInfo, { module: MOD, step: 'A1_automation_crud', status: 'REVIEW', http: triggers.status,
                note: 'triggers list unavailable — CRUD path not exercisable' });
            return;
        }
        leakScan(testInfo, triggers.body, 'A1_triggers');
        const trigList = triggers.body?.triggers || [];
        // backend returns either dict-of-events or list-of-strings — pick first reasonable trigger.
        const firstTrigger = (Array.isArray(trigList) && trigList.length > 0)
            ? (typeof trigList[0] === 'string' ? trigList[0] : trigList[0]?.event)
            : (typeof trigList === 'object' ? Object.keys(trigList)[0] : null);
        if (!firstTrigger) {
            rec(testInfo, { module: MOD, step: 'A1_automation_crud', status: 'REVIEW', http: triggers.status,
                note: 'no trigger event resolvable from triggers payload — CRUD aborted' });
            return;
        }

        // A1.2 — create rule
        const createPayload = {
            trigger_event: firstTrigger,
            template_id: createdTemplateIds[0],
            channel: 'email',
            name: taggedName('A1_rule'),
            enabled: false,
            delay_minutes: 0,
        };
        const create = await callTimed(
            request, 'post', `${BASE}/automation/rules`, createPayload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('A1_create') } },
        );
        if ([403, 404, 501].includes(create.status)) {
            recFinding(testInfo, 'P2', MOD,
                `A1.2 automation create not available status=${create.status}`,
                `body=${JSON.stringify(create.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'A1_automation_crud', status: 'REVIEW', http: create.status,
                note: 'create endpoint denied — CRUD aborted (no leftover to clean)' });
            return;
        }
        expect(create.status, `A1.2 create 5xx status=${create.status}`).toBeLessThan(500);
        expect(create.status, `A1.2 create non-2xx status=${create.status}`).toBeGreaterThanOrEqual(200);
        expect(create.status).toBeLessThan(300);
        const ruleId = create.body?.id;
        expect(ruleId, `A1.2 create rule_id missing — body=${JSON.stringify(create.body || {}).slice(0, 200)}`).toBeTruthy();
        expect(create.body?.tenant_id, 'A1.2 rule tenant_id missing').toBeTruthy();
        // Track for afterAll idempotent sweep (orphan-residue insurance:
        // if any step between create and the explicit DELETE below throws,
        // the afterAll loop will reclaim the rule).
        createdAutomationRuleIds.push(ruleId);
        leakScan(testInfo, create.body, 'A1_create_rule');

        // A1.3 — list rules + verify present + tenant scope
        const list = await callTimed(
            request, 'get', `${BASE}/automation/rules`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(list.status, `A1.3 list 5xx status=${list.status}`).toBeLessThan(500);
        if (list.status === 200) {
            const rules = list.body?.rules || [];
            for (const r of rules) {
                expect(r.tenant_id, `A1.3 rule missing tenant_id: ${JSON.stringify(r).slice(0, 100)}`).toBeTruthy();
            }
            const found = rules.find(r => r.id === ruleId);
            expect(found, `A1.3 created rule ${ruleId} not present in own-tenant rules list`).toBeTruthy();
            leakScan(testInfo, list.body, 'A1_list_rules');
        }

        // A1.4 — update rule (toggle enabled)
        const update = await callTimed(
            request, 'put', `${BASE}/automation/rules/${ruleId}`,
            { enabled: true, name: taggedName('A1_rule_updated') },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('A1_update') } },
        );
        expect(update.status, `A1.4 update 5xx status=${update.status}`).toBeLessThan(500);
        if (update.status === 200) {
            expect(update.body?.success, 'A1.4 update success flag missing').toBe(true);
        } else {
            recFinding(testInfo, 'P2', MOD, `A1.4 update non-200 status=${update.status}`, `rule_id=${ruleId}`);
        }

        // A1.5 — delete rule (best-effort cleanup must not raise)
        const del = await callTimed(
            request, 'delete', `${BASE}/automation/rules/${ruleId}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(del.status, `A1.5 delete 5xx status=${del.status}`).toBeLessThan(500);
        if (!(del.status >= 200 && del.status < 300)) {
            recFinding(testInfo, 'P2', MOD, `A1.5 delete non-2xx status=${del.status}`, `rule_id=${ruleId}`);
        }
        // A1.6 — idempotent re-delete → 404
        const del2 = await callTimed(
            request, 'delete', `${BASE}/automation/rules/${ruleId}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(del2.status, `A1.6 re-delete 5xx status=${del2.status}`).toBeLessThan(500);

        rec(testInfo, {
            module: MOD, step: 'A1_automation_crud', status: 'PASS',
            http: create.status,
            note: `trigger=${firstTrigger} rule_id=${ruleId} update=${update.status} delete=${del.status} re-delete=${del2.status}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // S1) SCHEDULER STATUS — read-only probe of pre-arrival scheduler.
    //     POST /scheduler/start and /stop are deliberately NOT exercised
    //     (would mutate global background-task state shared with pilot
    //     instance — destructive per F9 doctrine).
    test('S1) GET /scheduler/status read-only probe', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'S1_scheduler_status', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', `${BASE}/scheduler/status`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `S1 scheduler/status 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status === 200) {
            leakScan(testInfo, r.body, 'S1_scheduler_status');
            // Status payload should have at minimum a recognizable status field.
            const status = r.body?.status ?? r.body?.state ?? null;
            rec(testInfo, {
                module: MOD, step: 'S1_scheduler_status', status: 'PASS',
                http: r.status, note: `scheduler_status=${status ?? '(payload returned)'}`,
            });
        } else if ([403, 404, 501].includes(r.status)) {
            recFinding(testInfo, 'P2', MOD,
                `S1 scheduler/status non-200 status=${r.status}`,
                'endpoint not deployed or RBAC denied — REVIEW (not PASS)');
            rec(testInfo, { module: MOD, step: 'S1_scheduler_status', status: 'REVIEW', http: r.status });
        } else {
            recFinding(testInfo, 'P2', MOD, `S1 scheduler/status unexpected status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'S1_scheduler_status', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // K) Anonymous (headerless) GET → 401/403 — PUBLIC SURFACE LEAK guard.
    //    Raw request.get with NO Authorization header (callTimed sends
    //    "Bearer null" which is invalid-token probe, not strict anonymous).
    test('K) Anonymous headerless GET /templates → 401/403', async ({ request }, testInfo) => {
        let status = 0;
        let bodySnippet = '';
        try {
            const r = await request.get(`${BASE}/templates`, {
                failOnStatusCode: false,
                timeout: 10_000,
                // Intentionally headerless.
            });
            status = r.status();
            try { bodySnippet = (await r.text()).slice(0, 200); } catch { /* ignore */ }
        } catch (e) {
            recFinding(testInfo, 'P2', MOD, 'K_anon network error', String(e?.message || e).slice(0, 200));
        }
        expect(status, `K_anon 5xx status=${status}`).toBeLessThan(500);

        const blocked = status === 401 || status === 403;
        if (!blocked) {
            recFinding(testInfo, 'P1', MOD,
                `Anonymous GET ${BASE}/templates not blocked (status=${status})`,
                `PUBLIC SURFACE LEAK — template data may be reachable without auth. body=${bodySnippet}`);
        }
        expect(blocked, `K_anon: headerless request returned ${status} (expected 401/403)`).toBe(true);
        rec(testInfo, { module: MOD, step: 'K_anon', status: 'PASS', http: status, note: 'headerless probe' });
    });

    // ──────────────────────────────────────────────────────────────
    // INVARIANTS
    test('M) Invariant: external_calls=[] for this module batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(
            testInfo, MOD, 'F9C_MSG_full',
            stressState, request, stressTokens.pilot_token,
        );
        expect(ok, 'external_calls invariant failed').toBe(true);
    });

    test('N) Invariant: pilot drift — booking baseline + pilot template prefix scan', async ({ request, stressTokens }, testInfo) => {
        // Primary gate: pilot bookings count baseline vs after.
        const primaryOk = await assertPilotDriftZero(
            testInfo, MOD, request, stressTokens.pilot_token, pilotBookingBaseline,
        );
        expect(primaryOk, 'pilot bookings drift detected → suite mutated pilot').toBe(true);

        // Supplemental: pilot template prefix scan (best-effort).
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefix_scan', status: 'SKIP', note: 'pilot_token yok' });
            return;
        }
        const r = await callTimed(
            request, 'get', `${BASE}/templates`, null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        expect(r.status, 'pilot templates list 5xx').toBeLessThan(500);
        if (r.status === 200 && Array.isArray(r.body?.templates)) {
            const leaked = r.body.templates.filter(t =>
                (typeof t.name === 'string' && t.name.includes(prefix || '__nope__')) ||
                (typeof t.body_template === 'string' && t.body_template.includes(prefix || '__nope__')) ||
                (typeof t.name === 'string' && t.name.includes(SUB_PREFIX)),
            );
            if (leaked.length > 0) {
                recFinding(testInfo, 'P0', MOD,
                    'PILOT DRIFT (supplemental): stress-prefixed template found in pilot tenant',
                    `count=${leaked.length} sample_id=${leaked[0].id} sample_name=${leaked[0].name}`);
            }
            expect(leaked.length, 'pilot drift (supplemental): stress-prefixed template leaked to pilot').toBe(0);
            rec(testInfo, {
                module: MOD, step: 'N_supplemental_prefix_scan', status: 'PASS',
                http: r.status, note: `pilot templates=${r.body.templates.length} leaked=0`,
            });
        } else {
            rec(testInfo, {
                module: MOD, step: 'N_supplemental_prefix_scan', status: 'REVIEW',
                http: r.status, note: 'pilot templates list non-200 — supplemental unverifiable; primary gate authoritative',
            });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // CLEANUP — idempotent DELETE of created templates.
    test.afterAll(async ({}, testInfo) => {
        const cleanupRec = {
            module: MOD,
            step: 'cleanup',
            tmpl_attempted: createdTemplateIds.length,
            rule_attempted: createdAutomationRuleIds.length,
            note: 'hard DELETE /templates/{id} + /automation/rules/{id} idempotent; tagged with data_prefix for orphan sweep',
        };
        try {
            const { request: globalRequest } = await import('@playwright/test');
            const path = (await import('node:path')).default;
            const fs = await import('node:fs');
            const TOKEN_FILE = process.env.E2E_TOKEN_FILE || path.join(
                process.cwd(), 'e2e-stress', '.auth', 'stress-token.json');
            if (!fs.existsSync(TOKEN_FILE)) {
                cleanupRec.status = 'SKIP';
                cleanupRec.note += ' | token cache yok';
                testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
                return;
            }
            const tok = JSON.parse(fs.readFileSync(TOKEN_FILE, 'utf-8')).stress_token;
            const ctx = await globalRequest.newContext({
                extraHTTPHeaders: { Authorization: `Bearer ${tok}` },
            });
            let deleted = 0;
            let already_gone = 0;
            for (const id of createdTemplateIds) {
                try {
                    const r = await ctx.delete(`${BASE}/templates/${id}`, {
                        timeout: 10_000, failOnStatusCode: false,
                    });
                    const s = r.status();
                    if (s >= 200 && s < 300) deleted += 1;
                    else if (s === 404) already_gone += 1;
                } catch { /* idempotent best-effort */ }
            }
            // Automation rule sweep — A1 may have left orphans if a step
            // between create and the explicit DELETE threw. Idempotent:
            // 404 counts as already_gone, errors swallowed.
            let rule_deleted = 0;
            let rule_already_gone = 0;
            for (const id of createdAutomationRuleIds) {
                try {
                    const r = await ctx.delete(`${BASE}/automation/rules/${id}`, {
                        timeout: 10_000, failOnStatusCode: false,
                    });
                    const s = r.status();
                    if (s >= 200 && s < 300) rule_deleted += 1;
                    else if (s === 404) rule_already_gone += 1;
                } catch { /* idempotent best-effort */ }
            }
            await ctx.dispose();
            cleanupRec.deleted = deleted;
            cleanupRec.already_gone = already_gone;
            cleanupRec.rule_deleted = rule_deleted;
            cleanupRec.rule_already_gone = rule_already_gone;
            cleanupRec.status = 'PASS';
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        } catch (e) {
            cleanupRec.status = 'REVIEW';
            cleanupRec.error = String(e?.message || e).slice(0, 200);
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        }
    });
});

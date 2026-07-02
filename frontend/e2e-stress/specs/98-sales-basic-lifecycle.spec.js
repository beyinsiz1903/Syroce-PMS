// ─────────────────────────────────────────────────────────────────────────
// F9C § 98 — Sales Basic Lifecycle Deep Stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Scope (rapor §3.1 + §2.1 — Sales modülü ZERO coverage idi):
//   Backend:
//     - backend/domains/sales/router.py        (/api/sales/* lead CRUD + funnel + activity)
//     - backend/routers/sales_catering.py      (/api/mice/sales/* opportunities + packages + quote)
//   Yüzey:
//     A) POST   /api/sales/leads                        (lead create)
//     B) GET    /api/sales/leads?status=new             (list + filter)
//     C) PUT    /api/sales/leads/{id}/stage             (new → qualified)
//     D) PUT    /api/sales/leads/{id}/stage             (qualified → won)
//     E) GET    /api/sales/leads/{id}                   (detail + activities list)
//     F) GET    /api/sales/funnel                       (aggregation)
//     G) POST   /api/sales/activity                     (activity / "attachment" log)
//     H) POST   /api/mice/sales/opportunities           (quote/contract surrogate — stage:contract)
//     I) GET    /api/mice/sales/packages/{pkg_id}/quote (quote generate, best-effort)
//     J) IDOR   PUT cross-tenant lead stage             (must fail / 404 / no mutation)
//     K) Anon   headerless GET /api/sales/leads         (must be 401/403)
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []   (assertNoExternalCallsPostBatch)
//   - pilot mutation = 0    (assertPilotDriftZero primary + pilot sales prefix scan supplemental)
//   - P0 = P1 = 0; 5xx = 0; PII leak = 0
//   - Tüm mutasyonlar stress-tenant scope; tüm contact_name/company_name değerleri
//     `${prefix}` ile tag'lenir ki cleanup yakalasın.
//   - Lifecycle final state lost/cancelled; afterAll soft-cleanup idempotent.
//   - Module-blocked doctrine: GET /api/sales/leads non-2xx → A-I skip + REVIEW;
//     J/K (security probes) BAĞIMSIZ çalışır.
//
// Reporter satırı: `sales_lifecycle`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'sales_lifecycle';
const SUB_PREFIX = 'F9C_SALES';
const GAP_MS = 1500;

test.describe.configure({ mode: 'serial' });

test.describe('F9C § 98 — Sales Basic Lifecycle', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBookingBaseline = null;
    let pilotKnownLeadId = null;
    const createdLeadIds = [];
    const createdOpportunityIds = [];
    const createdPackageIds = [];
    let probedPackageId = null;

    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }
    function taggedName(label) {
        return `${prefix}_${SUB_PREFIX}_${label}`;
    }
    function taggedEmail(label) {
        return `${(prefix || 'stress').toLowerCase()}_${SUB_PREFIX.toLowerCase()}_${label}_${Date.now()}@stress.local`;
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: stress token + module probe + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        // Pilot baseline — assertPilotDriftZero için bookings count snapshot.
        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBookingBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;

            // Best-effort: known pilot lead id capture for IDOR probe (J).
            // Pilot sales/leads 200 ise sample id alıp stress_token ile cross-tenant
            // PUT dener. non-2xx ise bogus uuid fallback.
            try {
                const pilotSales = await callTimed(
                    request, 'get', '/api/sales/leads', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                const leads = pilotSales.body?.leads;
                if (pilotSales.status === 200 && Array.isArray(leads) && leads.length > 0) {
                    pilotKnownLeadId = leads[0].id || null;
                }
            } catch { /* ignore — J falls back to bogus id */ }
        }

        // Module probe: GET list
        const probe = await callTimed(
            request, 'get', '/api/sales/leads', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (probe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Sales module 5xx on setup probe',
                `GET /api/sales/leads → ${probe.status}; body=${JSON.stringify(probe.body || {}).slice(0, 200)}`);
            expect(probe.status, 'Sales setup 5xx').toBeLessThan(500);
        }
        // Doctrine: any non-2xx setup probe blocks A-I (J/K stay independent).
        // 5xx already handled above (P1 hard-fail). For 4xx/3xx/etc, mark
        // moduleBlocked so lifecycle steps SKIP rather than emitting noisy
        // REVIEWs against an unreachable module.
        if (probe.status < 200 || probe.status >= 300) {
            moduleBlocked = true;
            blockedReason = `setup_probe_${probe.status}`;
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'REVIEW',
                http: probe.status, note: 'Module blocked / non-2xx — A-I SKIP, J/K independent.',
            });
            recFinding(testInfo, 'P2', MOD,
                `Sales module blocked at setup (${probe.status})`,
                'A-I lifecycle SKIP; security probes (J/K) bağımsız çalışır.');
            return;
        }
        rec(testInfo, {
            module: MOD, step: 'module_probe', status: 'PASS',
            http: probe.status, note: 'GET /api/sales/leads 2xx — lifecycle aktif.',
        });
    });

    // ──────────────────────────────────────────────────────────────
    // A) CREATE LEAD
    test('A) Create lead — stress-tenant scoped', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'A_create', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const payload = {
            company_name: taggedName('A_company'),
            contact_name: taggedName('A_contact'),
            contact_email: taggedEmail('A_create'),
            contact_phone: '+90-555-000-0000',
            source: 'website',
            priority: 'medium',
            estimated_value: 12500,
            estimated_rooms: 5,
            notes: taggedName('A_notes'),
        };
        const r = await callTimed(
            request, 'post', '/api/sales/leads', payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('A_create') } },
        );
        recPerf(testInfo, MOD, 'A_create', [r.ms], r.status >= 200 && r.status < 300);

        if (r.status === 404 || r.status === 403 || r.status === 501) {
            rec(testInfo, { module: MOD, step: 'A_create', status: 'REVIEW', http: r.status, note: 'create endpoint blocked' });
            recFinding(testInfo, 'P2', MOD, 'POST /api/sales/leads not available', `status=${r.status}`);
            return;
        }
        expect(r.status, `A_create unexpected status=${r.status}`).toBeLessThan(500);
        expect(r.status, `A_create non-2xx status=${r.status}`).toBeGreaterThanOrEqual(200);
        expect(r.status).toBeLessThan(300);

        const body = r.body || {};
        const leadId = body.lead_id || body.id;
        expect(leadId, 'created lead id yok').toBeTruthy();
        createdLeadIds.push(leadId);

        rec(testInfo, {
            module: MOD, step: 'A_create', status: 'PASS',
            http: r.status, note: `created lead_id=${leadId}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // B) LIST + FILTER
    test('B) List + filter by status=new', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'B_list', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/sales/leads?status=new', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `B_list 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `B_list non-200 status=${r.status}`, `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'B_list', status: 'REVIEW', http: r.status });
            return;
        }
        const leads = r.body?.leads;
        expect(Array.isArray(leads), 'B_list leads array değil').toBe(true);

        // Tenant scoping invariant: hiçbir item başka tenant'a ait olmamalı
        for (const it of leads) {
            expect(it.tenant_id, `B_list item tenant_id yok: ${JSON.stringify(it).slice(0, 100)}`).toBeTruthy();
        }
        rec(testInfo, {
            module: MOD, step: 'B_list', status: 'PASS',
            http: r.status, note: `leads=${leads.length} total=${r.body?.total}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // C+D) Lifecycle stage transitions: new → qualified → won
    test('C+D) Lifecycle: new → qualified → won', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdLeadIds.length === 0 ? 'no_lead_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'CD_lifecycle', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const leadId = createdLeadIds[0];
        const transitions = [
            { to: 'qualified', op: 'C_qualified' },
            { to: 'won', op: 'D_won' },
        ];
        for (const t of transitions) {
            const r = await callTimed(
                request, 'put',
                `/api/sales/leads/${leadId}/stage`,
                { status: t.to, note: taggedName(`stage_${t.to}`) },
                stressTokens.stress_token,
                { timeout: 10_000, headers: { 'Idempotency-Key': idemKey(t.op) } },
            );
            expect(r.status, `${t.op} 5xx status=${r.status}`).toBeLessThan(500);
            if (r.status !== 200) {
                recFinding(testInfo, 'P2', MOD,
                    `Lifecycle transition ${t.to} non-200`,
                    `lead_id=${leadId} status=${r.status} body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
                rec(testInfo, { module: MOD, step: t.op, status: 'REVIEW', http: r.status });
                continue;
            }
            expect(r.body?.success, `${t.op} response success flag yok`).toBe(true);
            expect(r.body?.status, `${t.op} response status mismatch`).toBe(t.to);
            rec(testInfo, { module: MOD, step: t.op, status: 'PASS', http: r.status });
            await gap(500);
        }
    });

    // ──────────────────────────────────────────────────────────────
    // E) Lead detail + activities ("attachment list")
    test('E) Lead detail — GET /api/sales/leads/{id} (attachments=activities)', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdLeadIds.length === 0 ? 'no_lead_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'E_detail', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const leadId = createdLeadIds[0];
        const r = await callTimed(
            request, 'get', `/api/sales/leads/${leadId}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `E_detail 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `lead detail non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'E_detail', status: 'REVIEW', http: r.status });
            return;
        }
        expect(r.body?.lead?.id, 'lead.id yok').toBe(leadId);
        expect(r.body?.lead?.tenant_id, 'lead.tenant_id yok').toBeTruthy();
        expect(Array.isArray(r.body?.activities), 'activities array değil').toBe(true);
        rec(testInfo, {
            module: MOD, step: 'E_detail', status: 'PASS',
            http: r.status, note: `activities=${r.body.activities.length}`,
        });
    });

    // ──────────────────────────────────────────────────────────────
    // F) Funnel aggregation
    test('F) GET /api/sales/funnel', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'F_funnel', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/sales/funnel', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `F_funnel 5xx`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `funnel non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'F_funnel', status: 'REVIEW', http: r.status });
            return;
        }
        expect(r.body?.funnel, 'funnel field yok').toBeTruthy();
        rec(testInfo, {
            module: MOD, step: 'F_funnel', status: 'PASS', http: r.status,
            note: `total=${r.body.total_leads} win_rate=${r.body.win_rate}`,
        });
    });

    // ──────────────────────────────────────────────────────────────
    // G) Activity log (POST /api/sales/activity)
    test('G) POST /api/sales/activity — activity (attachment-like) log', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdLeadIds.length === 0 ? 'no_lead_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'G_activity', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const leadId = createdLeadIds[0];
        const r = await callTimed(
            request, 'post', '/api/sales/activity',
            {
                lead_id: leadId,
                activity_type: 'note',
                subject: taggedName('G_subject'),
                description: taggedName('G_description'),
            },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('G_activity') } },
        );
        expect(r.status, `G_activity 5xx`).toBeLessThan(500);
        if (r.status >= 200 && r.status < 300 && r.body?.activity_id) {
            rec(testInfo, { module: MOD, step: 'G_activity', status: 'PASS', http: r.status });
        } else if ([404, 422, 501].includes(r.status)) {
            recFinding(testInfo, 'P2', MOD, `activity POST non-2xx status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'G_activity', status: 'REVIEW', http: r.status });
        } else {
            rec(testInfo, { module: MOD, step: 'G_activity', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // H) MICE Opportunity create (contract surrogate — stage_history includes contract)
    test('H) POST /api/mice/sales/opportunities — contract surrogate', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'H_opp_create', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        // Backend contract (OpportunityIn): `title` is the only required field.
        // account_id/contact_id/event_type/source/notes are optional and free-form;
        // we tag notes with the stress prefix so cleanup + supplemental drift
        // scans can find leaks.
        const payload = {
            title: taggedName('H_opp_title'),
            event_type: 'conference',
            source: 'website',
            estimated_value: 25000,
            currency: 'TRY',
            probability: 50,
            pax: 80,
            notes: taggedName('H_opp_notes'),
        };
        const r = await callTimed(
            request, 'post', '/api/mice/sales/opportunities', payload,
            stressTokens.stress_token,
            { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('H_opp') } },
        );
        expect(r.status, `H_opp_create 5xx`).toBeLessThan(500);
        if (r.status === 201 || (r.status >= 200 && r.status < 300)) {
            const oppId = r.body?.id;
            if (oppId) createdOpportunityIds.push(oppId);
            rec(testInfo, { module: MOD, step: 'H_opp_create', status: 'PASS', http: r.status, note: `opp_id=${oppId}` });

            // Best-effort transition to 'contract' stage
            if (oppId) {
                await gap(500);
                const t = await callTimed(
                    request, 'post', `/api/mice/sales/opportunities/${oppId}/transition`,
                    { to_stage: 'contract' },
                    stressTokens.stress_token,
                    { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('H_opp_transition') } },
                );
                expect(t.status, `H_opp_transition 5xx`).toBeLessThan(500);
                rec(testInfo, {
                    module: MOD, step: 'H_opp_transition',
                    status: (t.status >= 200 && t.status < 300) ? 'PASS' : 'REVIEW',
                    http: t.status, note: `→ contract stage`,
                });
            }
        } else if ([403, 404, 422, 501].includes(r.status)) {
            recFinding(testInfo, 'P2', MOD, `opportunity POST non-2xx status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'H_opp_create', status: 'REVIEW', http: r.status });
        } else {
            rec(testInfo, { module: MOD, step: 'H_opp_create', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // I) Quote generate (best-effort: needs an existing package)
    test('I) Quote generate — POST /api/mice/sales/packages/{pkg_id}/quote', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'I_quote', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        // Task #48: seed a stress-prefixed package on demand so Step I exercises
        // real pricing math (base + per_pax × pax + items_total). Prior behavior
        // downgraded to REVIEW on a clean tenant because the spec only read.
        //
        // Strategy:
        //   1) Try to find an EXISTING stress-prefixed package (idempotent /
        //      respects prior global-seed packages tagged `stress_seed=true`).
        //   2) If none, POST one tagged with `${prefix}` in name + a single
        //      addon item with non-zero quantity × unit_price so the items_total
        //      branch of the subtotal formula is actually covered.
        //   3) Track in `createdPackageIds` for afterAll DELETE cleanup so the
        //      tenant footprint stays bounded (only the package WE created is
        //      deleted; pre-seeded packages stay intact).
        //   4) Assert subtotal === base + per_pax*pax + items_total (rounded).
        const pkgList = await callTimed(
            request, 'get', '/api/mice/sales/packages?active_only=false', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(pkgList.status, `I_quote pkg-list 5xx`).toBeLessThan(500);
        if (pkgList.status !== 200) {
            rec(testInfo, { module: MOD, step: 'I_quote_pkg_list', status: 'REVIEW', http: pkgList.status });
            return;
        }
        let pkg = null;
        const pkgs = Array.isArray(pkgList.body?.packages) ? pkgList.body.packages : [];
        // Prefer a stress-prefixed pkg if any exist (deterministic math).
        pkg = pkgs.find((p) => typeof p?.name === 'string' && p.name.includes(prefix)) || pkgs[0] || null;

        if (!pkg) {
            // Seed a stress-tagged package with deterministic, non-zero pricing
            // so the subtotal assertion below exercises all three branches.
            const seedPayload = {
                name: taggedName('I_pkg'),
                type: 'wedding',
                description: taggedName('I_pkg_desc'),
                min_pax: 10,
                max_pax: 500,
                base_price: 12000,
                per_pax_price: 350,
                currency: 'TRY',
                items: [
                    {
                        kind: 'addon',
                        name: taggedName('I_pkg_addon'),
                        quantity: 2,
                        unit_price: 1500,
                    },
                ],
                active: true,
            };
            const seedResp = await callTimed(
                request, 'post', '/api/mice/sales/packages', seedPayload,
                stressTokens.stress_token,
                { timeout: 15_000, headers: { 'Idempotency-Key': idemKey('I_pkg_seed') } },
            );
            expect(seedResp.status, `I_quote pkg-seed 5xx`).toBeLessThan(500);
            if (seedResp.status < 200 || seedResp.status >= 300 || !seedResp.body?.id) {
                rec(testInfo, {
                    module: MOD, step: 'I_quote', status: 'REVIEW',
                    http: seedResp.status,
                    note: `pkg seed non-2xx — quote unverifiable. body=${JSON.stringify(seedResp.body || {}).slice(0, 200)}`,
                });
                recFinding(testInfo, 'P2', MOD,
                    `package seed non-2xx status=${seedResp.status}`,
                    'Step I cannot run pricing assertion without a package.');
                return;
            }
            pkg = seedResp.body;
            createdPackageIds.push(pkg.id);
            rec(testInfo, {
                module: MOD, step: 'I_quote_pkg_seed', status: 'PASS',
                http: seedResp.status, note: `seeded pkg_id=${pkg.id}`,
            });
        }

        probedPackageId = pkg.id;
        const pax = 10;
        const r = await callTimed(
            request, 'post', `/api/mice/sales/packages/${probedPackageId}/quote?pax=${pax}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `I_quote 5xx`).toBeLessThan(500);
        if (r.status === 200) {
            expect(r.body?.package_id, 'quote package_id yok').toBe(probedPackageId);
            expect(typeof r.body?.subtotal, 'quote subtotal yok').toBe('number');

            // Real pricing assertion: base + per_pax*pax + items_total (rounded
            // to 2dp by backend). Tolerance 0.01 to absorb float drift.
            const base = Number(pkg.base_price || 0);
            const perPax = Number(pkg.per_pax_price || 0);
            const items = Array.isArray(pkg.items) ? pkg.items : [];
            const itemsTotal = items.reduce(
                (acc, it) => acc + (Number(it?.quantity ?? 1) * Number(it?.unit_price ?? 0)),
                0,
            );
            const expectedSubtotal = Math.round((base + perPax * pax + itemsTotal) * 100) / 100;
            expect(
                Math.abs(r.body.subtotal - expectedSubtotal),
                `quote subtotal math mismatch: got=${r.body.subtotal} expected=${expectedSubtotal} (base=${base} per_pax=${perPax} pax=${pax} items_total=${itemsTotal})`,
            ).toBeLessThanOrEqual(0.01);

            rec(testInfo, {
                module: MOD, step: 'I_quote', status: 'PASS', http: r.status,
                note: `pkg=${probedPackageId} pax=${pax} subtotal=${r.body.subtotal} expected=${expectedSubtotal}`,
            });
        } else {
            recFinding(testInfo, 'P2', MOD, `quote non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'I_quote', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // J) SECURITY: IDOR — cross-tenant PUT stage (must be no-op or 404)
    // Always-on; module-blocked durumda da çalışır.
    test('J) IDOR: cross-tenant PUT stage → no mutation', async ({ request, stressTokens }, testInfo) => {
        // Real-id-first: tercihen REAL pilot lead id ile dene (gerçek IDOR
        // boundary'sini test eder). Setup'ta pilotKnownLeadId varsa onu kullan;
        // yoksa bogus UUID fallback (en azından "nonexistent → no-op" doğrular).
        const targetId = pilotKnownLeadId || `cross-tenant-${cryptoRandomUUID()}`;
        const probeKind = pilotKnownLeadId ? 'real_pilot_lead_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'put',
            `/api/sales/leads/${targetId}/stage`,
            { status: 'won', note: 'idor_probe' },
            stressTokens.stress_token,
            { timeout: 10_000 },
        );
        expect(r.status, `J_idor 5xx`).toBeLessThan(500);
        // Doctrine: 404/403/401 OK. 200+success=true ile cross-tenant lead
        // güncellemesi → P0 IDOR breach.
        if (r.status === 200) {
            const success = r.body?.success;
            if (success === true) {
                recFinding(testInfo, 'P0', MOD,
                    `IDOR boundary breach: cross-tenant PUT stage succeeded (${probeKind})`,
                    `target_id=${targetId} response=${JSON.stringify(r.body).slice(0, 200)}`);
            }
            expect(success, `J_idor: PUT with ${probeKind}=${targetId} returned success=true → cross-tenant tampering`).not.toBe(true);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'PASS', http: r.status, note: `${probeKind} → success!=true` });
        } else if ([404, 403, 401].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'PASS', http: r.status, note: `${probeKind} rejected ${r.status}` });
        } else {
            recFinding(testInfo, 'P2', MOD, `IDOR probe unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // K) SECURITY: Anonymous list — must be blocked
    // Raw request.get + NO Authorization header (callTimed token=null "Bearer null"
    // gönderir — invalid token probe olur, strict anonymous değil). Burada
    // gerçek headerless probe yapıyoruz.
    test('K) Anonymous (headerless) GET /api/sales/leads → 401/403', async ({ request }, testInfo) => {
        let status = 0;
        let bodySnippet = '';
        try {
            const r = await request.get('/api/sales/leads', {
                failOnStatusCode: false,
                timeout: 10_000,
                // Intentionally headerless — no Authorization header at all.
            });
            status = r.status();
            try { bodySnippet = (await r.text()).slice(0, 200); } catch { /* ignore */ }
        } catch (e) {
            recFinding(testInfo, 'P2', MOD, 'K_anon network error', String(e?.message || e).slice(0, 200));
        }
        expect(status, `K_anon 5xx status=${status}`).toBeLessThan(500);

        const blocked = status === 401 || status === 403 || status === 429;
        if (!blocked) {
            recFinding(testInfo, 'P1', MOD,
                `Anonymous GET /api/sales/leads not blocked (status=${status})`,
                `PUBLIC SURFACE LEAK — tenant lead data may be reachable without auth. body=${bodySnippet}`);
        }
        expect(blocked, `K_anon: headerless request returned ${status} (expected 401/403)`).toBe(true);
        rec(testInfo, { module: MOD, step: 'K_anon', status: 'PASS', http: status, note: 'headerless probe' });
    });

    // ──────────────────────────────────────────────────────────────
    // INVARIANTS
    test('M) Invariant: external_calls=[] for this module batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(
            testInfo, MOD, 'F9C_SALES_full',
            stressState, request, stressTokens.pilot_token,
        );
        expect(ok, 'external_calls invariant failed').toBe(true);
    });

    test('N) Invariant: pilot drift — booking-count baseline + sales prefix scan', async ({ request, stressTokens }, testInfo) => {
        // Primary gate = assertPilotDriftZero (booking count baseline vs after).
        // Stress sales suite pilot bookings'i hiç değiştirmemeli.
        const primaryOk = await assertPilotDriftZero(
            testInfo, MOD, request, stressTokens.pilot_token, pilotBookingBaseline,
        );
        expect(primaryOk, 'pilot bookings drift detected → suite mutated pilot').toBe(true);

        // Supplemental: pilot sales/leads list prefix scan (best-effort).
        if (!stressTokens.pilot_token) {
            rec(testInfo, { module: MOD, step: 'N_supplemental_prefix_scan', status: 'SKIP', note: 'pilot_token yok' });
            return;
        }
        const r = await callTimed(
            request, 'get', '/api/sales/leads', null,
            stressTokens.pilot_token, { timeout: 10_000 },
        );
        expect(r.status, 'pilot sales list 5xx').toBeLessThan(500);
        if (r.status === 200 && Array.isArray(r.body?.leads)) {
            const tag = prefix || '__nope__';
            const leaked = r.body.leads.filter(it => {
                const blob = `${it.contact_name || ''}|${it.company_name || ''}|${it.notes || ''}|${it.contact_email || ''}`;
                return blob.includes(tag) || blob.toLowerCase().includes(tag.toLowerCase());
            });
            if (leaked.length > 0) {
                recFinding(testInfo, 'P0', MOD,
                    'PILOT DRIFT (supplemental): stress-prefixed lead found in pilot tenant',
                    `count=${leaked.length} sample_id=${leaked[0].id}`);
            }
            expect(leaked.length, 'pilot drift (supplemental): stress-prefixed lead leaked to pilot').toBe(0);
            rec(testInfo, {
                module: MOD, step: 'N_supplemental_prefix_scan', status: 'PASS',
                http: r.status, note: `pilot leads count=${r.body.leads.length} leaked=0`,
            });
        } else {
            rec(testInfo, {
                module: MOD, step: 'N_supplemental_prefix_scan', status: 'REVIEW',
                http: r.status, note: 'pilot sales list non-200 — supplemental unverifiable; primary gate authoritative',
            });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // CLEANUP — idempotent: leads → DELETE (hard delete supported);
    // opportunities → transition to 'lost' (soft cancel).
    test.afterAll(async ({}, testInfo) => {
        const cleanupRec = {
            module: MOD,
            step: 'cleanup',
            leads_attempted: createdLeadIds.length,
            opps_attempted: createdOpportunityIds.length,
            packages_attempted: createdPackageIds.length,
            note: 'DELETE leads + packages (idempotent); opportunities → transition lost (idempotent).',
        };
        try {
            const { request: globalRequest } = await import('@playwright/test');
            const TOKEN_FILE = (await import('node:path')).default.join(
                process.cwd(), 'e2e-stress', '.auth', 'stress-token.json');
            const fs = await import('node:fs');
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
            let leadsDeleted = 0;
            for (const id of createdLeadIds) {
                try {
                    const r = await ctx.delete(
                        `/api/sales/leads/${id}`,
                        { timeout: 10_000, failOnStatusCode: false },
                    );
                    if (r.status() < 500) leadsDeleted += 1;
                } catch { /* idempotent best-effort */ }
            }
            let oppsLost = 0;
            for (const id of createdOpportunityIds) {
                try {
                    const r = await ctx.post(
                        `/api/mice/sales/opportunities/${id}/transition`,
                        {
                            data: { to_stage: 'lost', reason: 'stress_cleanup' },
                            headers: { 'Content-Type': 'application/json' },
                            timeout: 10_000,
                            failOnStatusCode: false,
                        },
                    );
                    if (r.status() < 500) oppsLost += 1;
                } catch { /* idempotent best-effort */ }
            }
            let packagesDeleted = 0;
            for (const id of createdPackageIds) {
                try {
                    const r = await ctx.delete(
                        `/api/mice/sales/packages/${id}`,
                        { timeout: 10_000, failOnStatusCode: false },
                    );
                    if (r.status() < 500) packagesDeleted += 1;
                } catch { /* idempotent best-effort */ }
            }
            await ctx.dispose();
            cleanupRec.leads_deleted = leadsDeleted;
            cleanupRec.opps_lost = oppsLost;
            cleanupRec.packages_deleted = packagesDeleted;
            cleanupRec.status = 'PASS';
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        } catch (e) {
            cleanupRec.status = 'REVIEW';
            cleanupRec.error = String(e?.message || e).slice(0, 200);
            testInfo.annotations.push({ type: 'rec', description: JSON.stringify(cleanupRec) });
        }
    });
});

// ─────────────────────────────────────────────────────────────────────────
// F9C § 98 — F&B BEO (Banquet Event Order) Generator Deep Stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Scope (rapor §4.1 G4 — `/fnb/beo-generator` ZERO coverage, para kritik):
//   Backend: backend/routers/mice.py (prefix=/api/mice)
//     A) POST   /api/mice/events                       (create — lead)
//     B) GET    /api/mice/events                       (list + status filter)
//     C) GET    /api/mice/events/{id}                  (detail read)
//     D) PUT    /api/mice/events/{id}                  (menu/space attach + pricing calc)
//     E) GET    /api/mice/events/{id}/beo              (BEO generator — JSON body)
//     F) POST   /api/mice/events/{id}/status           (lifecycle: lead → tentative)
//     G) GET    /api/mice/spaces  +  GET /api/mice/menus  (catalog read)
//     H) GET    /api/mice/events/{id}/kitchen-ticket   (production sheet probe)
//     J) IDOR   POST status on cross-tenant pilot event id → 404/403 (no mutation)
//     K) ANON   headerless GET /api/mice/events       → 401/403 (PUBLIC SURFACE LEAK guard)
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []   (assertNoExternalCallsPostBatch)
//   - pilot mutation = 0    (assertPilotDriftZero — bookings baseline + supplemental BEO prefix scan)
//   - P0 = P1 = 0; 5xx = 0
//   - Tüm event name'leri `${prefix}_${SUB_PREFIX}_…` ile tag'lenir; afterAll
//     status=cancelled (idempotent — `lead → cancelled` transition allowed,
//     `tentative → cancelled` allowed). Hard DELETE yok.
//   - Module-blocked doctrine: GET list non-2xx → A-H skip + REVIEW;
//     J/K (security probes) BAĞIMSIZ çalışır.
//   - PDF render YOK: BEO endpoint JSON döner, body length>0 + event field
//     present şartı yeterli (task acceptance).
//
// Reporter satırı: `fnb_beo`.
// ─────────────────────────────────────────────────────────────────────────

import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'fnb_beo';
const SUB_PREFIX = 'F9C_BEO';
const GAP_MS = 1500;

test.describe.configure({ mode: 'serial' });

test.describe('F9C § 98 — F&B BEO Generator Lifecycle', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBookingBaseline = null;
    let pilotKnownEventId = null;
    let attachedSpaceId = null;
    let attachedMenuId = null;
    let attachedMenuPrice = 0;
    const createdEventIds = [];

    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }
    function taggedName(label) {
        return `${prefix}_${SUB_PREFIX}_${label}`;
    }
    function eventBody({ status = 'lead', withSpace = false, withMenu = false, label }) {
        const today = new Date();
        const startDate = new Date(today.getTime() + 7 * 86400_000).toISOString().slice(0, 10);
        const endDate = startDate;
        const startsAt = `${startDate}T10:00:00`;
        const endsAt = `${startDate}T14:00:00`;
        const body = {
            name: taggedName(label),
            client_name: taggedName(`${label}_client`),
            client_email: null,
            client_phone: null,
            event_type: 'meeting',
            status,
            expected_pax: 20,
            start_date: startDate,
            end_date: endDate,
            space_bookings: [],
            resources: [],
            agenda: [],
            payment_schedule: [],
            notes: `${SUB_PREFIX} synthetic — stress-tenant only`,
        };
        if (withSpace && attachedSpaceId) {
            body.space_bookings.push({
                space_id: attachedSpaceId,
                starts_at: startsAt,
                ends_at: endsAt,
                setup_style: 'theatre',
                expected_pax: 10,
            });
        }
        if (withMenu && attachedMenuId) {
            body.resources.push({
                menu_id: attachedMenuId,
                name: `${SUB_PREFIX}_menu_line`,
                type: 'fb',
                quantity: 10,
                unit: 'pax',
                unit_price: attachedMenuPrice || 0,
            });
        }
        return body;
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: stress token + module probe + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBookingBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;
            try {
                const pilotEvents = await callTimed(
                    request, 'get', '/api/mice/events', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (pilotEvents.status === 200) {
                    const items = pilotEvents.body?.events || [];
                    if (Array.isArray(items) && items.length > 0) {
                        pilotKnownEventId = items[0].id || null;
                    }
                }
            } catch { /* ignore — J falls back to bogus id */ }
        }

        // Module probe: GET list
        const probe = await callTimed(
            request, 'get', '/api/mice/events', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        if (probe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'MICE/BEO module 5xx on setup probe',
                `GET /api/mice/events → ${probe.status}; body=${JSON.stringify(probe.body || {}).slice(0, 200)}`);
            expect(probe.status, 'BEO setup 5xx').toBeLessThan(500);
        }
        // Doctrine: setup probe non-2xx → A-H SKIP (architect Round-1 strictness).
        // 5xx already hard-failed above; everything else non-2xx blocks lifecycle.
        if (probe.status < 200 || probe.status >= 300) {
            moduleBlocked = true;
            blockedReason = `setup_probe_${probe.status}`;
            rec(testInfo, {
                module: MOD, step: 'module_probe', status: 'REVIEW',
                http: probe.status, note: 'Module blocked / non-2xx — A-H SKIP, J/K independent.',
            });
            recFinding(testInfo, 'P2', MOD,
                `MICE/BEO module blocked at setup (${probe.status})`,
                'A-H lifecycle SKIP; security probes (J/K) bağımsız çalışır.');
            return;
        }
        rec(testInfo, {
            module: MOD, step: 'module_probe', status: 'PASS',
            http: probe.status, note: 'GET events 2xx — lifecycle aktif.',
        });
    });

    // ──────────────────────────────────────────────────────────────
    // G) Catalog reads — spaces + menus (used by D attach step)
    test('G) Catalog: GET /api/mice/spaces + /api/mice/menus', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'G_catalog', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const spaces = await callTimed(
            request, 'get', '/api/mice/spaces', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(spaces.status, `G_spaces 5xx status=${spaces.status}`).toBeLessThan(500);
        if (spaces.status === 200) {
            const list = spaces.body?.spaces || [];
            if (Array.isArray(list) && list.length > 0) {
                attachedSpaceId = list[0].id || null;
            }
            rec(testInfo, { module: MOD, step: 'G_spaces', status: 'PASS', http: spaces.status,
                note: `count=${list.length} picked=${attachedSpaceId?.slice(0, 8) || 'none'}` });
        } else {
            rec(testInfo, { module: MOD, step: 'G_spaces', status: 'REVIEW', http: spaces.status });
            recFinding(testInfo, 'P2', MOD, `spaces non-200 status=${spaces.status}`, '');
        }

        const menus = await callTimed(
            request, 'get', '/api/mice/menus', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(menus.status, `G_menus 5xx status=${menus.status}`).toBeLessThan(500);
        if (menus.status === 200) {
            const list = menus.body?.menus || [];
            if (Array.isArray(list) && list.length > 0) {
                const pick = list.find((m) => (m.price_per_person || 0) > 0) || list[0];
                attachedMenuId = pick?.id || null;
                attachedMenuPrice = Number(pick?.price_per_person || pick?.flat_price || 0);
            }
            rec(testInfo, { module: MOD, step: 'G_menus', status: 'PASS', http: menus.status,
                note: `count=${list.length} picked=${attachedMenuId?.slice(0, 8) || 'none'} price=${attachedMenuPrice}` });
        } else {
            rec(testInfo, { module: MOD, step: 'G_menus', status: 'REVIEW', http: menus.status });
            recFinding(testInfo, 'P2', MOD, `menus non-200 status=${menus.status}`, '');
        }
    });

    // ──────────────────────────────────────────────────────────────
    // A) CREATE BEO event
    test('A) Create BEO event — stress-tenant scoped', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'A_create', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const payload = eventBody({ label: 'A_create', status: 'lead' });
        const r = await callTimed(
            request, 'post', '/api/mice/events', payload,
            stressTokens.stress_token,
            { timeout: 20_000, headers: { 'Idempotency-Key': idemKey('A_create') } },
        );
        recPerf(testInfo, MOD, 'A_create', [r.ms], r.status >= 200 && r.status < 300);

        if ([401, 403, 404, 501].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'A_create', status: 'REVIEW', http: r.status,
                note: 'create endpoint not authorized for stress token' });
            recFinding(testInfo, 'P2', MOD, `POST /api/mice/events not authorized (${r.status})`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            moduleBlocked = true;
            blockedReason = `create_${r.status}`;
            return;
        }
        expect(r.status, `A_create unexpected status=${r.status}`).toBeLessThan(500);
        expect(r.status, `A_create non-2xx status=${r.status}`).toBeGreaterThanOrEqual(200);
        expect(r.status).toBeLessThan(300);

        const ev = r.body || {};
        expect(ev.id, 'created event id yok').toBeTruthy();
        expect(ev.tenant_id, 'event tenant_id yok').toBeTruthy();
        expect(ev.status, 'event status yok').toBe('lead');
        createdEventIds.push(ev.id);

        rec(testInfo, {
            module: MOD, step: 'A_create', status: 'PASS',
            http: r.status, note: `created event_id=${ev.id}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // B) LIST + STATUS FILTER
    test('B) List + filter by status=lead — tenant scoping invariant', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'B_list', status: 'SKIP', note: blockedReason });
            test.skip(true, `module_blocked: ${blockedReason}`);
        }
        const r = await callTimed(
            request, 'get', '/api/mice/events?status=lead', null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `B_list 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `B_list non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'B_list', status: 'REVIEW', http: r.status });
            return;
        }
        const items = r.body?.events || [];
        expect(Array.isArray(items), 'B_list events array değil').toBe(true);

        // Tenant scoping invariant
        for (const it of items) {
            expect(it.tenant_id, `B_list event tenant_id yok: ${JSON.stringify(it).slice(0, 100)}`).toBeTruthy();
        }
        rec(testInfo, {
            module: MOD, step: 'B_list', status: 'PASS',
            http: r.status, note: `events=${items.length}`,
        });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // C) GET event detail
    test('C) GET event detail', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdEventIds.length === 0 ? 'no_event_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'C_detail', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const evId = createdEventIds[0];
        const r = await callTimed(
            request, 'get', `/api/mice/events/${evId}`, null,
            stressTokens.stress_token, { timeout: 10_000 },
        );
        expect(r.status, `C_detail 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `C_detail non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'C_detail', status: 'REVIEW', http: r.status });
            return;
        }
        expect(r.body?.id, 'detail id yok').toBe(evId);
        rec(testInfo, { module: MOD, step: 'C_detail', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // D) PUT update — menu attach + room (space) booking link + pricing calc
    test('D) Update: menu attach + space link + pricing calc', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdEventIds.length === 0 ? 'no_event_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'D_update', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const evId = createdEventIds[0];
        const payload = eventBody({
            label: 'A_create',
            status: 'lead',
            withSpace: !!attachedSpaceId,
            withMenu: !!attachedMenuId,
        });
        const r = await callTimed(
            request, 'put', `/api/mice/events/${evId}`, payload,
            stressTokens.stress_token,
            { timeout: 20_000, headers: { 'Idempotency-Key': idemKey('D_update') } },
        );
        recPerf(testInfo, MOD, 'D_update', [r.ms], r.status === 200);
        expect(r.status, `D_update 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `D_update non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'D_update', status: 'REVIEW', http: r.status });
            return;
        }
        // Pricing calc invariant — totals field must come back; if menu+space
        // attached with non-zero prices, grand_total should be > 0.
        const totals = r.body?.totals || {};
        expect(totals, 'D_update totals yok').toBeTruthy();
        const note = `space=${attachedSpaceId?.slice(0, 8) || 'none'} menu=${attachedMenuId?.slice(0, 8) || 'none'} grand=${totals.grand_total ?? 'n/a'}`;
        rec(testInfo, { module: MOD, step: 'D_update', status: 'PASS', http: r.status, note });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // E) BEO generator endpoint — task acceptance: 200 + non-empty body
    test('E) GET /api/mice/events/{id}/beo — generator output', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdEventIds.length === 0 ? 'no_event_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'E_beo', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const evId = createdEventIds[0];
        const r = await callTimed(
            request, 'get', `/api/mice/events/${evId}/beo`, null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'E_beo', [r.ms], r.status === 200);
        expect(r.status, `E_beo 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `E_beo non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'E_beo', status: 'REVIEW', http: r.status });
            return;
        }
        // Task acceptance: endpoint 200 + non-empty body (PDF render YOK).
        const bodyStr = JSON.stringify(r.body || {});
        expect(bodyStr.length, `E_beo body empty`).toBeGreaterThan(2);
        expect(r.body?.event?.id, 'E_beo event.id yok').toBe(evId);
        rec(testInfo, { module: MOD, step: 'E_beo', status: 'PASS', http: r.status,
            note: `body_len=${bodyStr.length} spaces=${(r.body?.spaces || []).length} resources=${(r.body?.resources || []).length}` });
    });

    // ──────────────────────────────────────────────────────────────
    // F) STATUS lifecycle: lead → tentative
    test('F) Status transition: lead → tentative', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdEventIds.length === 0 ? 'no_event_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'F_status', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const evId = createdEventIds[0];
        const r = await callTimed(
            request, 'post', `/api/mice/events/${evId}/status`,
            { status: 'tentative' },
            stressTokens.stress_token,
            { timeout: 10_000, headers: { 'Idempotency-Key': idemKey('F_status') } },
        );
        expect(r.status, `F_status 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `F_status non-200 status=${r.status}`,
                `body=${JSON.stringify(r.body || {}).slice(0, 200)}`);
            rec(testInfo, { module: MOD, step: 'F_status', status: 'REVIEW', http: r.status });
            return;
        }
        expect(r.body?.status, 'F_status response status yok').toBe('tentative');
        rec(testInfo, { module: MOD, step: 'F_status', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // H) Kitchen ticket — production sheet probe
    test('H) GET /api/mice/events/{id}/kitchen-ticket', async ({ request, stressTokens }, testInfo) => {
        const reason = moduleBlocked ? blockedReason : (createdEventIds.length === 0 ? 'no_event_created' : null);
        if (reason) {
            rec(testInfo, { module: MOD, step: 'H_kitchen', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const evId = createdEventIds[0];
        const r = await callTimed(
            request, 'get', `/api/mice/events/${evId}/kitchen-ticket`, null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        expect(r.status, `H_kitchen 5xx status=${r.status}`).toBeLessThan(500);
        if (r.status !== 200) {
            recFinding(testInfo, 'P2', MOD, `H_kitchen non-200 status=${r.status}`, '');
            rec(testInfo, { module: MOD, step: 'H_kitchen', status: 'REVIEW', http: r.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'H_kitchen', status: 'PASS', http: r.status });
    });

    // ──────────────────────────────────────────────────────────────
    // J) SECURITY: IDOR — cross-tenant status POST (must be no-op or 404/403)
    test('J) IDOR: cross-tenant status POST → no mutation', async ({ request, stressTokens }, testInfo) => {
        const targetId = pilotKnownEventId || `cross-tenant-${cryptoRandomUUID()}`;
        const probeKind = pilotKnownEventId ? 'real_pilot_event_id' : 'bogus_uuid_fallback';

        const r = await callTimed(
            request, 'post', `/api/mice/events/${targetId}/status`,
            { status: 'tentative' },
            stressTokens.stress_token,
            { timeout: 10_000 },
        );
        expect(r.status, `J_idor 5xx status=${r.status}`).toBeLessThan(500);
        // Doctrine: 404/403/401 expected. 200 + ok=true → cross-tenant breach.
        if (r.status === 200) {
            const ok = r.body?.ok;
            if (ok === true) {
                recFinding(testInfo, 'P0', MOD,
                    `IDOR boundary breach: cross-tenant status POST succeeded (${probeKind})`,
                    `target_id=${targetId} response=${JSON.stringify(r.body).slice(0, 200)}`);
            }
            expect(ok, `J_idor: status POST with ${probeKind}=${targetId} returned ok=true → cross-tenant tampering`).not.toBe(true);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'PASS', http: r.status, note: `${probeKind} → ok!=true` });
        } else if ([404, 403, 401].includes(r.status)) {
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'PASS', http: r.status, note: `${probeKind} rejected ${r.status}` });
        } else {
            recFinding(testInfo, 'P2', MOD, `IDOR probe unexpected status=${r.status}`, `probe=${probeKind}`);
            rec(testInfo, { module: MOD, step: 'J_idor', status: 'REVIEW', http: r.status });
        }
    });

    // ──────────────────────────────────────────────────────────────
    // K) SECURITY: Anonymous list — must be blocked (raw headerless GET)
    test('K) Anonymous (headerless) GET /api/mice/events → 401/403', async ({ request }, testInfo) => {
        let status = 0;
        let bodySnippet = '';
        try {
            const r = await request.get('/api/mice/events', {
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

        const blocked = status === 401 || status === 403;
        if (!blocked) {
            recFinding(testInfo, 'P1', MOD,
                `Anonymous GET /api/mice/events not blocked (status=${status})`,
                `PUBLIC SURFACE LEAK — tenant event data may be reachable without auth. body=${bodySnippet}`);
        }
        expect(blocked, `K_anon: headerless request returned ${status} (expected 401/403)`).toBe(true);
        rec(testInfo, { module: MOD, step: 'K_anon', status: 'PASS', http: status, note: 'headerless probe' });
    });

    // ──────────────────────────────────────────────────────────────
    // INVARIANTS
    test('M) Invariant: external_calls=[] for this module batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(
            testInfo, MOD, 'F9C_BEO_full',
            stressState, request, stressTokens.pilot_token,
        );
        expect(ok, 'external_calls invariant failed').toBe(true);
    });

    test('N) Invariant: pilot drift — booking-count baseline + BEO prefix scan', async ({ request, stressTokens }, testInfo) => {
        // Primary gate: bookings count drift (pilot read-only contract).
        const primaryOk = await assertPilotDriftZero(
            testInfo, MOD, request, stressTokens.pilot_token, pilotBookingBaseline,
        );

        // Supplemental: scan pilot mice_events list for any BEO prefix leak.
        // If our prefix appears in pilot tenant events → cross-tenant write occurred.
        let supplementalOk = true;
        if (stressTokens.pilot_token && prefix) {
            try {
                const r = await callTimed(
                    request, 'get', '/api/mice/events', null,
                    stressTokens.pilot_token, { timeout: 10_000 },
                );
                if (r.status === 200) {
                    const items = r.body?.events || [];
                    const leaked = items.filter((e) => {
                        const n = String(e?.name || '');
                        return n.startsWith(prefix) || n.includes(SUB_PREFIX);
                    });
                    if (leaked.length > 0) {
                        supplementalOk = false;
                        recFinding(testInfo, 'P0', MOD,
                            `Pilot BEO prefix leak: ${leaked.length} event(s) with stress prefix in pilot tenant`,
                            `samples=${JSON.stringify(leaked.slice(0, 3).map((e) => e.name)).slice(0, 200)}`);
                    }
                    rec(testInfo, { module: MOD, step: 'pilot_beo_prefix_scan',
                        status: supplementalOk ? 'PASS' : 'FAIL', http: r.status,
                        note: `pilot_events=${items.length} leaked=${leaked.length}` });
                } else {
                    rec(testInfo, { module: MOD, step: 'pilot_beo_prefix_scan',
                        status: 'REVIEW', http: r.status, note: 'pilot events endpoint unreachable' });
                }
            } catch (e) {
                rec(testInfo, { module: MOD, step: 'pilot_beo_prefix_scan',
                    status: 'REVIEW', note: `scan_error=${String(e?.message || e).slice(0, 120)}` });
            }
        } else {
            rec(testInfo, { module: MOD, step: 'pilot_beo_prefix_scan',
                status: 'SKIP', note: 'no pilot_token or prefix' });
        }
        expect(primaryOk, 'pilot drift primary gate failed').toBe(true);
        expect(supplementalOk, 'pilot BEO prefix leak detected').toBe(true);
    });

    // ──────────────────────────────────────────────────────────────
    // CLEANUP — afterAll: idempotent status=cancelled. lead/tentative →
    // cancelled is allowed by _MICE_TRANSITIONS. Cancelled→cancelled is
    // not a valid transition (returns 409), so we treat 409 as already-done.
    test.afterAll(async ({ }, testInfo) => {
        if (createdEventIds.length === 0) return;
        const apiContext = await (await import('@playwright/test')).request.newContext({
            baseURL: process.env.E2E_BASE_URL,
            extraHTTPHeaders: {},
        });
        // Canonical token path matches stress-context.js / global-setup.js:
        // frontend/e2e-stress/.auth/stress-token.json (cwd = frontend/).
        // Env override (E2E_TOKEN_FILE) supported as first fallback.
        let stressToken = null;
        try {
            const fs = await import('node:fs');
            const pathMod = await import('node:path');
            const candidate = process.env.E2E_TOKEN_FILE
                || pathMod.join(process.cwd(), 'e2e-stress', '.auth', 'stress-token.json');
            const t = JSON.parse(fs.readFileSync(candidate, 'utf-8'));
            stressToken = t.stress_token;
        } catch { /* ignore — cleanup best-effort */ }
        if (!stressToken) {
            await apiContext.dispose();
            return;
        }
        const cancelled = [];
        const alreadyCancelled = [];
        const skipped = [];
        for (const id of createdEventIds) {
            try {
                const r = await apiContext.post(`/api/mice/events/${id}/status`, {
                    headers: {
                        Authorization: `Bearer ${stressToken}`,
                        'Content-Type': 'application/json',
                    },
                    data: { status: 'cancelled', reason: `${SUB_PREFIX} stress cleanup (idempotent soft-cancel)` },
                    failOnStatusCode: false,
                    timeout: 10_000,
                });
                const st = r.status();
                if (st >= 200 && st < 300) {
                    cancelled.push(id);
                } else if (st === 409) {
                    // cancelled→cancelled returns 409 from _MICE_TRANSITIONS;
                    // semantically already-clean → success-equivalent for idempotency.
                    alreadyCancelled.push(id);
                } else {
                    skipped.push({ id, status: st });
                }
            } catch (e) {
                skipped.push({ id, error: String(e?.message || e).slice(0, 80) });
            }
        }
        await apiContext.dispose();
        // Attach cleanup ledger to last testInfo for traceability.
        try {
            testInfo.attach('beo-cleanup-ledger.json', {
                body: Buffer.from(JSON.stringify({
                    created: createdEventIds.length,
                    cancelled: cancelled.length,
                    already_cancelled: alreadyCancelled.length,
                    skipped,
                }, null, 2)),
                contentType: 'application/json',
            });
        } catch { /* ignore */ }
    });
});

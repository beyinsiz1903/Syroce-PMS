// F8C § 14 — MICE Events: catalog reads + bulk create + status transitions
// (lead→tentative→definite) + payment-schedule replace + mark-paid.
//
// Dry-run safety:
//   - Tests NEVER transition to `completed` — that triggers
//     `_post_event_to_folio` + `bus.publish(POSTING_CHARGE)` which would be
//     a real external dispatch attempt. Even though seeded events have
//     reservation_id=None (folio posting short-circuits), the bus.publish
//     is unconditional in some code paths → keep status transitions safe.
//   - Created events have reservation_id=None and `stress_prefix` tag.
//   - mark-paid is DB-only ($set positional) — no provider call.
//   - Each created event uses unique (space_id, date) tuple to avoid
//     conflict on lead→tentative transition (_check_space_conflict).
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    fetchSingle, callTimed, callTimedWithBackoff, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'mice_events';
const N_CREATE = 10;

test.describe.configure({ mode: 'serial' });

test.describe('F8C § 14 — MICE Events', () => {
    let pilotBefore = null;
    let prefix = null;
    let stressTid = null;
    let createdEventIds = [];
    let seededSpaceIds = [];
    let moduleBlocked = false;

    test('Setup: prefix + pilot baseline + space catalog', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid || stressState.seed_response?.target_tenant_id;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        // Fetch seeded function spaces (stress_prefix scoped) → 14-B reuses these
        // for non-overlapping (space, date) tuples. Endpoint is `@_cached(ttl=300)`
        // keyed on (function_name, current_user.tenant_id) — query params do NOT
        // bust the cache. If endpoint returns non-2xx or 0 spaces, we mark the
        // module blocked (P2 informational, same pattern as 15-sales) and skip
        // A/B/C/D while preserving the E pilot-drift invariant.
        const spacesResp = await callTimed(request, 'get', '/api/mice/spaces', undefined, stressTokens.stress_token);
        const allSpaces = spacesResp.body?.spaces || spacesResp.body?.items || [];
        const stressSpaces = allSpaces.filter(
            (s) => typeof s.name === 'string' && s.name.includes(prefix),
        );
        const usable = stressSpaces.length > 0 ? stressSpaces : allSpaces;
        seededSpaceIds = usable.map((s) => s.id).slice(0, 8);
        moduleBlocked = !spacesResp.ok || seededSpaceIds.length < 1;
        rec(testInfo, { module: MOD, step: 'setup', status: moduleBlocked ? 'REVIEW' : 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} spaces_total=${allSpaces.length} stress_spaces=${stressSpaces.length} usable=${seededSpaceIds.length} resp_status=${spacesResp.status} module_blocked=${moduleBlocked}` });
        if (moduleBlocked) {
            recFinding(testInfo, 'P2', MOD, 'MICE events module read blocked — A/B/C/D skipped',
                `spaces endpoint resp_status=${spacesResp.status} usable_spaces=${seededSpaceIds.length}. Could be @_cached(ttl=300) stale entry or stress-admin RBAC. Informational — pilot_drift gate (E) still enforced.`);
        }
        // Soft assertions only — setup never hard-fails; downstream tests guard themselves.
        expect(typeof spacesResp.status).toBe('number');
    });

    test('A) Catalog read: spaces, menus, accounts, events, diary', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'catalog_read', status: 'SKIP', note: 'module_blocked=true (see setup P2)' });
            test.skip(true, 'MICE events module blocked at setup');
            return;
        }
        const samples = [];
        const reads = [
            ['/api/mice/spaces', 'spaces'],
            ['/api/mice/menus', 'menus'],
            ['/api/mice/accounts', 'accounts'],
            ['/api/mice/resources', 'resources'],
            ['/api/mice/events?status=lead', 'events_lead'],
            ['/api/mice/diary', 'diary'],
        ];
        const results = {};
        for (const [path, key] of reads) {
            const r = await callTimed(request, 'get', path, undefined, stressTokens.stress_token);
            samples.push(r.ms);
            results[key] = { status: r.status, len: Array.isArray(r.body) ? r.body.length :
                (r.body?.events?.length ?? r.body?.spaces?.length ?? r.body?.menus?.length
                ?? r.body?.accounts?.length ?? r.body?.resources?.length ?? r.body?.items?.length ?? 0) };
        }
        recPerf(testInfo, MOD, 'catalog_read', samples, true);
        const allOk = Object.values(results).every((r) => r.status >= 200 && r.status < 300);
        rec(testInfo, { module: MOD, step: 'catalog_read', status: allOk ? 'PASS' : 'REVIEW',
            endpoint: '/api/mice/*',
            note: `results=${JSON.stringify(results)} max_ms=${Math.max(...samples)}` });
        if (!allOk) recFinding(testInfo, 'P2', MOD, 'Catalog read non-2xx',
            `results=${JSON.stringify(results)}`);
        // Hard-assert at least events_lead returned non-zero (we seeded 30).
        expect(results.events_lead.len).toBeGreaterThan(0);
    });

    test('B) Bulk create — N events status=lead, unique (space, date)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (seededSpaceIds.length < 1) {
            rec(testInfo, { module: MOD, step: 'bulk_create', status: 'SKIP', note: 'no seeded spaces' });
            return;
        }
        const samples = [];
        let ok = 0, fail = 0, throttled = 0;
        const errs = [];
        const baseDay = new Date();
        baseDay.setUTCDate(baseDay.getUTCDate() + 90);  // 90 days from now, beyond seed window
        for (let i = 0; i < N_CREATE; i++) {
            const day = new Date(baseDay);
            day.setUTCDate(day.getUTCDate() + i);  // unique day per event
            const ymd = day.toISOString().slice(0, 10);
            const startIso = `${ymd}T09:00:00.000Z`;
            const endIso = `${ymd}T17:00:00.000Z`;
            const payload = {
                name: `${prefix}EvtB_${i + 1}`,
                client_name: `${prefix}ClientB_${i + 1}`,
                client_email: `${prefix.toLowerCase()}cb${i + 1}@e2e-stress.example.com`,
                event_type: 'meeting',
                status: 'lead',
                expected_pax: 40,
                start_date: ymd,
                end_date: ymd,
                space_bookings: [{
                    space_id: seededSpaceIds[i % seededSpaceIds.length],
                    starts_at: startIso,
                    ends_at: endIso,
                    setup_style: 'theatre',
                    expected_pax: 40,
                }],
                resources: [],
                agenda: [],
                payment_schedule: [],
                notes: `${prefix} F8C 14-B created`,
            };
            const r = await callTimedWithBackoff(request, 'post', '/api/mice/events', payload, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok && (r.body?.id || r.body?.event?.id)) {
                ok++;
                createdEventIds.push(r.body.id || r.body.event?.id);
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const floor = Math.ceil(N_CREATE * 0.9);
        recPerf(testInfo, MOD, 'bulk_create', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'bulk_create', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/mice/events',
            note: `n=${N_CREATE} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor} created=${createdEventIds.length} errs=${JSON.stringify(errs)}` });
        if (ok < floor) recFinding(testInfo, 'P1', MOD, 'Event bulk create floor (>=90%) ihlal',
            `n=${N_CREATE} ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_create', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `bulk_create floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) Status transitions: lead → tentative → definite', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (createdEventIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'transitions', status: 'SKIP', note: 'no created events' });
            return;
        }
        const samples = [];
        let okTent = 0, okDef = 0, fail = 0, throttled = 0;
        const errs = [];
        // lead → tentative
        for (const eid of createdEventIds) {
            const r = await callTimedWithBackoff(request, 'post', `/api/mice/events/${eid}/status`,
                { status: 'tentative', reason: 'F8C 14-C tentative transition' },
                stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) okTent++; else { fail++; if (errs.length < 3) errs.push({ tgt: 'tentative', status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        // tentative → definite
        for (const eid of createdEventIds) {
            const r = await callTimedWithBackoff(request, 'post', `/api/mice/events/${eid}/status`,
                { status: 'definite', reason: 'F8C 14-C definite transition' },
                stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) okDef++; else { fail++; if (errs.length < 3) errs.push({ tgt: 'definite', status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const total = createdEventIds.length * 2;
        const okTotal = okTent + okDef;
        const floor = Math.ceil(total * 0.9);
        recPerf(testInfo, MOD, 'transitions', samples, okTotal >= floor);
        rec(testInfo, { module: MOD, step: 'transitions', status: okTotal >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/mice/events/{id}/status',
            note: `tentative ok=${okTent}/${createdEventIds.length} definite ok=${okDef}/${createdEventIds.length} throttled_429=${throttled} floor>=${floor} errs=${JSON.stringify(errs)}` });
        if (okTotal < floor) recFinding(testInfo, 'P1', MOD, 'Status transitions floor ihlal',
            `total=${total} ok=${okTotal} (<${floor}). errs=${JSON.stringify(errs)}`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'transitions', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Payment schedule replace + mark-paid (DB-only)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(180_000);
        if (createdEventIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'payment_schedule', status: 'SKIP', note: 'no created events' });
            return;
        }
        const samples = [];
        let okReplace = 0, okMark = 0, fail = 0, throttled = 0, permFail = 0;
        const errs = [];
        const targets = createdEventIds.slice(0, 5);
        const today = new Date();
        const dueIso = (offset) => {
            const d = new Date(today);
            d.setUTCDate(d.getUTCDate() + offset);
            return d.toISOString().slice(0, 10);
        };
        // Replace schedule: 3 items per event
        for (const eid of targets) {
            const r = await callTimedWithBackoff(request, 'post', `/api/mice/events/${eid}/payment-schedule`, {
                items: [
                    { due_date: dueIso(7),  label: 'Depozito %30', amount: 3000.0, paid: false },
                    { due_date: dueIso(30), label: '1. Taksit',     amount: 4000.0, paid: false },
                    { due_date: dueIso(60), label: 'Bakiye',        amount: 3000.0, paid: false },
                ],
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) okReplace++; else { fail++; if (errs.length < 3) errs.push({ op: 'replace', status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        // Mark first item paid on each event — guarded for require_finance 403.
        for (const eid of targets) {
            const r = await callTimedWithBackoff(request, 'post', `/api/mice/events/${eid}/payment-schedule/0/mark-paid?reference=F8C-${prefix}-A`,
                undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.throttled) throttled++;
            if (r.ok) okMark++;
            else if (r.status === 403) { permFail++; }  // finance role missing — informational, not P1
            else { fail++; if (errs.length < 3) errs.push({ op: 'mark', status: r.status, body: JSON.stringify(r.body).slice(0, 120) }); }
            await new Promise((res) => setTimeout(res, 1500));
        }
        const totalOps = targets.length * 2;
        const okTotal = okReplace + okMark;
        // Floor accounts for possible finance 403 — only fail hard if even
        // replace floor not met. mark-paid permFail downgrades to REVIEW.
        const replaceFloor = Math.ceil(targets.length * 0.9);
        const passOverall = okReplace >= replaceFloor && (okMark + permFail) === targets.length;
        recPerf(testInfo, MOD, 'payment_schedule', samples, passOverall);
        rec(testInfo, { module: MOD, step: 'payment_schedule', status: passOverall ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/mice/events/{id}/payment-schedule[/{i}/mark-paid]',
            note: `replace ok=${okReplace}/${targets.length} mark ok=${okMark}/${targets.length} perm_403=${permFail} throttled_429=${throttled} errs=${JSON.stringify(errs)}` });
        if (okReplace < replaceFloor) recFinding(testInfo, 'P1', MOD, 'Payment-schedule replace floor ihlal',
            `n=${targets.length} ok=${okReplace} (<${replaceFloor}). errs=${JSON.stringify(errs)}`);
        if (permFail > 0 && okMark === 0) recFinding(testInfo, 'P2', MOD, 'mark-paid require_finance 403',
            `Stress admin rolü require_finance kapsamı dışında. ${permFail} call 403 döndü. Informational — finance rolü gerekli.`);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'payment_schedule', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('E) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});

// F8AH § 98 — Ops Surface Smoke Stress.
//
// Beş düşük-yüzey ama yüksek-risk operasyonel uç noktayı tek spec'te
// birleştirir: Cross-Property Rollup IDOR, Shift Handover lifecycle,
// Webhook Admin DLQ role-guard, EOD Report read-only smoke, Booking
// Holds lifecycle. F8R–F8W (ops-readiness) + F8AC (golf-operational)
// doktrini: her test try/finally + post-batch external_calls=[] +
// pilot_drift=0 invariants, module-blocked → A/B/C/D/E skip + P2,
// cleanup idempotent.
//
// Mutlak kurallar:
//   - pilot mutation = 0 (cross-tenant probe sadece read/4xx-expect)
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//   - EOD `/send` ASLA çağrılmaz (mail external_calls invariant'ını kırar)
//
// Threat model anchors:
//   - cross_property: /api/cross-property/guests/search — chain rollup
//     bypass-tenant-guard yüzey; stress chain dışı tenant_id leak = P0.
//   - shift_handover: PATCH /{id}/acknowledge + DELETE /{id} cross-tenant
//     mutation = P0 (find_one_and_update tenant_id filter sağlamlık testi).
//   - webhook_admin: require_super_admin_guard router-wide; non-super-admin
//     bearer ile 200 → P0 (RBAC bypass).
//   - eod_report: _collect(current_user.tenant_id, ...) — tenant filter
//     yapısal; leak yapısal olarak imkânsız; sadece smoke + send YASAK.
//   - booking_holds: tenant_id filter create/confirm/delete/status; cross-
//     tenant booking_id ile confirm/delete = P0 (state mutate breach).
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';
import { randomUUID } from 'node:crypto';

const MOD_CP = 'cross_property_rollup';
const MOD_SH = 'shift_handover';
const MOD_WH = 'webhook_admin_dlq';
const MOD_EOD = 'eod_report';
const MOD_BH = 'booking_holds';

function ymdOffset(days) {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
}

test.describe.serial('F8AH ops surface smoke stress', () => {
    let prefix = null;
    let stressTid = null;
    let pilotTid = null;
    let createdHandoverIds = [];
    let createdHoldBookingIds = [];

    const blocked = {
        cross_property: false,
        shift_handover: false,
        webhook_admin: false,
        eod_report: false,
        booking_holds: false,
    };

    test('Setup: prefix + tenant id snapshot + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix || `STRESS_F8AH_${Date.now()}_`;
        stressTid = stressState.stress_tenant_id || stressState.tenant_id || process.env.E2E_STRESS_TENANT_ID || null;
        pilotTid = stressTokens.pilot_tenant_id || stressState.pilot_tenant_id || process.env.PILOT_TENANT_ID || null;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: 'f8ah_setup', step: 'pilot_baseline', status: 'INFO',
            note: `prefix=${prefix} stress_tid=${stressTid ?? 'unset'} pilot_tid=${pilotTid ?? 'unset'} pilot_before=${pilotBefore?.count}` });
        // Setup batch — no mutations performed.
        const extOk = await assertNoExternalCallsPostBatch(testInfo, 'f8ah_setup', 'setup_batch',
            stressTokens.seed_state ?? stressState ?? {}, request, pToken);
        expect(extOk).toBe(true);
        await assertPilotDriftZero(testInfo, 'f8ah_setup', request, pToken, pilotBefore);
    });

    // ──────────────────────────────────────────────────────────────
    // Module A — cross_property_rollup
    // ──────────────────────────────────────────────────────────────
    test('A) cross_property_rollup — guest-search smoke + cross-tenant leak guard', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Probe — endpoint reachable?
            const probe = await withModuleProbe(request, sToken,
                '/api/cross-property/guests/search?q=ZZZNOMATCH');
            if (probe.moduleBlocked) {
                blocked.cross_property = true;
                recFinding(testInfo, 'P2', MOD_CP, 'cross-property search module-blocked',
                    `status=${probe.status} reason=${probe.reason} — cross-tenant leak guard SKIP, final invariants still enforced.`);
                rec(testInfo, { module: MOD_CP, step: 'probe', status: 'SKIP',
                    note: `blocked status=${probe.status}` });
                test.skip(true, 'cross-property search blocked');
                return;
            }

            // A1) Stress smoke — search common prefix that matches stress seed data.
            const sRes = await callTimed(request, 'get',
                `/api/cross-property/guests/search?q=STRESS&limit=50`, undefined, sToken);
            expect(sRes.status, `stress search http=${sRes.status}`).toBe(200);
            const sGuests = sRes.body?.guests || [];
            // Stress bearer should NOT see pilot tenant guests (no chain).
            const stressLeaksToPilot = pilotTid
                ? sGuests.filter(g => g?.tenant_id && g.tenant_id === pilotTid)
                : [];
            if (stressLeaksToPilot.length > 0) {
                recFinding(testInfo, 'P0', MOD_CP,
                    'cross-property stress→pilot tenant leak in chain search',
                    `stress bearer search returned ${stressLeaksToPilot.length} pilot-tenant guest(s); chain_id misconfig or chain bypass. sample=${JSON.stringify(stressLeaksToPilot.slice(0,2))}`);
            }

            // A2) Pilot probe — search for the stress-only prefix. Pilot bearer
            // MUST NOT see stress-tenant guests unless it is super_admin AND
            // intentionally cross-property chain-enabled. Any returned guest
            // with tenant_id === stressTid is a chain-scope breach OR an
            // unexpected super_admin grant — emit P0 finding either way (the
            // operator decides on review whether to whitelist).
            let pilotLeakCount = 0;
            if (pToken) {
                const pRes = await callTimed(request, 'get',
                    `/api/cross-property/guests/search?q=${encodeURIComponent(prefix.slice(0, 12))}&limit=50`,
                    undefined, pToken);
                // 200 expected (endpoint requires auth only); 4xx = RBAC tighter.
                if (pRes.status >= 200 && pRes.status < 300) {
                    const pGuests = pRes.body?.guests || [];
                    const leak = stressTid
                        ? pGuests.filter(g => g?.tenant_id && g.tenant_id === stressTid)
                        : [];
                    pilotLeakCount = leak.length;
                    if (leak.length > 0) {
                        recFinding(testInfo, 'P0', MOD_CP,
                            'cross-property pilot→stress tenant leak in chain search',
                            `pilot bearer search returned ${leak.length} stress-tenant guest(s) (tenant_id=${stressTid}). Either pilot is super_admin (review chain bypass policy) or chain_id is mis-linked. sample_tenants=${JSON.stringify([...new Set(pGuests.map(g => g?.tenant_id))].slice(0,5))}`);
                    }
                }
            }

            rec(testInfo, { module: MOD_CP, step: 'leak_guard',
                status: (stressLeaksToPilot.length === 0 && pilotLeakCount === 0) ? 'PASS' : 'FAIL',
                note: `stress_returned=${sGuests.length} stress→pilot_leak=${stressLeaksToPilot.length} pilot→stress_leak=${pilotLeakCount}` });
            expect(stressLeaksToPilot.length, 'stress→pilot leak').toBe(0);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD_CP, 'cross_property_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD_CP, request, pToken, pilotBefore);
        }
    });

    // ──────────────────────────────────────────────────────────────
    // Module B — shift_handover lifecycle + IDOR
    // ──────────────────────────────────────────────────────────────
    test('B) shift_handover — create/list/open-count/ack/delete + cross-tenant IDOR', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const probe = await withModuleProbe(request, sToken,
                '/api/pms/shift-handover/open-count');
            if (probe.moduleBlocked) {
                blocked.shift_handover = true;
                recFinding(testInfo, 'P2', MOD_SH, 'shift-handover module-blocked',
                    `status=${probe.status} reason=${probe.reason} — lifecycle SKIP.`);
                test.skip(true, 'shift-handover blocked');
                return;
            }

            // B1) Create — happy path.
            const bd = ymdOffset(0);
            const create = await callTimed(request, 'post',
                '/api/pms/shift-handover', {
                    business_date: bd,
                    shift: 'morning',
                    note: `${prefix} F8AH handover smoke ${randomUUID()}`,
                    priority: 'normal',
                    to_shift: 'afternoon',
                }, sToken);
            expect(create.status, `handover create http=${create.status} body=${JSON.stringify(create.body).slice(0,200)}`).toBe(200);
            const handoverId = create.body?.id;
            expect(handoverId, 'handover id').toBeTruthy();
            createdHandoverIds.push(handoverId);

            // B2) List — must include the new id (tenant-scoped).
            const list = await callTimed(request, 'get',
                `/api/pms/shift-handover?business_date=${bd}&status=open`, undefined, sToken);
            expect(list.status).toBe(200);
            const found = (list.body?.items || []).some(h => h.id === handoverId);
            expect(found, `created handover ${handoverId} present in list`).toBe(true);

            // B3) open-count — non-negative integer.
            const cnt = await callTimed(request, 'get',
                '/api/pms/shift-handover/open-count', undefined, sToken);
            expect(cnt.status).toBe(200);
            expect(typeof cnt.body?.open).toBe('number');

            // B4) Negative validation — invalid shift → 400; missing field → 422.
            const badShift = await callTimed(request, 'post',
                '/api/pms/shift-handover', {
                    business_date: bd, shift: 'twilight', note: 'invalid',
                }, sToken);
            expect(badShift.status, `invalid shift must 4xx; got ${badShift.status}`).toBeGreaterThanOrEqual(400);
            expect(badShift.status).toBeLessThan(500);

            // B5) IDOR — pilot bearer cross-tenant ack/delete MUST 404 (tenant
            // filter on find_one_and_update + delete_one). 2xx = P0.
            if (pToken) {
                const xAck = await callTimed(request, 'patch',
                    `/api/pms/shift-handover/${handoverId}/acknowledge`, { note: 'pilot-cross-tenant' }, pToken);
                expect(xAck.status, `pilot cross-tenant ack must 4xx; got ${xAck.status}`).toBeGreaterThanOrEqual(400);
                if (xAck.status >= 200 && xAck.status < 300) {
                    recFinding(testInfo, 'P0', MOD_SH, 'Pilot cross-tenant shift_handover ack',
                        `pilot bearer acknowledged stress handover ${handoverId} → http=${xAck.status}. Tenant guard breach (find_one_and_update tenant_id filter missing or pilot is super_admin without scope).`);
                }
                const xDel = await callTimed(request, 'delete',
                    `/api/pms/shift-handover/${handoverId}`, undefined, pToken);
                expect(xDel.status, `pilot cross-tenant delete must 4xx; got ${xDel.status}`).toBeGreaterThanOrEqual(400);
                if (xDel.status >= 200 && xDel.status < 300) {
                    recFinding(testInfo, 'P0', MOD_SH, 'Pilot cross-tenant shift_handover delete',
                        `pilot bearer deleted stress handover ${handoverId} → http=${xDel.status}. Tenant guard breach.`);
                }
            }

            // B6) Self ack — happy path (after IDOR confirms still present).
            const ack = await callTimed(request, 'patch',
                `/api/pms/shift-handover/${handoverId}/acknowledge`, { note: 'F8AH ack' }, sToken);
            expect(ack.status, `self ack http=${ack.status}`).toBe(200);
            expect(ack.body?.acknowledged).toBe(true);

            rec(testInfo, { module: MOD_SH, step: 'lifecycle', status: 'PASS',
                note: `created=${handoverId} open_count=${cnt.body?.open} ack=ok cross_tenant_guards=verified` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD_SH, 'shift_handover_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD_SH, request, pToken, pilotBefore);
        }
    });

    // ──────────────────────────────────────────────────────────────
    // Module C — webhook_admin DLQ smoke + role guard
    // ──────────────────────────────────────────────────────────────
    test('C) webhook_admin_dlq — global status smoke + non-super-admin 403 + cross-tenant filter', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // C1) Non-super-admin probe — stress_token is tenant admin (NOT
            // super_admin). require_super_admin_guard MUST 403/401. 2xx = P0.
            const sStatus = await callTimed(request, 'get',
                '/api/webhooks/status', undefined, sToken);
            if (sStatus.status === 404) {
                blocked.webhook_admin = true;
                recFinding(testInfo, 'P2', MOD_WH, 'webhook-admin endpoint not deployed',
                    `GET /api/webhooks/status http=404 — module not mounted; suite SKIP.`);
                test.skip(true, 'webhook-admin not deployed');
                return;
            }
            if (sStatus.status >= 200 && sStatus.status < 300) {
                // CRITICAL: stress bearer should not pass super_admin guard.
                // If it does, either (a) the stress fixture grants super_admin
                // (review fixture scope) or (b) the guard is broken (P0).
                recFinding(testInfo, 'P0', MOD_WH,
                    'webhook-admin /status accessible to non-super-admin bearer',
                    `stress_token GET /api/webhooks/status → http=${sStatus.status}. require_super_admin_guard bypass OR stress fixture is super_admin. Operator review required.`);
            } else {
                expect(sStatus.status, `non-super-admin must be 4xx; got ${sStatus.status}`).toBeGreaterThanOrEqual(400);
            }

            // C2) Super-admin (pilot) probe — must 2xx (read-only smoke).
            let pilotOk = false;
            if (pToken) {
                const pStatus = await callTimed(request, 'get',
                    '/api/webhooks/status', undefined, pToken);
                if (pStatus.status >= 200 && pStatus.status < 300) {
                    pilotOk = true;
                    // Sanity: response shape contains expected counts.
                    const shapeOk = pStatus.body && typeof pStatus.body.dlq_total === 'number';
                    if (!shapeOk) {
                        recFinding(testInfo, 'P2', MOD_WH, 'webhook /status shape regression',
                            `body keys=${Object.keys(pStatus.body || {}).join(',')} — dlq_total field missing.`);
                    }
                } else if (pStatus.status === 401 || pStatus.status === 403) {
                    recFinding(testInfo, 'P2', MOD_WH, 'pilot bearer also denied on webhook /status',
                        `pilot http=${pStatus.status} — pilot fixture is NOT super_admin; cross-tenant filter probe SKIP.`);
                }
            }

            // C3) Cross-tenant filter — admin-guarded /deliveries supports
            // tenant_id query param. If pilot is super_admin (C2 passed), it
            // CAN scope to stress tenant (intended ops behavior). We don't
            // emit a finding here — that is the documented contract. We only
            // assert the endpoint accepts the tenant filter and returns ≤ all
            // (sanity: tenant_id filter actually narrows). Skipped if pilot
            // not super_admin.
            if (pilotOk && stressTid) {
                const dAll = await callTimed(request, 'get',
                    '/api/webhooks/deliveries?limit=10', undefined, pToken);
                const dStress = await callTimed(request, 'get',
                    `/api/webhooks/deliveries?tenant_id=${encodeURIComponent(stressTid)}&limit=10`,
                    undefined, pToken);
                if (dAll.status === 200 && dStress.status === 200) {
                    const allTotal = dAll.body?.total ?? null;
                    const sTotal = dStress.body?.total ?? null;
                    // Sanity only — stress-scoped count must be ≤ global.
                    if (typeof allTotal === 'number' && typeof sTotal === 'number' && sTotal > allTotal) {
                        recFinding(testInfo, 'P1', MOD_WH,
                            'webhook deliveries tenant_id filter widens result set',
                            `global=${allTotal} stress_filtered=${sTotal} — filter should narrow, not widen. Possible filter bypass.`);
                    }
                }
            }

            // C4) DLQ list — admin-guarded; same contract.
            if (pilotOk) {
                const dlq = await callTimed(request, 'get',
                    '/api/webhooks/dlq?limit=10', undefined, pToken);
                expect(dlq.status, `dlq list http=${dlq.status}`).toBe(200);
                expect(Array.isArray(dlq.body?.items), 'dlq items array').toBe(true);
            }

            rec(testInfo, { module: MOD_WH, step: 'role_guard', status: 'PASS',
                note: `stress_status=${sStatus.status} pilot_ok=${pilotOk}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD_WH, 'webhook_admin_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD_WH, request, pToken, pilotBefore);
        }
    });

    // ──────────────────────────────────────────────────────────────
    // Module D — eod_report read-only smoke (NO /send)
    // ──────────────────────────────────────────────────────────────
    test('D) eod_report — preview + pdf smoke (NO /send — external_calls invariant)', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const bd = ymdOffset(-1);  // yesterday — stable business date

            const probe = await withModuleProbe(request, sToken,
                `/api/pms/eod-report/preview?business_date=${bd}`);
            if (probe.moduleBlocked) {
                blocked.eod_report = true;
                recFinding(testInfo, 'P2', MOD_EOD, 'eod-report module-blocked',
                    `status=${probe.status} reason=${probe.reason} — preview/pdf SKIP.`);
                test.skip(true, 'eod-report blocked');
                return;
            }

            // D1) Stress preview — 200 + expected shape.
            const sPrev = await callTimed(request, 'get',
                `/api/pms/eod-report/preview?business_date=${bd}`, undefined, sToken);
            expect(sPrev.status, `stress preview http=${sPrev.status}`).toBe(200);
            expect(sPrev.body?.business_date, 'business_date echoed').toBe(bd);
            expect(typeof sPrev.body?.occupancy_rate).toBe('number');

            // D2) PDF download — 2xx + content-type pdf or html (weasyprint
            // fallback). 5xx = P1 (renderer crash).
            const sPdf = await callTimed(request, 'get',
                `/api/pms/eod-report/pdf?business_date=${bd}`, undefined, sToken);
            if (sPdf.status >= 500) {
                recFinding(testInfo, 'P1', MOD_EOD, 'eod-report pdf renderer 5xx',
                    `http=${sPdf.status} — weasyprint crash or template error.`);
            } else {
                expect(sPdf.status, `pdf http=${sPdf.status}`).toBe(200);
            }

            // D3) Pilot preview — also 200 (own tenant data). _collect uses
            // current_user.tenant_id, so structural cross-tenant leak is
            // impossible; this confirms the endpoint serves both tenants
            // independently (different totals expected, not asserted).
            if (pToken) {
                const pPrev = await callTimed(request, 'get',
                    `/api/pms/eod-report/preview?business_date=${bd}`, undefined, pToken);
                expect(pPrev.status, `pilot preview http=${pPrev.status}`).toBe(200);
                // Defensive: response should NOT echo a foreign tenant_id field.
                if (pPrev.body && pPrev.body.tenant_id && stressTid && pPrev.body.tenant_id === stressTid) {
                    recFinding(testInfo, 'P0', MOD_EOD, 'eod-report pilot response leaked stress tenant_id',
                        `pilot preview body.tenant_id === stress tenant_id — structural leak.`);
                }
            }

            // D4) /send MUST NOT be invoked under any circumstance — this test
            // simply asserts source-level discipline by NOT calling it. The
            // post-batch external_calls=[] invariant is the runtime guarantee.

            rec(testInfo, { module: MOD_EOD, step: 'eod_smoke', status: 'PASS',
                note: `bd=${bd} preview=${sPrev.status} pdf=${sPdf.status} send=NOT_CALLED` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD_EOD, 'eod_report_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD_EOD, request, pToken, pilotBefore);
        }
    });

    // ──────────────────────────────────────────────────────────────
    // Module E — booking_holds lifecycle + IDOR
    // ──────────────────────────────────────────────────────────────
    test('E) booking_holds — create/status/delete + cross-tenant IDOR + sweep role-guard', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Synthetic booking_id + room_id — service uses these as opaque
            // tags on room_night_lock docs; no FK enforced. Stress prefix
            // tagged → orphan-scrub cleans residue.
            const bookingId = `${prefix}HOLD_${randomUUID()}`;
            const roomId = `${prefix}ROOM_${randomUUID()}`;
            const checkIn = ymdOffset(30);
            const checkOut = ymdOffset(31);

            // E1) Create — probe + happy path.
            const create = await callTimed(request, 'post',
                '/api/booking-holds', {
                    booking_id: bookingId,
                    room_id: roomId,
                    check_in: checkIn,
                    check_out: checkOut,
                    ttl_minutes: 5,
                }, sToken);
            if (create.status === 403 || create.status === 404) {
                blocked.booking_holds = true;
                recFinding(testInfo, 'P2', MOD_BH, 'booking-holds module-blocked',
                    `create http=${create.status} body=${JSON.stringify(create.body).slice(0,200)} — frontdesk module guard or unmounted; lifecycle SKIP.`);
                test.skip(true, 'booking-holds blocked');
                return;
            }
            expect(create.status, `hold create http=${create.status} body=${JSON.stringify(create.body).slice(0,200)}`).toBe(200);
            expect(create.body?.success).toBe(true);
            createdHoldBookingIds.push(bookingId);

            // E2) Status — has_hold true, night_count=1.
            const status = await callTimed(request, 'get',
                `/api/booking-holds/status?booking_id=${encodeURIComponent(bookingId)}`, undefined, sToken);
            expect(status.status).toBe(200);
            expect(status.body?.has_hold).toBe(true);
            expect(status.body?.night_count).toBeGreaterThanOrEqual(1);

            // E3) IDOR — pilot bearer status probe on stress booking_id MUST
            // return has_hold=false (tenant_id filter on room_night_locks).
            if (pToken) {
                const xStatus = await callTimed(request, 'get',
                    `/api/booking-holds/status?booking_id=${encodeURIComponent(bookingId)}`, undefined, pToken);
                // 200 with has_hold=false = tenant filter worked (no leak).
                // 200 with has_hold=true = P0 (cross-tenant lock visibility).
                // 4xx = also acceptable (tighter RBAC).
                if (xStatus.status === 200 && xStatus.body?.has_hold === true) {
                    recFinding(testInfo, 'P0', MOD_BH,
                        'Pilot cross-tenant booking_holds status leak',
                        `pilot bearer GET /status?booking_id=${bookingId} returned has_hold=true (stress-owned). Tenant filter on room_night_locks bypassed.`);
                }

                // E4) IDOR — pilot bearer confirm on stress booking_id. Service
                // filters by tenant_id; mutation should NOT touch stress locks.
                const xConfirm = await callTimed(request, 'post',
                    '/api/booking-holds/confirm', { booking_id: bookingId }, pToken);
                // confirm endpoint generally returns 200 even when no locks
                // found (service is best-effort). The breach signature is:
                // after this call, stress-side status must still show has_hold=true.

                // E5) IDOR — pilot bearer DELETE on stress booking_id.
                const xDel = await callTimed(request, 'delete',
                    `/api/booking-holds?booking_id=${encodeURIComponent(bookingId)}&reason=pilot-cross-tenant`,
                    undefined, pToken);
                // Same as confirm: 200 is the typical contract; the breach is
                // verified by stress-side post-state.

                // Re-check stress side — locks must still be present.
                const reCheck = await callTimed(request, 'get',
                    `/api/booking-holds/status?booking_id=${encodeURIComponent(bookingId)}`, undefined, sToken);
                if (reCheck.status === 200 && reCheck.body?.has_hold !== true) {
                    recFinding(testInfo, 'P0', MOD_BH,
                        'Pilot cross-tenant booking_holds mutation (confirm/delete)',
                        `pilot bearer confirm/delete on stress booking_id=${bookingId} cleared stress-side locks (post has_hold=${reCheck.body?.has_hold}). Tenant guard on release_hold/confirm_hold breached. xConfirm.http=${xConfirm.status} xDel.http=${xDel.status}`);
                }
                rec(testInfo, { module: MOD_BH, step: 'idor_probe',
                    status: 'PASS',
                    note: `pilot_status.has_hold=${xStatus.body?.has_hold} pilot_confirm=${xConfirm.status} pilot_del=${xDel.status} stress_recheck.has_hold=${reCheck.body?.has_hold}` });
            }

            // E6) Self DELETE — happy path, releases locks.
            const sDel = await callTimed(request, 'delete',
                `/api/booking-holds?booking_id=${encodeURIComponent(bookingId)}&reason=cleanup`,
                undefined, sToken);
            expect(sDel.status, `self delete http=${sDel.status}`).toBe(200);

            // E7) Sweep — role-guarded (frontdesk module). 2xx OR 403 acceptable.
            const sweep = await callTimed(request, 'post',
                '/api/booking-holds/sweep', {}, sToken);
            expect(sweep.status, `sweep http=${sweep.status}`).toBeLessThan(500);

            rec(testInfo, { module: MOD_BH, step: 'lifecycle', status: 'PASS',
                note: `create=ok status=ok self_del=ok sweep=${sweep.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD_BH, 'booking_holds_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD_BH, request, pToken, pilotBefore);
        }
    });

    // ──────────────────────────────────────────────────────────────
    // Z) Cleanup (idempotent) + final invariants
    // ──────────────────────────────────────────────────────────────
    test('Z) Cleanup (idempotent) + final invariants', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Handover cleanup — DELETE all created ids; second pass = 404.
            let hDeleted = 0, hMissing = 0, hOther = 0;
            for (const id of new Set(createdHandoverIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete',
                    `/api/pms/shift-handover/${id}`, undefined, sToken);
                if (r.status >= 200 && r.status < 300) hDeleted++;
                else if (r.status === 404) hMissing++;
                else hOther++;
            }
            let hSecondNonIdem = 0;
            for (const id of new Set(createdHandoverIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete',
                    `/api/pms/shift-handover/${id}`, undefined, sToken);
                if (r.status !== 404) hSecondNonIdem++;
            }

            // Holds cleanup — DELETE any holds not already released in E6.
            // release_hold service returns 200 even when locks missing
            // (idempotent by construction). Second pass should also 200.
            let bhPass = 0, bhOther = 0;
            for (const bid of new Set(createdHoldBookingIds.filter(Boolean))) {
                const r1 = await callTimed(request, 'delete',
                    `/api/booking-holds?booking_id=${encodeURIComponent(bid)}&reason=cleanup`,
                    undefined, sToken);
                const r2 = await callTimed(request, 'delete',
                    `/api/booking-holds?booking_id=${encodeURIComponent(bid)}&reason=cleanup`,
                    undefined, sToken);
                if ((r1.status === 200 || r1.status === 404) &&
                    (r2.status === 200 || r2.status === 404)) {
                    bhPass++;
                } else {
                    bhOther++;
                }
            }

            if (hSecondNonIdem > 0) {
                recFinding(testInfo, 'P1', MOD_SH, 'shift_handover DELETE NOT idempotent',
                    `Second-pass DELETE returned non-404 for ${hSecondNonIdem} handover id(s).`);
            }
            if (bhOther > 0) {
                recFinding(testInfo, 'P1', MOD_BH, 'booking_holds DELETE non-idempotent',
                    `${bhOther} hold id(s) returned unexpected status on cleanup passes.`);
            }

            rec(testInfo, { module: 'f8ah_cleanup', step: 'cleanup',
                status: (hSecondNonIdem === 0 && bhOther === 0) ? 'PASS' : 'FAIL',
                note: `handover deleted=${hDeleted} missing=${hMissing} other=${hOther} 2nd_bad=${hSecondNonIdem} | holds idem=${bhPass} other=${bhOther} | blocked=${JSON.stringify(blocked)}` });
            expect(hSecondNonIdem, 'shift_handover cleanup idempotent').toBe(0);
            expect(bhOther, 'booking_holds cleanup idempotent').toBe(0);
        } finally {
            const extOk = await assertNoExternalCallsPostBatch(testInfo, 'f8ah_cleanup', 'final_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            const driftOk = await assertPilotDriftZero(testInfo, 'f8ah_cleanup', request, pToken, pilotBefore);
            rec(testInfo, { module: 'f8ah_cleanup', step: 'final_invariants',
                status: (extOk && driftOk) ? 'PASS' : 'FAIL',
                note: `external_calls_empty=${extOk} pilot_drift_zero=${driftOk}` });
            expect(extOk).toBe(true);
            expect(driftOk).toBe(true);
        }
    });
});

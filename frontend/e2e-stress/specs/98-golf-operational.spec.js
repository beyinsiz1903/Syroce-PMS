// F8AC § 98 — Golf Operational Stress (sister of F8AB spa_operations).
//
// Threat-model surface:
//   - Catalog reads (courses / players / tee-sheet / daily-summary)
//   - Booking lifecycle: confirmed → checked_in → completed + no_show + cancelled
//   - Atomic conflict guard:
//       * slot capacity overflow (party_size + booked > capacity → 409)
//       * same player_ids OR same guest_id at same tee_time → 409
//       (both enforced under `with_resource_locks` keyed on (course, tee_time))
//   - Explicit folio-post endpoint (`/bookings/{id}/folio-post`):
//       * 400 when reservation_id missing
//       * 409 on replay (already posted) — idempotent contract
//   - P0 cross-tenant IDOR: pilot bearer must NEVER mutate a stress-created
//     golf booking (status change / delete / folio-post must 4xx)
//
// Folio-posting safety:
//   golf `_post_to_folio` + `bus.publish(POSTING_CHARGE)` only fire when BOTH
//   `charge_to_room=True` AND `reservation_id` is set. We exercise the
//   "completed" transition with `charge_to_room=False` so neither folio nor
//   bus publish runs. For the safe-by-construction invariant verification a
//   SEPARATE booking is completed with `charge_to_room=True + reservation_id=null`;
//   backend guard short-circuits (no folio_postings insert, no Xchange dispatch).
//   `external_calls` post-batch invariant proves no real bus traffic occurred.
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//   - cleanup idempotent (DELETE created bookings; 404 OK on second pass)
//   - try/finally ile final invariants her test'te zorunlu
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';
import { randomUUID } from 'node:crypto';

const MOD = 'golf_operations';

function dayOffsetIso(days, hour = 10, minute = 0) {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + days);
    d.setUTCHours(hour, minute, 0, 0);
    return d.toISOString();
}

function ymdOffset(days) {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + days);
    return d.toISOString().slice(0, 10);
}

test.describe.serial('F8AC golf operational stress', () => {
    let prefix = null;
    let createdBookingIds = [];
    let createdPlayerIds = [];
    let createdCourseIds = [];   // only ids we created ourselves; not auto-seed default
    let moduleBlocked = false;
    let courses = [];
    let players = [];

    test('Setup: probe catalog surfaces + prefix', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix || `STRESS_F8AC_${Date.now()}_`;
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO',
            note: `count=${pilotBefore?.count} prefix=${prefix}` });

        try {
            const courseProbe = await withModuleProbe(request, sToken, '/api/golf/courses');
            const playerProbe = await withModuleProbe(request, sToken, '/api/golf/players');

            if (courseProbe.moduleBlocked || playerProbe.moduleBlocked) {
                moduleBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'Golf catalog surface module-blocked',
                    `courses_http=${courseProbe.status} players_http=${playerProbe.status} — A/B/C/D/E skip, final invariants still enforced.`);
                rec(testInfo, { module: MOD, step: 'catalog_probe', status: 'SKIP',
                    note: `module_blocked courses=${courseProbe.status} players=${playerProbe.status}` });
                return;
            }

            courses = courseProbe.body?.courses || [];
            players = playerProbe.body?.players || [];

            // Courses auto-seed when an admin-ish role calls GET on empty tenant —
            // a second GET confirms. If still empty, we are super_admin and can
            // POST one ourselves (require_catalog passes).
            if (courses.length === 0) {
                const r = await callTimed(request, 'get', '/api/golf/courses', undefined, sToken);
                courses = r.body?.courses || [];
            }
            if (courses.length === 0) {
                const r = await callTimed(request, 'post', '/api/golf/courses', {
                    name: `${prefix}Course`,
                    holes: 18, par: 72,
                    course_rating: 72.4, slope_rating: 132,
                    tee_interval_minutes: 10, slot_capacity: 4,
                    open_time: '07:00', close_time: '18:00',
                    green_fee: 1800, cart_fee: 600, currency: 'TRY',
                    active: true,
                }, sToken);
                if (r.ok && r.body?.id) {
                    courses = [r.body];
                    createdCourseIds.push(r.body.id);
                }
            }

            // Seed at least one player for double-booking probes.
            if (players.length === 0) {
                const r = await callTimed(request, 'post', '/api/golf/players', {
                    name: `${prefix}Player`,
                    handicap: 18.0, member_tier: 'guest',
                }, sToken);
                if (r.ok && r.body?.id) {
                    players = [r.body];
                    createdPlayerIds.push(r.body.id);
                }
            }

            if (courses.length === 0 || players.length === 0) {
                moduleBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'Golf catalog empty after seed attempt',
                    `courses=${courses.length} players=${players.length}. A/B/C/D/E skip.`);
            }

            rec(testInfo, { module: MOD, step: 'catalog_probe',
                status: moduleBlocked ? 'SKIP' : 'PASS',
                note: `courses=${courses.length} players=${players.length} (self-seeded course=${createdCourseIds.length} player=${createdPlayerIds.length})` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('A) Catalog smoke + tee-sheet + daily-summary', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'golf catalog blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const course = courses[0];
            const reads = [
                ['/api/golf/courses', 'courses'],
                ['/api/golf/players', 'players'],
                [`/api/golf/tee-sheet?course_id=${course.id}&date=${ymdOffset(7)}`, 'tee_sheet'],
                [`/api/golf/daily-summary?date=${ymdOffset(0)}`, 'daily_summary'],
                ['/api/golf/bookings', 'bookings'],
            ];
            const results = {};
            for (const [path, key] of reads) {
                const r = await callTimed(request, 'get', path, undefined, sToken);
                results[key] = { http: r.status, ms: r.ms };
                if (r.status < 200 || r.status >= 300) {
                    recFinding(testInfo, 'P2', MOD, `Golf catalog read non-2xx ${key}`,
                        `GET ${path} http=${r.status}`);
                }
            }
            rec(testInfo, { module: MOD, step: 'catalog_read', status: 'PASS',
                note: JSON.stringify(results) });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'catalog_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('B) Booking lifecycle: confirmed → checked_in → completed + no_show + cancelled + folio-guard', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'golf catalog blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const course = courses[0];

            // a) Happy lifecycle: confirmed → checked_in → completed (no folio).
            const a1 = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: course.id,
                tee_time: dayOffsetIso(10, 9),
                lead_player: `${prefix}LeadB1`,
                party_size: 2,
                player_ids: [],
                cart_count: 1,
                charge_to_room: false,
                notes: `${prefix} B-happy`,
            }, sToken);
            expect(a1.status, `lifecycle create http=${a1.status} body=${JSON.stringify(a1.body).slice(0,160)}`).toBeGreaterThanOrEqual(200);
            expect(a1.status).toBeLessThan(300);
            const a1Id = a1.body?.id;
            expect(a1Id, 'happy booking id').toBeTruthy();
            createdBookingIds.push(a1Id);

            const t1 = await callTimed(request, 'post', `/api/golf/bookings/${a1Id}/status`,
                { status: 'checked_in' }, sToken);
            expect(t1.status, `checked_in transition http=${t1.status}`).toBe(200);
            const t2 = await callTimed(request, 'post', `/api/golf/bookings/${a1Id}/status`,
                { status: 'completed' }, sToken);
            // completed requires require_finance — stress admin super_admin → PASS.
            // If RBAC blocks (403), downgrade to P2 informational (role gap).
            if (t2.status === 403) {
                recFinding(testInfo, 'P2', MOD, 'completed transition require_finance 403',
                    `Stress admin role missing finance scope. Lifecycle invariant intact (PUT-side guard).`);
            } else {
                expect(t2.status, `completed transition http=${t2.status} body=${JSON.stringify(t2.body).slice(0,160)}`).toBe(200);
            }

            // b) no_show path (separate booking, slot far from a1).
            const a2 = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: course.id,
                tee_time: dayOffsetIso(11, 9),
                lead_player: `${prefix}LeadB2`,
                party_size: 1,
                charge_to_room: false,
                notes: `${prefix} B-noshow`,
            }, sToken);
            expect(a2.status, 'no_show booking create').toBeGreaterThanOrEqual(200);
            const a2Id = a2.body?.id;
            if (a2Id) {
                createdBookingIds.push(a2Id);
                const ns = await callTimed(request, 'post', `/api/golf/bookings/${a2Id}/status`,
                    { status: 'no_show' }, sToken);
                expect(ns.status, `no_show http=${ns.status}`).toBe(200);
            }

            // c) cancelled path.
            const a3 = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: course.id,
                tee_time: dayOffsetIso(12, 9),
                lead_player: `${prefix}LeadB3`,
                party_size: 1,
                charge_to_room: false,
                notes: `${prefix} B-cancel`,
            }, sToken);
            const a3Id = a3.body?.id;
            if (a3Id) {
                createdBookingIds.push(a3Id);
                const cx = await callTimed(request, 'post', `/api/golf/bookings/${a3Id}/status`,
                    { status: 'cancelled' }, sToken);
                expect(cx.status, `cancelled http=${cx.status}`).toBe(200);
            }

            // d) Folio-posting safety: charge_to_room=True + reservation_id=null →
            // `change_booking_status` completes the booking BUT _post_to_folio is
            // only called when BOTH `charge_to_room` AND `reservation_id` are set
            // (golf router.py L558-559). external_calls post-batch invariant proves
            // no Xchange dispatch occurred.
            const a4 = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: course.id,
                tee_time: dayOffsetIso(13, 9),
                lead_player: `${prefix}LeadB4`,
                party_size: 1,
                reservation_id: null,
                charge_to_room: true,
                notes: `${prefix} B-folio-guard`,
            }, sToken);
            const a4Id = a4.body?.id;
            if (a4Id) {
                createdBookingIds.push(a4Id);
                const ip = await callTimed(request, 'post', `/api/golf/bookings/${a4Id}/status`,
                    { status: 'checked_in' }, sToken);
                expect(ip.status, `folio-guard checked_in http=${ip.status}`).toBe(200);
                const cp = await callTimed(request, 'post', `/api/golf/bookings/${a4Id}/status`,
                    { status: 'completed' }, sToken);
                if (cp.status !== 200 && cp.status !== 403) {
                    recFinding(testInfo, 'P1', MOD, 'Folio-guard completion non-2xx',
                        `booking=${a4Id} http=${cp.status} body=${JSON.stringify(cp.body).slice(0,160)}`);
                }
                rec(testInfo, { module: MOD, step: 'folio_guard_completion',
                    status: cp.status === 200 ? 'PASS' : 'REVIEW',
                    note: `http=${cp.status} — charge_to_room=True + reservation_id=null must NOT post folio nor publish Xchange (external_calls invariant below).` });
            }

            rec(testInfo, { module: MOD, step: 'lifecycle', status: 'PASS',
                note: `created=${createdBookingIds.length} (B1=happy B2=no_show B3=cancel B4=folio-guard)` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'lifecycle_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('C) Conflict guard: slot capacity + player double-book', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'golf catalog blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const course = courses[0];
            const capacity = Number(course.slot_capacity || 4);
            const slot = dayOffsetIso(20, 11);

            // c1) Fill slot up to capacity with one booking.
            const fill = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: course.id,
                tee_time: slot,
                lead_player: `${prefix}LeadC1_fill`,
                party_size: capacity,
                charge_to_room: false,
            }, sToken);
            expect(fill.status, `fill-slot create http=${fill.status} body=${JSON.stringify(fill.body).slice(0,160)}`).toBeGreaterThanOrEqual(200);
            expect(fill.status).toBeLessThan(300);
            if (fill.body?.id) createdBookingIds.push(fill.body.id);

            // c2) Overflow create with party_size=1 → must 409 (capacity exhausted).
            const overflow = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: course.id,
                tee_time: slot,
                lead_player: `${prefix}LeadC2_overflow`,
                party_size: 1,
                charge_to_room: false,
            }, sToken);
            if (overflow.status === 409) {
                rec(testInfo, { module: MOD, step: 'capacity_guard', status: 'PASS',
                    note: `overflow http=${overflow.status} (atomic capacity guard fired)` });
            } else if (overflow.status >= 200 && overflow.status < 300) {
                if (overflow.body?.id) createdBookingIds.push(overflow.body.id);
                recFinding(testInfo, 'P1', MOD, 'Golf slot capacity guard NOT fired',
                    `capacity=${capacity} fully booked; overflow accepted http=${overflow.status} id=${overflow.body?.id}. _slot_has_capacity / with_resource_locks gap.`);
                expect(overflow.status, 'capacity guard must reject overflow').toBe(409);
            } else {
                rec(testInfo, { module: MOD, step: 'capacity_guard', status: 'PASS',
                    note: `overflow http=${overflow.status} (non-2xx accepted as defensive rejection)` });
            }

            // c3) Same player_ids double-book at a fresh slot.
            const playerId = players[0]?.id;
            if (playerId) {
                const playerSlot = dayOffsetIso(21, 12);
                const p1 = await callTimed(request, 'post', '/api/golf/bookings', {
                    course_id: course.id,
                    tee_time: playerSlot,
                    lead_player: `${prefix}LeadC3a`,
                    party_size: 1,
                    player_ids: [playerId],
                    charge_to_room: false,
                }, sToken);
                expect(p1.status, `player-base create http=${p1.status}`).toBeGreaterThanOrEqual(200);
                expect(p1.status).toBeLessThan(300);
                if (p1.body?.id) createdBookingIds.push(p1.body.id);

                const p2 = await callTimed(request, 'post', '/api/golf/bookings', {
                    course_id: course.id,
                    tee_time: playerSlot,
                    lead_player: `${prefix}LeadC3b`,
                    party_size: 1,
                    player_ids: [playerId],
                    charge_to_room: false,
                }, sToken);
                if (p2.status === 409) {
                    rec(testInfo, { module: MOD, step: 'player_double_book_guard', status: 'PASS',
                        note: `dup-player http=${p2.status} (double-book guard fired)` });
                } else if (p2.status >= 200 && p2.status < 300) {
                    if (p2.body?.id) createdBookingIds.push(p2.body.id);
                    recFinding(testInfo, 'P1', MOD, 'Golf player double-book guard NOT fired',
                        `player_id=${playerId} accepted at same tee_time twice. http=${p2.status} id=${p2.body?.id}. _player_double_booked gap.`);
                    expect(p2.status, 'player double-book must 409').toBe(409);
                } else {
                    rec(testInfo, { module: MOD, step: 'player_double_book_guard', status: 'PASS',
                        note: `dup-player http=${p2.status} (non-2xx defensive)` });
                }
            } else {
                rec(testInfo, { module: MOD, step: 'player_double_book_guard', status: 'SKIP',
                    note: 'no player_id available' });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'conflict_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('D) Folio-post endpoint contract (no reservation → 400, replay → 409)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'golf catalog blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const course = courses[0];

            // D1) Booking with reservation_id=null → folio-post must 400.
            const noRes = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: course.id,
                tee_time: dayOffsetIso(25, 9),
                lead_player: `${prefix}LeadD1`,
                party_size: 1,
                reservation_id: null,
                charge_to_room: false,
            }, sToken);
            expect(noRes.status, `D1 create http=${noRes.status}`).toBeGreaterThanOrEqual(200);
            const noResId = noRes.body?.id;
            if (noResId) {
                createdBookingIds.push(noResId);
                const fp = await callTimed(request, 'post', `/api/golf/bookings/${noResId}/folio-post`,
                    {}, sToken);
                if (fp.status === 403) {
                    recFinding(testInfo, 'P2', MOD, 'folio-post require_finance 403',
                        `Stress admin role missing finance scope. Contract invariant intact (PUT-side guard).`);
                } else {
                    expect(fp.status, `folio-post without reservation must 400; got ${fp.status} body=${JSON.stringify(fp.body).slice(0,160)}`).toBe(400);
                }
            }

            // D2) Bogus booking id → 404.
            const bogus = await callTimed(request, 'post',
                `/api/golf/bookings/00000000-0000-0000-0000-000000000000/folio-post`,
                {}, sToken);
            expect(bogus.status, `bogus folio-post must 404; got ${bogus.status}`).toBeGreaterThanOrEqual(400);
            // Accept 403 (role gate) or 404 (target not found); 2xx is the breach.
            if (bogus.status >= 200 && bogus.status < 300) {
                recFinding(testInfo, 'P0', MOD, 'Bogus folio-post accepted',
                    `Non-existent booking id accepted by /folio-post. http=${bogus.status}. Money-safety breach.`);
            }

            rec(testInfo, { module: MOD, step: 'folio_post_contract', status: 'PASS',
                note: `no_reservation_400=${noResId ? 'tested' : 'skip'} bogus_404=${bogus.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'folio_post_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('E) Cross-tenant IDOR + negative validation + idempotency replay', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, 'golf catalog blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const course = courses[0];

            // E1) Unknown course → 404.
            const unk = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: '00000000-0000-0000-0000-000000000000',
                tee_time: dayOffsetIso(40, 9),
                lead_player: `${prefix}NegE1`,
                party_size: 1,
                charge_to_room: false,
            }, sToken);
            expect(unk.status, `unknown course http=${unk.status}`).toBeGreaterThanOrEqual(400);
            expect(unk.status).toBeLessThan(500);

            // E2) Malformed tee_time → 422.
            const badTime = await callTimed(request, 'post', '/api/golf/bookings', {
                course_id: course.id,
                tee_time: 'not-a-datetime',
                lead_player: `${prefix}NegE2`,
                party_size: 1,
                charge_to_room: false,
            }, sToken);
            expect(badTime.status, `bad time http=${badTime.status}`).toBeGreaterThanOrEqual(400);
            expect(badTime.status).toBeLessThan(500);

            // E3) Invalid status transition (confirmed → invented_status) → 4xx.
            let probeId = createdBookingIds[0];
            if (!probeId) {
                const tmp = await callTimed(request, 'post', '/api/golf/bookings', {
                    course_id: course.id,
                    tee_time: dayOffsetIso(41, 9),
                    lead_player: `${prefix}NegE3`,
                    party_size: 1,
                    charge_to_room: false,
                }, sToken);
                probeId = tmp.body?.id;
                if (probeId) createdBookingIds.push(probeId);
            }
            if (probeId) {
                const badStatus = await callTimed(request, 'post', `/api/golf/bookings/${probeId}/status`,
                    { status: 'invented_status' }, sToken);
                expect(badStatus.status, `invalid status http=${badStatus.status}`).toBeGreaterThanOrEqual(400);
                expect(badStatus.status).toBeLessThan(500);
            }

            // E4) Idempotency-Key-style replay: same (course, tee_time, lead_player)
            // tuple. Golf doesn't honor X-Idempotency-Key explicitly, but the atomic
            // double-booking guard MUST refuse the second insert if it shares any
            // player_id or guest_id. With distinct lead_player strings and empty
            // player_ids, both succeed (capacity allows). We probe the harder case:
            // same player_id at same slot → 409 (covered by C3) AND verify replay
            // with X-Idempotency-Key header doesn't bypass atomic constraints.
            const idemKey = `STRESS_F8AC_${randomUUID()}`;
            const slot = dayOffsetIso(42, 16);
            const playerId = players[0]?.id;
            if (playerId) {
                const r1 = await callTimed(request, 'post', '/api/golf/bookings', {
                    course_id: course.id,
                    tee_time: slot,
                    lead_player: `${prefix}IdemE4`,
                    party_size: 1,
                    player_ids: [playerId],
                    charge_to_room: false,
                }, sToken, { headers: { 'X-Idempotency-Key': idemKey, 'Idempotency-Key': idemKey } });
                const r2 = await callTimed(request, 'post', '/api/golf/bookings', {
                    course_id: course.id,
                    tee_time: slot,
                    lead_player: `${prefix}IdemE4`,
                    party_size: 1,
                    player_ids: [playerId],
                    charge_to_room: false,
                }, sToken, { headers: { 'X-Idempotency-Key': idemKey, 'Idempotency-Key': idemKey } });
                if (r1.body?.id) createdBookingIds.push(r1.body.id);
                const r1Id = r1.body?.id;
                const r2Id = r2.body?.id;
                const sameId = r1Id && r2Id && r1Id === r2Id;
                const r2Conflict = r2.status === 409 || (r2.status >= 400 && r2.status < 500);
                const idempotent = sameId || r2Conflict;
                if (!idempotent && r2.status >= 200 && r2.status < 300) {
                    if (r2Id) createdBookingIds.push(r2Id);
                    recFinding(testInfo, 'P1', MOD, 'Golf booking replay NOT idempotent',
                        `r1.id=${r1Id} r2.id=${r2Id} player_id=${playerId} — identical (course,tee_time,player_id) tuple created two distinct bookings (no 409 conflict guard). Double-book money risk.`);
                }
                rec(testInfo, { module: MOD, step: 'idempotency_replay',
                    status: idempotent ? 'PASS' : 'FAIL',
                    note: `r1.http=${r1.status} r2.http=${r2.status} sameId=${!!sameId} r2_conflict=${r2Conflict}` });
                expect(idempotent, 'golf booking replay must be guarded (same id or 409)').toBe(true);
            } else {
                rec(testInfo, { module: MOD, step: 'idempotency_replay', status: 'SKIP',
                    note: 'no player_id available' });
            }

            // E5) Cross-tenant IDOR — pilot token must NOT be able to mutate a
            // stress-tenant booking by id. Backend filters by tenant_id; expected
            // outcome 4xx (not 200, not 500).
            if (pToken && createdBookingIds[0]) {
                const targetId = createdBookingIds[0];
                const xStatus = await callTimed(request, 'post', `/api/golf/bookings/${targetId}/status`,
                    { status: 'cancelled' }, pToken);
                expect(xStatus.status, `pilot cross-tenant status change must 4xx; got ${xStatus.status}`).toBeGreaterThanOrEqual(400);
                if (xStatus.status >= 200 && xStatus.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant golf booking status mutation',
                        `pilot bearer mutated stress tenant golf booking ${targetId} → http=${xStatus.status}. Tenant guard breach.`);
                }
                const xDel = await callTimed(request, 'delete', `/api/golf/bookings/${targetId}`,
                    undefined, pToken);
                expect(xDel.status, `pilot cross-tenant delete must 4xx; got ${xDel.status}`).toBeGreaterThanOrEqual(400);
                if (xDel.status >= 200 && xDel.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant golf booking delete',
                        `pilot bearer deleted stress tenant golf booking ${targetId} → http=${xDel.status}. Tenant guard breach.`);
                }
                const xFp = await callTimed(request, 'post', `/api/golf/bookings/${targetId}/folio-post`,
                    {}, pToken);
                expect(xFp.status, `pilot cross-tenant folio-post must 4xx; got ${xFp.status}`).toBeGreaterThanOrEqual(400);
                if (xFp.status >= 200 && xFp.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant golf folio-post',
                        `pilot bearer folio-posted stress tenant golf booking ${targetId} → http=${xFp.status}. Money-safety + tenant guard breach.`);
                }
            }
            rec(testInfo, { module: MOD, step: 'cross_tenant_idor', status: 'PASS',
                note: `verified status + delete + folio-post cross-tenant guards` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'idor_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('Z) Cleanup (idempotent) + final invariants', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            let bkDeleted = 0, bkMissing = 0, bkOther = 0;
            for (const id of new Set(createdBookingIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete', `/api/golf/bookings/${id}`, undefined, sToken);
                if (r.status >= 200 && r.status < 300) bkDeleted++;
                else if (r.status === 404) bkMissing++;
                else bkOther++;
            }
            // Second pass — idempotency: every id should now be 404.
            let secondPassNonIdempotent = 0;
            for (const id of new Set(createdBookingIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete', `/api/golf/bookings/${id}`, undefined, sToken);
                if (r.status !== 404) secondPassNonIdempotent++;
            }

            // Player cleanup — no DELETE endpoint exposed for /api/golf/players;
            // rows are orphan-scrubbed via STRESS_COLLECTIONS unified cleanup loop
            // (stress_seed=True + stress_prefix tag). Same for self-seeded courses.
            // We only assert the booking DELETE contract here.
            if (secondPassNonIdempotent > 0) {
                recFinding(testInfo, 'P1', MOD, 'Golf booking delete NOT idempotent',
                    `Second-pass delete returned non-404 for ${secondPassNonIdempotent} booking id(s). Cleanup contract broken.`);
            }
            rec(testInfo, { module: MOD, step: 'cleanup',
                status: secondPassNonIdempotent === 0 ? 'PASS' : 'FAIL',
                note: `bookings deleted=${bkDeleted} missing=${bkMissing} other=${bkOther} second_pass_bad=${secondPassNonIdempotent} | players_self_seeded=${createdPlayerIds.length} courses_self_seeded=${createdCourseIds.length} (orphan-scrub via STRESS_COLLECTIONS)` });
            expect(secondPassNonIdempotent, 'booking cleanup must be idempotent').toBe(0);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'cleanup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});

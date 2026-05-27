// F8N § 95 — Reservation Lifecycle Deep Stress.
//
// Scope (Task #200 / F8N):
//   12 derin lifecycle varyantı (A–L) — F8A § 05'in TEMEL lifecycle'ını
//   (create / modify / cancel / no-show / overbooking / group / multi-room)
//   GENİŞLETIR. Bu spec'in odağı: edge-case'ler + multi-step orchestrations
//   (split / merge / fee tier / city-ledger transfer / hold expiry).
//
//     A) Waitlist promote                — POST /api/waitlist (yoksa module-blocked + REVIEW)
//     B) Option / hold create + status   — POST /api/booking-holds + GET /api/booking-holds/status
//     C) Overbooking oversell guard      — GET /api/pms-core/overbooking-check + POST quick-booking duplicate reject
//     D) Overbooking yield guard         — same endpoint, RoomType-level sample
//     E) Multi-room partial cancel       — POST /api/pms/bookings/multi-room (3 oda) → POST /api/pms-core/cancel (1 oda)
//     F) Group rooming list batch        — POST /api/pms/groups/create-block + POST /api/pms/groups/rooming-list/{id}
//     G) Rate change after modification  — PUT /api/pms/bookings/{id} total_amount değişikliği
//     H) Split reservation (5-gece→2+3)  — PUT /api/pms/bookings/{id} (kısalt) + POST /api/pms/quick-booking (ikinci leg)
//     I) Merge duplicate guest           — POST /api/guests/{primary_id}/merge (cross-property router)
//     J) No-show fee dry-run             — POST /api/pms-core/no-show + folio fee charge gözlem
//     K) Cancellation policy fee tier    — POST /api/pms-core/cancel (farklı policy'ler) + fee gözlem
//     L) City ledger transfer dry-run    — POST /api/pms-core/folio/city-ledger-transfer
//
// Mutlak kurallar:
//   - external_calls = [] (assertNoExternalCallsPostBatch per major batch + final).
//   - pilot mutation = 0 (assertPilotDriftZero / pilotBookingsCount final gate).
//   - P0 = P1 = 0; 5xx = 0; PII leak = 0; pilot booking ID/tid leak = 0.
//   - Tüm mutasyonlar stress-tenant scope; tüm yeni objeler stress_prefix
//     prefix-tagged ki cleanup yakalasın.
//   - Idempotency-Key her POST'ta zorunlu (F8A § 05 tur-27b CI #43 root cause).
//   - 1500ms gap (F8H standardı; reservation lifecycle ağır bir yüzey).
//
// Module-blocked doctrine (F8H/F8A mirror):
//   - Setup probe (/api/pms/bookings stress-tenant) non-2xx → A–L skip;
//     M (external_calls) ve N (pilot_drift) BAĞIMSIZ çalışır.
//   - Bireysel varyant probe non-2xx (404/403/501) → o varyant SKIP + P2
//     informational; downstream varyantlar etkilenmez. Backend bazı yüzeyleri
//     (özellikle waitlist) production'da henüz mount edilmemiş olabilir.
//
// Reporter satırı: `reservation_deep`.
import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    fetchAllByPrefix, callTimed,
    recPerf, recFinding, pilotBookingsCount,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
} from '../fixtures/stress-helpers.js';

const MOD = 'reservation_deep';
const SUB_PREFIX = 'F8N_RESDEEP';

test.describe.configure({ mode: 'serial' });

test.describe('F8N § 95 — Reservation Lifecycle Deep Stress', () => {
    let bookings = [];
    let rooms = [];
    let guests = [];
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;

    // Spec-local tracking — cleanup ana stress_prefix query'siyle yakalanır.
    const createdBookingIds = [];
    const createdGroupBlockIds = [];
    const createdMultiRoomGroupIds = [];

    function futureDateISO(daysFromNow) {
        const d = new Date();
        d.setUTCDate(d.getUTCDate() + daysFromNow);
        return d.toISOString().slice(0, 10);
    }
    function idemKey(op, i = 0) {
        return `${SUB_PREFIX}_${op}_${Date.now()}_${i}_${cryptoRandomUUID()}`;
    }
    async function gap(ms = 1500) { await new Promise((r) => setTimeout(r, ms)); }

    test('Setup: stress bookings/rooms/guests snapshot + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Architect-iter-1 fix: fetchAllByPrefix non-2xx'te sessizce [] döner →
        // module-blocked yanlış sebep ile (data scarcity) tetiklenebilir. Önce
        // explicit reachability probe yap: /api/pms/bookings + /api/pms/rooms +
        // /api/pms/guests. Herhangi biri non-2xx → moduleBlocked + reason net.
        const probes = [];
        for (const ep of ['/api/pms/bookings?limit=1', '/api/pms/rooms?limit=1', '/api/pms/guests?limit=1']) {
            const r = await callTimed(request, 'get', ep, undefined, stressTokens.stress_token);
            probes.push({ ep, status: r.status, ok: r.ok });
            if (!r.ok) {
                moduleBlocked = true;
                blockedReason = `probe_${ep}_status_${r.status}`;
                recFinding(testInfo, 'P2', MOD, 'PMS surface probe non-2xx — module blocked',
                    `${ep} → ${r.status} body=${JSON.stringify(r.body).slice(0, 120)} — A/B/C/D/E/F/G/H/I/J/K/L skipped, M/N still enforced.`);
                break;
            }
        }

        if (!moduleBlocked) {
            try {
                bookings = await fetchAllByPrefix(request, stressTokens.stress_token,
                    '/api/pms/bookings', 'stress_prefix', prefix);
                rooms = await fetchAllByPrefix(request, stressTokens.stress_token,
                    '/api/pms/rooms', 'stress_prefix', prefix);
                guests = await fetchAllByPrefix(request, stressTokens.stress_token,
                    '/api/pms/guests', 'stress_prefix', prefix);
            } catch (e) {
                moduleBlocked = true;
                blockedReason = `setup_fetch_error_${String(e?.message || e).slice(0, 80)}`;
            }
        }
        if (!moduleBlocked && rooms.length < 5) {
            moduleBlocked = true;
            blockedReason = `insufficient_rooms_${rooms.length}`;
            recFinding(testInfo, 'P2', MOD, 'Setup: stress oda havuzu yetersiz — module blocked',
                `rooms=${rooms.length} (en az 5 gerekli A–L için) — A/B/C/D/E/F/G/H/I/J/K/L skipped, M/N still enforced.`);
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} probes=${JSON.stringify(probes)} bookings=${bookings.length} rooms=${rooms.length} guests=${guests.length} pilot_before=${pilotBefore?.count} module_blocked=${moduleBlocked} reason=${blockedReason || 'reachable'}` });
        expect(typeof bookings.length).toBe('number');
    });

    // ────────────────────────────────────────────────────────────────────
    // A) Waitlist promote — endpoint contract probe
    // ────────────────────────────────────────────────────────────────────
    test('A) Waitlist promote (endpoint probe + REVIEW if absent)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'waitlist_promote', status: 'SKIP', note: `module_blocked=true (${blockedReason})` }); test.skip(); return; }
        // Reservation waitlist endpoint'i backend'de mount değil
        // (spa/waitlist mevcut ama bu rezervasyon kapsamında değil).
        // Doctrine: probe + REVIEW + P2 informational.
        const probe = await callTimed(request, 'get', '/api/waitlist',
            undefined, stressTokens.stress_token);
        const reachable = probe.ok || (probe.status >= 400 && probe.status < 500 && probe.status !== 404);
        const status = reachable ? 'PASS' : 'REVIEW';
        rec(testInfo, { module: MOD, step: 'waitlist_promote', status,
            endpoint: '/api/waitlist',
            note: `probe_status=${probe.status} reachable=${reachable} (404=endpoint not mounted; not a regression — REVIEW informational)` });
        if (!reachable) {
            recFinding(testInfo, 'P2', MOD, 'Waitlist endpoint mount yok',
                `GET /api/waitlist → ${probe.status}. Reservation waitlist promote yüzeyi henüz production'da değil; spec gelecekteki feature gate için iskelet bırakıyor.`);
        }
        await gap();
    });

    // ────────────────────────────────────────────────────────────────────
    // B) Option / hold create + status read
    // ────────────────────────────────────────────────────────────────────
    test('B) Booking hold create + status read (TTL contract)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'hold_create', status: 'SKIP' }); test.skip(); return; }
        if (rooms.length < 1) { rec(testInfo, { module: MOD, step: 'hold_create', status: 'SKIP', note: 'no rooms' }); return; }

        // Önce stress-tenant'ta kısa süreli bir reservation yarat — hold için
        // booking_id zorunlu (backend HoldCreateRequest).
        const room = rooms[0];
        const ts = Date.now();
        const checkIn = futureDateISO(200);
        const checkOut = futureDateISO(202);
        const seedR = await callTimed(request, 'post', '/api/pms/quick-booking', {
            room_id: room.id,
            guest_name: `${SUB_PREFIX}_Hold_${ts}`,
            check_in: checkIn,
            check_out: checkOut,
            total_amount: 1500,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('hold_seed') } });
        const bid = seedR.body?.id || seedR.body?.booking_id || seedR.body?.booking?.id;
        if (seedR.ok && bid) createdBookingIds.push(bid);
        if (!seedR.ok || !bid) {
            rec(testInfo, { module: MOD, step: 'hold_create', status: 'REVIEW',
                note: `seed booking fail status=${seedR.status} — hold path probe skipped` });
            recFinding(testInfo, 'P2', MOD, 'Hold seed booking başarısız',
                `Quick-booking ${seedR.status} döndü; hold yüzeyi test edilemedi.`);
            await gap();
            return;
        }
        await gap();

        // Create hold (TTL default).
        const holdR = await callTimed(request, 'post', '/api/booking-holds', {
            booking_id: bid,
            room_id: room.id,
            check_in: checkIn,
            check_out: checkOut,
            ttl_minutes: 5,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('hold_create') } });

        // Status read.
        const statusR = await callTimed(request, 'get',
            `/api/booking-holds/status?booking_id=${encodeURIComponent(bid)}`,
            undefined, stressTokens.stress_token);

        // Release (cleanup belt-and-suspenders).
        const releaseR = await callTimed(request, 'delete',
            `/api/booking-holds?booking_id=${encodeURIComponent(bid)}&reason=${encodeURIComponent(SUB_PREFIX + '_cleanup')}`,
            undefined, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('hold_release') } });

        const fiveXx = [holdR, statusR, releaseR].filter((r) => r.status >= 500).length;
        const allReachable = [holdR.status, statusR.status, releaseR.status].every((s) => s > 0 && s < 500);
        const status = fiveXx > 0 ? 'FAIL' : (allReachable ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'hold_create', status,
            endpoint: '/api/booking-holds (+/status, DELETE)',
            note: `hold=${holdR.status} status=${statusR.status} has_hold=${statusR.body?.has_hold} release=${releaseR.status} 5xx=${fiveXx}` });
        if (fiveXx > 0) recFinding(testInfo, 'P1', MOD, 'Hold TTL surface 5xx',
            `hold=${holdR.status} status=${statusR.status} release=${releaseR.status}`);
        await gap();
    });

    // ────────────────────────────────────────────────────────────────────
    // C) Overbooking oversell guard — duplicate reject
    // ────────────────────────────────────────────────────────────────────
    test('C) Overbooking oversell guard (duplicate booking reject)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'overbook_oversell', status: 'SKIP' }); test.skip(); return; }
        const candidate = bookings.find((b) => b.room_id && b.check_in && b.check_out && b.status === 'checked_in');
        if (!candidate) {
            rec(testInfo, { module: MOD, step: 'overbook_oversell', status: 'SKIP', note: 'no checked_in candidate' });
            return;
        }
        const checkR = await callTimed(request, 'get',
            `/api/pms-core/overbooking-check?room_id=${encodeURIComponent(candidate.room_id)}&check_in=${encodeURIComponent(candidate.check_in)}&check_out=${encodeURIComponent(candidate.check_out)}&exclude_booking_id=${encodeURIComponent(candidate.id)}`,
            undefined, stressTokens.stress_token);
        const hasConflict = checkR.body?.has_conflict === true;

        const ts = Date.now();
        const dupR = await callTimed(request, 'post', '/api/pms/quick-booking', {
            room_id: candidate.room_id,
            guest_name: `${SUB_PREFIX}_OversellAttempt_${ts}`,
            check_in: String(candidate.check_in).slice(0, 10),
            check_out: String(candidate.check_out).slice(0, 10),
            total_amount: 500,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('oversell_dup') } });
        const rejected = !dupR.ok && [400, 409, 422].includes(dupR.status);
        rec(testInfo, { module: MOD, step: 'overbook_oversell', status: rejected ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms/quick-booking (duplicate)',
            note: `check_status=${checkR.status} has_conflict=${hasConflict} dup_status=${dupR.status} rejected=${rejected}` });
        if (dupR.ok) {
            const dupId = dupR.body?.id || dupR.body?.booking_id || dupR.body?.booking?.id;
            if (dupId) createdBookingIds.push(dupId);
            recFinding(testInfo, 'P0', MOD, 'Oversell guard yok — duplicate booking yaratıldı',
                `room=${candidate.room_id} ${candidate.check_in}→${candidate.check_out} duplicate POST 2xx döndü.`);
        }
        await gap();
    });

    // ────────────────────────────────────────────────────────────────────
    // D) Overbooking yield guard — same-night second booking attempt for
    //    each room type sample (room_type-level conflict).
    // ────────────────────────────────────────────────────────────────────
    test('D) Overbooking yield guard (room-type sample probe)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'overbook_yield', status: 'SKIP' }); test.skip(); return; }
        // Stress seed checked_in bookings'ten 3 farklı oda için yield probe.
        const sample = bookings.filter((b) => b.room_id && b.check_in && b.check_out).slice(0, 3);
        if (sample.length === 0) { rec(testInfo, { module: MOD, step: 'overbook_yield', status: 'SKIP', note: 'no sample' }); return; }
        let conflicts = 0; let probed = 0;
        const samples = [];
        for (const b of sample) {
            const r = await callTimed(request, 'get',
                `/api/pms-core/overbooking-check?room_id=${encodeURIComponent(b.room_id)}&check_in=${encodeURIComponent(b.check_in)}&check_out=${encodeURIComponent(b.check_out)}`,
                undefined, stressTokens.stress_token);
            samples.push(r.ms);
            probed++;
            if (r.body?.has_conflict === true) conflicts++;
            await gap();
        }
        // Beklenti: 3/3 conflict (seed bookings checked_in, aynı tarih).
        const status = conflicts === probed ? 'PASS' : (conflicts > 0 ? 'REVIEW' : 'FAIL');
        recPerf(testInfo, MOD, 'overbook_yield', samples, conflicts > 0);
        rec(testInfo, { module: MOD, step: 'overbook_yield', status,
            endpoint: '/api/pms-core/overbooking-check',
            note: `probed=${probed} conflicts=${conflicts}` });
        if (status === 'FAIL') recFinding(testInfo, 'P1', MOD, 'Yield guard tetiklenmedi',
            `${probed} oda için existing checked_in booking varken has_conflict=false döndü.`);
    });

    // ────────────────────────────────────────────────────────────────────
    // E) Multi-room booking → partial cancel (3 oda yarat, 1 oda iptal)
    // ────────────────────────────────────────────────────────────────────
    test('E) Multi-room partial cancel (3 rooms → cancel 1, keep 2)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'multi_room_partial_cancel', status: 'SKIP' }); test.skip(); return; }
        if (rooms.length < 3) { rec(testInfo, { module: MOD, step: 'multi_room_partial_cancel', status: 'SKIP', note: 'rooms<3' }); return; }
        const ts = Date.now();
        const arrival = futureDateISO(220);
        const departure = futureDateISO(222);
        const pickRooms = rooms.slice(0, 3).map((r) => ({
            room_id: r.id, adults: 1, children: 0, guests_count: 1, total_amount: 1200,
        }));
        const mr = await callTimed(request, 'post', '/api/pms/bookings/multi-room', {
            guest: {
                name: `${SUB_PREFIX}_MRPartial_${ts}`,
                email: `mrpartial-${ts}@e2e-stress.example.com`,
                phone: '+905550000000',
                id_number: `E2EMRP${ts}`,
            },
            arrival_date: arrival,
            departure_date: departure,
            rooms: pickRooms,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('mr_partial') } });

        if (!mr.ok) {
            rec(testInfo, { module: MOD, step: 'multi_room_partial_cancel', status: 'REVIEW',
                endpoint: '/api/pms/bookings/multi-room',
                note: `multi-room create status=${mr.status} body=${JSON.stringify(mr.body).slice(0, 200)}` });
            recFinding(testInfo, 'P2', MOD, 'Multi-room create başarısız — partial cancel test edilemedi',
                `status=${mr.status}`);
            await gap();
            return;
        }
        // Architect-iter-1 fix #1: backend `/api/pms/bookings/multi-room`
        // doğrudan `created_bookings: list[Booking]` döner (object wrap YOK).
        // Önceki revizyon `mr.body.bookings` + `mr.body.group_booking_id`
        // bekliyordu → subBookings=[] her zaman → variant E sahte REVIEW.
        // Düzeltme: array body kabul et, group_booking_id'yi ilk booking'den
        // türet (her sub-booking aynı group_booking_id'i taşır).
        const subBookings = (Array.isArray(mr.body)
            ? mr.body
            : (mr.body?.bookings || mr.body?.created_bookings || [])
        ).filter((b) => b?.id);
        const gid = subBookings[0]?.group_booking_id || mr.body?.group_booking_id;
        if (gid) createdMultiRoomGroupIds.push(gid);
        for (const b of subBookings) createdBookingIds.push(b.id);
        await gap();

        // Partial cancel: ilk booking'i iptal et, 2 booking kalmalı.
        if (subBookings.length < 1) {
            rec(testInfo, { module: MOD, step: 'multi_room_partial_cancel', status: 'REVIEW',
                note: `no sub-bookings returned (body shape: ${Object.keys(mr.body || {}).join(',')})` });
            return;
        }
        const cancelTarget = subBookings[0].id;
        const cancelR = await callTimed(request, 'post', '/api/pms-core/cancel', {
            booking_id: cancelTarget,
            reason: `${SUB_PREFIX}_partial_cancel`,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('mr_cancel') } });
        await gap();

        const status = cancelR.ok ? 'PASS' : (cancelR.status >= 500 ? 'FAIL' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'multi_room_partial_cancel', status,
            endpoint: '/api/pms-core/cancel',
            note: `group_id=${gid ?? 'n/a'} sub_bookings=${subBookings.length} cancel_target=${cancelTarget} cancel_status=${cancelR.status} expected_remaining=${subBookings.length - 1}` });
        if (cancelR.status >= 500) recFinding(testInfo, 'P1', MOD, 'Partial cancel 5xx', `status=${cancelR.status}`);
    });

    // ────────────────────────────────────────────────────────────────────
    // F) Group rooming list batch (block + rooming-list upload)
    // ────────────────────────────────────────────────────────────────────
    test('F) Group rooming list batch upload', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'group_rooming_list', status: 'SKIP' }); test.skip(); return; }
        const ts = Date.now();
        const arrival = futureDateISO(240);
        const departure = futureDateISO(243);
        const blockR = await callTimed(request, 'post', '/api/pms/groups/create-block', {
            stress_prefix: `${SUB_PREFIX}_GroupBlock_${ts}`,
            group_name: `${SUB_PREFIX}_GroupBlock_${ts}`,
            block_code: `${SUB_PREFIX.slice(0, 8)}${ts.toString().slice(-6)}`,
            arrival_date: arrival,
            departure_date: departure,
            total_rooms: 3,
            group_rate: 1000,
            cutoff_date: futureDateISO(230),
            contact_person: `${SUB_PREFIX}_contact`,
            notes: 'F8N § 95 rooming-list batch test',
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('group_block') } });

        if (!blockR.ok) {
            rec(testInfo, { module: MOD, step: 'group_rooming_list', status: 'REVIEW',
                endpoint: '/api/pms/groups/create-block',
                note: `block create status=${blockR.status} body=${JSON.stringify(blockR.body).slice(0, 200)}` });
            recFinding(testInfo, 'P2', MOD, 'Group block create başarısız — rooming-list test edilemedi',
                `status=${blockR.status} (RBAC veya schema drift olabilir)`);
            await gap();
            return;
        }
        const blockId = blockR.body?.id || blockR.body?.block_id || blockR.body?.block?.id;
        if (blockId) createdGroupBlockIds.push(blockId);
        await gap();

        // Rooming-list batch upload (3 satır). Backend `room_type` araması yapıp
        // 'available' status'lu oda bulamazsa errors array'inde dönecek — bu
        // smoke için "endpoint reachable + non-5xx + structured response" yeter.
        const roomType = rooms[0]?.room_type || 'standard';
        const entries = [0, 1, 2].map((i) => ({
            guest_name: `${SUB_PREFIX}_RL_${ts}_${i}`,
            email: `rl-${ts}-${i}@e2e-stress.example.com`,
            phone: '+905550000000',
            room_type: roomType,
            check_in: arrival,
            check_out: departure,
            special_requests: `${SUB_PREFIX}_rl_${i}`,
        }));
        const rlR = await callTimed(request, 'post',
            `/api/pms/groups/rooming-list/${encodeURIComponent(blockId)}`,
            entries, stressTokens.stress_token,
            { headers: { 'Idempotency-Key': idemKey('group_rl') } });

        // Architect-iter-1 fix #4: backend rooming-list response her satırda
        // `booking_id` field'ı taşıyor (`id` DEĞİL). Önceki revizyon `b.id`
        // bekliyordu → cleanup tracker'a hiç giremiyordu. Hem `id` hem
        // `booking_id`'yi yakala (forward-compat).
        const created = rlR.body?.created_bookings || rlR.body?.bookings || [];
        for (const b of created) {
            const bbid = b?.booking_id || b?.id;
            if (bbid) createdBookingIds.push(bbid);
        }

        const fiveXx = rlR.status >= 500;
        const status = fiveXx ? 'FAIL' : (rlR.ok ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'group_rooming_list', status,
            endpoint: '/api/pms/groups/rooming-list/{block_id}',
            note: `block_id=${blockId ?? 'n/a'} entries=${entries.length} rl_status=${rlR.status} created=${created.length} errors=${(rlR.body?.errors || []).length}` });
        if (fiveXx) recFinding(testInfo, 'P1', MOD, 'Rooming-list 5xx', `status=${rlR.status}`);
        await gap();
    });

    // ────────────────────────────────────────────────────────────────────
    // G) Rate change after modification (PUT total_amount)
    // ────────────────────────────────────────────────────────────────────
    test('G) Rate change after modification', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'rate_change', status: 'SKIP' }); test.skip(); return; }
        if (createdBookingIds.length < 1) {
            rec(testInfo, { module: MOD, step: 'rate_change', status: 'SKIP', note: 'no created bookings' });
            return;
        }
        const bid = createdBookingIds[0];
        // İki ardışık PUT: önce tarihleri shift, sonra total_amount değişikliği.
        // Backend rate change'in fee/folio'ya yansımasını gözlemlemek için ardışık modify.
        const r1 = await callTimed(request, 'put', `/api/pms/bookings/${encodeURIComponent(bid)}`, {
            special_requests: `${SUB_PREFIX}_rate_modify_phase1`,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('rate_p1') } });
        await gap();
        const r2 = await callTimed(request, 'put', `/api/pms/bookings/${encodeURIComponent(bid)}`, {
            total_amount: 2750.50,
            special_requests: `${SUB_PREFIX}_rate_modify_phase2`,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('rate_p2') } });
        await gap();

        const fiveXx = [r1, r2].filter((r) => r.status >= 500).length;
        const status = fiveXx > 0 ? 'FAIL' : (r1.ok && r2.ok ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'rate_change', status,
            endpoint: '/api/pms/bookings/{id} (PUT × 2)',
            note: `p1=${r1.status} p2=${r2.status} 5xx=${fiveXx}` });
        if (fiveXx > 0) recFinding(testInfo, 'P1', MOD, 'Rate change PUT 5xx', `p1=${r1.status} p2=${r2.status}`);
    });

    // ────────────────────────────────────────────────────────────────────
    // H) Split reservation: orijinali kısalt, yeni leg yarat (5n → 2n + 3n)
    // ────────────────────────────────────────────────────────────────────
    test('H) Split reservation (5-night → 2 + 3)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'split_reservation', status: 'SKIP' }); test.skip(); return; }
        if (rooms.length < 1) { rec(testInfo, { module: MOD, step: 'split_reservation', status: 'SKIP' }); return; }
        const room = rooms[1] || rooms[0];
        const ts = Date.now();
        const checkIn = futureDateISO(260);
        const fullCheckOut = futureDateISO(265);   // 5 gece
        const splitPoint = futureDateISO(262);     // 2 gece sonrası

        // Adım 1: 5-gecelik booking yarat.
        const seedR = await callTimed(request, 'post', '/api/pms/quick-booking', {
            room_id: room.id,
            guest_name: `${SUB_PREFIX}_Split_${ts}`,
            check_in: checkIn,
            check_out: fullCheckOut,
            total_amount: 5000,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('split_seed') } });
        const bid = seedR.body?.id || seedR.body?.booking_id || seedR.body?.booking?.id;
        if (seedR.ok && bid) createdBookingIds.push(bid);
        if (!seedR.ok || !bid) {
            rec(testInfo, { module: MOD, step: 'split_reservation', status: 'REVIEW',
                note: `seed status=${seedR.status} — split test edilemedi` });
            recFinding(testInfo, 'P2', MOD, 'Split seed booking başarısız', `status=${seedR.status}`);
            return;
        }
        await gap();

        // Adım 2: orijinali 2 geceye kısalt (PUT check_out=splitPoint).
        const shrinkR = await callTimed(request, 'put', `/api/pms/bookings/${encodeURIComponent(bid)}`, {
            check_out: splitPoint,
            total_amount: 2000,
            special_requests: `${SUB_PREFIX}_split_phase1_shortened`,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('split_shrink') } });
        await gap();

        // Adım 3: ikinci leg yarat (splitPoint → fullCheckOut, 3 gece).
        const legR = await callTimed(request, 'post', '/api/pms/quick-booking', {
            room_id: room.id,
            guest_name: `${SUB_PREFIX}_Split_${ts}_leg2`,
            check_in: splitPoint,
            check_out: fullCheckOut,
            total_amount: 3000,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('split_leg2') } });
        const legBid = legR.body?.id || legR.body?.booking_id || legR.body?.booking?.id;
        if (legR.ok && legBid) createdBookingIds.push(legBid);
        await gap();

        const fiveXx = [seedR, shrinkR, legR].filter((r) => r.status >= 500).length;
        const status = fiveXx > 0 ? 'FAIL'
            : (shrinkR.ok && legR.ok ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'split_reservation', status,
            endpoint: '/api/pms/quick-booking + PUT /api/pms/bookings/{id}',
            note: `seed=${seedR.status} shrink=${shrinkR.status} leg2=${legR.status} 5xx=${fiveXx} leg2_body=${JSON.stringify(legR.body).slice(0, 120)}` });
        if (fiveXx > 0) recFinding(testInfo, 'P1', MOD, 'Split reservation 5xx',
            `seed=${seedR.status} shrink=${shrinkR.status} leg2=${legR.status}`);
    });

    // ────────────────────────────────────────────────────────────────────
    // I) Merge duplicate guest
    // ────────────────────────────────────────────────────────────────────
    test('I) Merge duplicate guest profiles', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'merge_guest', status: 'SKIP' }); test.skip(); return; }
        if (guests.length < 2) {
            rec(testInfo, { module: MOD, step: 'merge_guest', status: 'SKIP', note: `guests<2 (have ${guests.length})` });
            return;
        }
        const primary = guests[0];
        const duplicate = guests[1];
        if (!primary?.id || !duplicate?.id) {
            rec(testInfo, { module: MOD, step: 'merge_guest', status: 'SKIP', note: 'guest ids missing' });
            return;
        }
        // Architect-iter-1 fix #2: backend merge router prefix
        // `/api/cross-property` (cross_property.py:38). Önceki revizyon
        // `/api/guests/{id}/merge` çağırıyordu → her zaman 404 → sahte
        // REVIEW (gerçek merge yüzeyi hiç test edilmiyordu). Doğru path:
        // `/api/cross-property/guests/{primary_id}/merge`.
        const mergeR = await callTimed(request, 'post',
            `/api/cross-property/guests/${encodeURIComponent(primary.id)}/merge`, {
                target_guest_id: duplicate.id,
                keep_field_overrides: {},
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('merge') } });

        const fiveXx = mergeR.status >= 500;
        // 403 / 404 RBAC veya schema drift olabilir → REVIEW.
        const status = fiveXx ? 'FAIL'
            : (mergeR.ok ? 'PASS'
                : (mergeR.status === 403 || mergeR.status === 404 ? 'REVIEW' : 'REVIEW'));
        rec(testInfo, { module: MOD, step: 'merge_guest', status,
            endpoint: '/api/guests/{primary_id}/merge',
            note: `primary=${primary.id} duplicate=${duplicate.id} merge_status=${mergeR.status} body=${JSON.stringify(mergeR.body).slice(0, 160)}` });
        if (fiveXx) recFinding(testInfo, 'P1', MOD, 'Merge guest 5xx', `status=${mergeR.status}`);
        else if (mergeR.status === 403) recFinding(testInfo, 'P2', MOD,
            'Merge guest RBAC short-circuit',
            `Stress automation role manage_sales perm eksik (403). Beklenen — merge SUPER_ADMIN/ADMIN/SUPERVISOR sınırlı.`);
        await gap();
    });

    // ────────────────────────────────────────────────────────────────────
    // J) No-show fee dry-run + folio gözlem
    // ────────────────────────────────────────────────────────────────────
    test('J) No-show fee dry-run (folio charge gözlem)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'noshow_fee', status: 'SKIP' }); test.skip(); return; }
        if (rooms.length < 1) { rec(testInfo, { module: MOD, step: 'noshow_fee', status: 'SKIP' }); return; }
        // Confirmed booking yarat, no-show'a çevir, fee folio'da görünüyor mu?
        const room = rooms[2] || rooms[0];
        const ts = Date.now();
        const seedR = await callTimed(request, 'post', '/api/pms/quick-booking', {
            room_id: room.id,
            guest_name: `${SUB_PREFIX}_NoShowFee_${ts}`,
            check_in: futureDateISO(280),
            check_out: futureDateISO(281),
            total_amount: 1800,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('nsfee_seed') } });
        const bid = seedR.body?.id || seedR.body?.booking_id || seedR.body?.booking?.id;
        if (seedR.ok && bid) createdBookingIds.push(bid);
        if (!seedR.ok || !bid) {
            rec(testInfo, { module: MOD, step: 'noshow_fee', status: 'REVIEW',
                note: `seed status=${seedR.status}` });
            recFinding(testInfo, 'P2', MOD, 'No-show fee seed başarısız', `status=${seedR.status}`);
            return;
        }
        await gap();

        const nsR = await callTimed(request, 'post', '/api/pms-core/no-show', {
            booking_id: bid,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('nsfee_apply') } });
        await gap();

        // Folio okuma — booking'in folio'sunda no_show_fee charge tipi var mı?
        // Backend frontdesk_service_v2 no_show_fee charge_type'ı ekler.
        // Folio listesi: /api/pms/folios?booking_id=...
        let feeObserved = null;
        const folioR = await callTimed(request, 'get',
            `/api/pms/folios?booking_id=${encodeURIComponent(bid)}`,
            undefined, stressTokens.stress_token);
        if (folioR.ok) {
            const folios = Array.isArray(folioR.body) ? folioR.body
                : (folioR.body?.folios || folioR.body?.items || []);
            const folioBody = JSON.stringify(folios).toLowerCase();
            feeObserved = folioBody.includes('no_show_fee') || folioBody.includes('no-show');
        }

        const fiveXx = [nsR, folioR].filter((r) => r.status >= 500).length;
        const status = fiveXx > 0 ? 'FAIL' : (nsR.ok ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'noshow_fee', status,
            endpoint: '/api/pms-core/no-show + /api/pms/folios?booking_id=...',
            note: `ns_status=${nsR.status} folio_status=${folioR.status} fee_observed=${feeObserved} (informational — fee logic policy/threshold'a bağlı olabilir)` });
        if (fiveXx > 0) recFinding(testInfo, 'P1', MOD, 'No-show fee 5xx',
            `ns=${nsR.status} folio=${folioR.status}`);
    });

    // ────────────────────────────────────────────────────────────────────
    // K) Cancellation policy fee tier'ları
    // ────────────────────────────────────────────────────────────────────
    test('K) Cancellation policy fee tier observation', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'cancel_fee_tier', status: 'SKIP' }); test.skip(); return; }
        if (rooms.length < 3) { rec(testInfo, { module: MOD, step: 'cancel_fee_tier', status: 'SKIP' }); return; }
        // Üç farklı lead-time için cancel: late (<24h), medium (~7d), early (>14d).
        // Backend cancellation policy lead-time threshold'larına göre fee uygulayabilir.
        const tiers = [
            { name: 'late', days: 1 },
            { name: 'medium', days: 7 },
            { name: 'early', days: 21 },
        ];
        const results = [];
        for (let i = 0; i < tiers.length; i++) {
            const t = tiers[i];
            const room = rooms[3 + i] || rooms[i];
            const ts = Date.now();
            const seedR = await callTimed(request, 'post', '/api/pms/quick-booking', {
                room_id: room.id,
                guest_name: `${SUB_PREFIX}_CancelTier_${t.name}_${ts}`,
                check_in: futureDateISO(300 + t.days),
                check_out: futureDateISO(301 + t.days),
                total_amount: 1600,
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey(`tier_seed_${t.name}`, i) } });
            const bid = seedR.body?.id || seedR.body?.booking_id || seedR.body?.booking?.id;
            if (seedR.ok && bid) createdBookingIds.push(bid);
            await gap();
            if (!seedR.ok || !bid) {
                results.push({ tier: t.name, seed_status: seedR.status, cancel_status: 'n/a' });
                continue;
            }
            const cancelR = await callTimed(request, 'post', '/api/pms-core/cancel', {
                booking_id: bid,
                reason: `${SUB_PREFIX}_tier_${t.name}`,
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey(`tier_cancel_${t.name}`, i) } });
            results.push({ tier: t.name, seed_status: seedR.status, cancel_status: cancelR.status });
            await gap();
        }
        const fiveXx = results.filter((r) => r.cancel_status >= 500).length;
        const cancelOks = results.filter((r) => r.cancel_status >= 200 && r.cancel_status < 300).length;
        const status = fiveXx > 0 ? 'FAIL' : (cancelOks >= 1 ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'cancel_fee_tier', status,
            endpoint: '/api/pms-core/cancel (× lead-time tiers)',
            note: `tiers=${JSON.stringify(results)} cancel_oks=${cancelOks}/${tiers.length} 5xx=${fiveXx}` });
        if (fiveXx > 0) recFinding(testInfo, 'P1', MOD, 'Cancel tier 5xx', `results=${JSON.stringify(results)}`);
    });

    // ────────────────────────────────────────────────────────────────────
    // L) City ledger transfer dry-run
    // ────────────────────────────────────────────────────────────────────
    test('L) City ledger transfer dry-run', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { rec(testInfo, { module: MOD, step: 'city_ledger_transfer', status: 'SKIP' }); test.skip(); return; }
        // Stress tenant'ta açık bir folio + city ledger account ID'leri lazım.
        // İlk açık folio'yu bul.
        const folioListR = await callTimed(request, 'get',
            '/api/pms/folios?status=open&limit=20',
            undefined, stressTokens.stress_token);
        const folios = folioListR.ok
            ? (Array.isArray(folioListR.body) ? folioListR.body
                : (folioListR.body?.folios || folioListR.body?.items || []))
            : [];
        const openFolio = folios.find((f) => f?.id);

        // City ledger account ID'sini cashiering listesinden çek.
        const accListR = await callTimed(request, 'get',
            '/api/cashiering/city-ledger',
            undefined, stressTokens.stress_token);
        const accounts = accListR.ok
            ? (Array.isArray(accListR.body) ? accListR.body
                : (accListR.body?.accounts || accListR.body?.items || []))
            : [];
        const account = accounts.find((a) => a?.id);

        if (!openFolio || !account) {
            rec(testInfo, { module: MOD, step: 'city_ledger_transfer', status: 'SKIP',
                endpoint: '/api/pms-core/folio/city-ledger-transfer',
                note: `folios_ok=${folioListR.ok}(${folioListR.status}) folios=${folios.length} accounts_ok=${accListR.ok}(${accListR.status}) accounts=${accounts.length} — pre-req unavailable` });
            recFinding(testInfo, 'P2', MOD, 'City ledger transfer pre-req yok',
                `Open folio veya city-ledger account stress-tenant'ta seed edilmemiş; smoke skipped.`);
            return;
        }
        const transferR = await callTimed(request, 'post',
            '/api/pms-core/folio/city-ledger-transfer', {
                folio_id: openFolio.id,
                account_id: account.id,
                reason: `${SUB_PREFIX}_cl_transfer`,
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey('cl_transfer') } });

        const fiveXx = transferR.status >= 500;
        const status = fiveXx ? 'FAIL'
            : (transferR.ok ? 'PASS'
                : (transferR.status === 400 || transferR.status === 403 ? 'REVIEW' : 'REVIEW'));
        rec(testInfo, { module: MOD, step: 'city_ledger_transfer', status,
            endpoint: '/api/pms-core/folio/city-ledger-transfer',
            note: `folio=${openFolio.id} account=${account.id} transfer_status=${transferR.status} body=${JSON.stringify(transferR.body).slice(0, 200)}` });
        if (fiveXx) recFinding(testInfo, 'P1', MOD, 'City ledger transfer 5xx', `status=${transferR.status}`);
        else if (transferR.status === 403) recFinding(testInfo, 'P2', MOD,
            'City ledger transfer RBAC short-circuit',
            `close_folio perm gate (403); beklenen RBAC davranışı.`);
        await gap();
    });

    // ────────────────────────────────────────────────────────────────────
    // M) External calls invariant — final batch verdict
    // ────────────────────────────────────────────────────────────────────
    test('M) External calls invariant after deep lifecycle batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(testInfo, MOD,
            'reservation_deep_full', stressState, request, stressTokens.pilot_token);
        expect(ok, 'F8N reservation_deep batch sonrası external_calls invariant ihlal').toBe(true);
    });

    // ────────────────────────────────────────────────────────────────────
    // N) Pilot drift = 0 — final tenant isolation gate
    // ────────────────────────────────────────────────────────────────────
    test('N) Pilot drift = 0 (tenant isolation final gate)', async ({ request, stressTokens }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD,
            request, stressTokens.pilot_token, pilotBefore);
        // Ek doğrudan sayım — assertPilotDriftZero zaten finding üretir,
        // fakat created-id tracker tarafından da pilot leak'i ayrı görmek istiyoruz.
        if (pilotBefore) {
            const after = await pilotBookingsCount(request, stressTokens.pilot_token);
            const drift = (after?.count ?? 0) - pilotBefore.count;
            rec(testInfo, { module: MOD, step: 'pilot_drift_summary',
                status: drift === 0 ? 'PASS' : 'FAIL',
                note: `pilot before=${pilotBefore.count} after=${after?.count} drift=${drift} created_in_stress=${createdBookingIds.length} group_blocks=${createdGroupBlockIds.length} mr_groups=${createdMultiRoomGroupIds.length}` });
            if (drift !== 0) {
                recFinding(testInfo, 'P0', MOD, 'Pilot mutation tespit edildi',
                    `drift=${drift} — F8N spec stress-tenant scope; pilot booking sayısı sabit kalmalıydı.`);
            }
        }
        expect(driftOk, 'F8N pilot drift invariant ihlal').toBe(true);
    });
});

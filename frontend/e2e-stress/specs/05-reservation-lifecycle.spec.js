// F8A § 05 — Reservation lifecycle deep:
//   create → modify → cancel → no-show → overbooking-check → group-reservation → multi-room.
//
// Tasarım notları:
// - Bu spec STRESS_TEST_ROADMAP "F8A v2 backlog" maddelerini kapatır
//   (reservation create/modify/cancel batch, no-show conversion, overbooking
//   guard, group bookings, multi-room reservation).
// - Mevcut F8A specs (02 day-turnover, 03 room-move, 04 folio-mass)
//   "checked_in" booking üzerinde mass-mutation yapıyor; bu spec lifecycle'ın
//   ÖNCE-checked-in yarısını test eder (pending → confirmed → cancel/no-show).
// - Cancel ve no-show için *bu spec içinde yarattığımız bookings*'i kullanıyoruz
//   (state machine `confirmed → cancelled/no_show` geçişlerine izin verir).
//   Stress seed `checked_in` bookings'ine no-show yapmak state error.
// - Quick-booking endpoint (/api/pms/quick-booking) tercih edildi — minimal
//   payload (guest_name + check_in + check_out + room_id + total_amount).
// - Future dates (+60..+90 gün): mevcut seed bookings ile çakışma yok →
//   create batch deterministik ok bekleniyor.
// - Throttle: 800ms gap (400ms charge'tan ağır, 1500ms split'ten hafif).
// - Sample size'lar küçük (10/10/5/5) — bu lifecycle smoke, yük testi değil.
import { randomUUID as cryptoRandomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import { fetchAllByPrefix, callTimed, recPerf, recFinding, pilotBookingsCount, assertNoExternalCallsPostBatch } from '../fixtures/stress-helpers.js';

const MOD = 'reservation-lifecycle';

test.describe.configure({ mode: 'serial' });

test.describe('F8A § 05 — Reservation lifecycle (create / modify / cancel / no-show / overbooking / group / multi-room)', () => {
    let bookings = [];
    let rooms = [];
    let pilotBefore = null;
    // Bu spec içinde yaratılan booking ID'leri — B/C/D test'leri bunları hedefler.
    const createdBookingIds = [];
    const createdGroupIds = [];
    const createdMultiRoomGroupIds = [];

    // Stress prefix'i bu spec için sub-prefix ile zenginleştiriyoruz; cleanup
    // ana stress_prefix'i query ettiği için yine yakalanır.
    const SUB_PREFIX = 'F8A_LIFECYCLE';

    function futureDateISO(daysFromNow) {
        const d = new Date();
        d.setUTCDate(d.getUTCDate() + daysFromNow);
        return d.toISOString().slice(0, 10); // YYYY-MM-DD
    }

    test('Setup: stress bookings + rooms snapshot + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        const prefix = stressState.data_prefix;
        bookings = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/bookings', 'stress_prefix', prefix);
        rooms = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/rooms', 'stress_prefix', prefix);
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `bookings=${bookings.length} rooms=${rooms.length} pilot_before=${pilotBefore?.count} sub_prefix=${SUB_PREFIX}` });
        expect(rooms.length, 'Setup: stress room havuzu boş — seed eksik').toBeGreaterThan(0);
    });

    test('A) 10 reservation create (future dates, quick-booking)', async ({ request, stressTokens }, testInfo) => {
        // Future dates: +60..+89 gün (her booking 1 gece, 30 gün aralığa dağıt).
        // Mevcut seed bookings'le çakışma yok → her create deterministik ok bekleniyor.
        if (rooms.length < 10) { rec(testInfo, { module: MOD, step: 'create_sample', status: 'SKIP', note: `only ${rooms.length} rooms` }); return; }
        const sample = rooms.slice(0, 10);
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        // tur-27 (CI #42 NO-GO follow-up): earlier run hard-FAIL'di
        // (`n=10 ok=0`) ama fail_modes assert error'da DEĞİLDİ — root cause
        // görünmüyordu. Şimdi: ilk hatalı response body'sini snapshot al
        // (truncated 300 char) + fail_modes assertion message'a dahil et.
        // RBAC/module-blocked (403/404) → REVIEW pattern (F8C/D/E doctrine).
        let firstFailBody = null;
        let firstFailStatus = null;
        for (let i = 0; i < sample.length; i++) {
            const room = sample[i];
            const ts = Date.now();
            const checkIn = futureDateISO(60 + (i * 3));
            const checkOut = futureDateISO(61 + (i * 3));
            // tur-27b (CI #43 NO-GO follow-up): backend `/pms/quick-booking`
            // → `create_reservation_service.create()` artık Idempotency-Key
            // header'ı ZORUNLU kılıyor (CI #43 root cause: `400 Missing
            // Idempotency-Key header`). Her POST için unique key üret —
            // retry idempotency garantili olur (aynı key + aynı payload =
            // aynı booking) ama her i için yeni booking yaratmak istiyoruz,
            // o yüzden `${SUB_PREFIX}_${ts}_${i}_${randomUUID}` deterministic
            // ama tekil. crypto.randomUUID() Node 14.17+ built-in.
            const idemKey = `${SUB_PREFIX}_create_${ts}_${i}_${cryptoRandomUUID()}`;
            const r = await callTimed(request, 'post', '/api/pms/quick-booking', {
                room_id: room.id,
                guest_name: `${SUB_PREFIX}_Create_${ts}_${i}`,
                check_in: checkIn,
                check_out: checkOut,
                total_amount: 1000 + i * 50,
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey } });
            samples.push(r.ms);
            if (r.ok) {
                ok++;
                // Quick-booking response: { id, booking, booking_id, guest_name, ... }
                const bid = r.body?.id || r.body?.booking_id || r.body?.booking?.id;
                if (bid) createdBookingIds.push(bid);
            } else {
                fail++;
                const k = `s${r.status}`;
                failModes[k] = (failModes[k] || 0) + 1;
                if (firstFailBody == null) {
                    firstFailStatus = r.status;
                    firstFailBody = JSON.stringify(r.body || {}).slice(0, 300);
                }
            }
            await new Promise((res) => setTimeout(res, 800));
        }
        // tur-27: classify all-failure modes — RBAC/module-blocked patterns
        // REVIEW (F8C/D/E doctrine), structural FAIL korunur (s400/s500/s422
        // = data contract / validation regression).
        const all403 = fail > 0 && ok === 0 && failModes.s403 === sample.length;
        const all404 = fail > 0 && ok === 0 && failModes.s404 === sample.length;
        const allModBlocked = all403 || all404;
        const status = allModBlocked
            ? 'REVIEW'
            : (ok === 0 ? 'FAIL' : (ok >= 7 ? 'PASS' : 'REVIEW'));
        rec(testInfo, { module: MOD, step: 'reservation_create', status,
            endpoint: '/api/pms/quick-booking',
            note: `n=${sample.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)} ` +
                  `all_403=${all403} all_404=${all404} created_ids_captured=${createdBookingIds.length} ` +
                  `first_fail_status=${firstFailStatus ?? 'n/a'} first_fail_body=${firstFailBody ?? 'n/a'}` });
        recPerf(testInfo, MOD, 'reservation_create', samples, ok > 0);
        if (allModBlocked) {
            recFinding(testInfo, 'P2', MOD,
                'Reservation create RBAC/module-blocked short-circuit',
                `Stress automation token quick-booking erişim yok (${all403 ? '403' : '404'} all-fail). ` +
                'F8C/D/E module-blocked doctrine: A test informational kalır, B/C/D/E/F/G/H/I downstream test\'leri skip cascade beklenir.');
        }
        if (ok === 0 && !allModBlocked) {
            recFinding(testInfo, 'P1', MOD, 'Reservation create lifecycle başarısız',
                `${sample.length} quick-booking POST 0 başarı. Modes: ${JSON.stringify(failModes)}. ` +
                `First fail: status=${firstFailStatus} body=${firstFailBody}. Future date çakışmaması bekleniyordu.`);
        }
        expect(status, `reservation_create FAIL: n=${sample.length} ok=${ok} fail_modes=${JSON.stringify(failModes)} ` +
            `first_fail=${firstFailStatus} body=${firstFailBody}`).not.toBe('FAIL');
    });

    test('B) 5 modify dates (PUT booking)', async ({ request, stressTokens }, testInfo) => {
        // A'da yaratılan bookings'in tarihlerini +1 gün shift et.
        if (createdBookingIds.length < 5) { rec(testInfo, { module: MOD, step: 'modify_sample', status: 'SKIP', note: `only ${createdBookingIds.length} created bookings` }); return; }
        const sample = createdBookingIds.slice(0, 5);
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        for (let i = 0; i < sample.length; i++) {
            const bid = sample[i];
            // Shift dates +1 gün — overbook olmayacak (yeni tarihte de boş).
            const newCheckIn = futureDateISO(120 + (i * 3));
            const newCheckOut = futureDateISO(121 + (i * 3));
            // tur-27b: Idempotency-Key proactive (Asher A pattern parity).
            const idemKey = `${SUB_PREFIX}_modify_${bid}_${cryptoRandomUUID()}`;
            const r = await callTimed(request, 'put', `/api/pms/bookings/${bid}`, {
                check_in: newCheckIn,
                check_out: newCheckOut,
                special_requests: `${SUB_PREFIX}_modified_${i}`,
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey } });
            samples.push(r.ms);
            if (r.ok) ok++;
            else { fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            await new Promise((res) => setTimeout(res, 800));
        }
        const status = ok === 0 ? 'FAIL' : (ok >= 3 ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'reservation_modify', status,
            endpoint: '/api/pms/bookings/{id}',
            note: `n=${sample.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)}` });
        recPerf(testInfo, MOD, 'reservation_modify', samples, ok > 0);
        expect(status, `reservation_modify FAIL: n=${sample.length} ok=${ok}`).not.toBe('FAIL');
    });

    test('C) 5 cancel', async ({ request, stressTokens }, testInfo) => {
        // Modify yapılmamış created bookings'i cancel et (5..10 arası).
        if (createdBookingIds.length < 6) { rec(testInfo, { module: MOD, step: 'cancel_sample', status: 'SKIP', note: `only ${createdBookingIds.length}` }); return; }
        const sample = createdBookingIds.slice(5, Math.min(10, createdBookingIds.length));
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        for (const bid of sample) {
            // tur-27b: Idempotency-Key proactive.
            const idemKey = `${SUB_PREFIX}_cancel_${bid}_${cryptoRandomUUID()}`;
            const r = await callTimed(request, 'post', '/api/pms-core/cancel', {
                booking_id: bid,
                reason: `${SUB_PREFIX}_cancel_test`,
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey } });
            samples.push(r.ms);
            if (r.ok) ok++;
            else { fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            await new Promise((res) => setTimeout(res, 800));
        }
        const status = ok === 0 ? 'FAIL' : (ok >= 3 ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'reservation_cancel', status,
            endpoint: '/api/pms-core/cancel',
            note: `n=${sample.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)}` });
        recPerf(testInfo, MOD, 'reservation_cancel', samples, ok > 0);
        expect(status, `reservation_cancel FAIL: n=${sample.length} ok=${ok}`).not.toBe('FAIL');
    });

    test('D) 3 no-show conversion', async ({ request, stressTokens }, testInfo) => {
        // No-show için ek bookings yarat (status=confirmed) → no-show çevir.
        // Stress seed bookings'i checked_in olduğu için state-machine reject ederdi.
        if (rooms.length < 3) { rec(testInfo, { module: MOD, step: 'noshow_setup', status: 'SKIP' }); return; }
        const noShowSample = [];
        for (let i = 0; i < 3; i++) {
            const ts = Date.now();
            const room = rooms[10 + i] || rooms[i];
            // tur-27b: Idempotency-Key proactive.
            const idemKey = `${SUB_PREFIX}_noshow_seed_${ts}_${i}_${cryptoRandomUUID()}`;
            const r = await callTimed(request, 'post', '/api/pms/quick-booking', {
                room_id: room.id,
                guest_name: `${SUB_PREFIX}_NoShow_${ts}_${i}`,
                check_in: futureDateISO(180 + i),
                check_out: futureDateISO(181 + i),
                total_amount: 800,
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey } });
            if (r.ok) {
                const bid = r.body?.id || r.body?.booking_id || r.body?.booking?.id;
                if (bid) noShowSample.push(bid);
            }
            await new Promise((res) => setTimeout(res, 800));
        }
        if (noShowSample.length < 1) {
            rec(testInfo, { module: MOD, step: 'noshow_conversion', status: 'SKIP', note: 'pre-create yetersiz' });
            return;
        }
        let ok = 0, fail = 0; const failModes = {};
        const samples = [];
        for (const bid of noShowSample) {
            // tur-27b: Idempotency-Key proactive.
            const idemKey = `${SUB_PREFIX}_noshow_${bid}_${cryptoRandomUUID()}`;
            const r = await callTimed(request, 'post', '/api/pms-core/no-show', {
                booking_id: bid,
            }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey } });
            samples.push(r.ms);
            if (r.ok) ok++;
            else { fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            await new Promise((res) => setTimeout(res, 800));
        }
        const status = ok === 0 ? 'FAIL' : (ok >= 1 ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'noshow_conversion', status,
            endpoint: '/api/pms-core/no-show',
            note: `n=${noShowSample.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)}` });
        recPerf(testInfo, MOD, 'noshow_conversion', samples, ok > 0);
        if (ok === 0) {
            recFinding(testInfo, 'P1', MOD, 'No-show conversion akışı başarısız',
                `${noShowSample.length} no-show denemesi 0 başarı. Modes: ${JSON.stringify(failModes)}. State machine confirmed→no_show geçişine izin vermeli.`);
        }
        expect(status, `noshow_conversion FAIL: ok=${ok} fail_modes=${JSON.stringify(failModes)}`).not.toBe('FAIL');
    });

    test('E) Overbooking guard: aynı oda + dolu tarih → conflict tespit', async ({ request, stressTokens }, testInfo) => {
        // Stress seed checked_in bookings'inden bir tanesi için overbooking-check
        // → conflict raporlanmalı (mevcut booking var).
        // İkinci aşama: aynı oda + aynı tarih için quick-booking POST → reject bekle.
        const candidate = bookings.find((b) => b.room_id && b.check_in && b.check_out);
        if (!candidate) { rec(testInfo, { module: MOD, step: 'overbook_setup', status: 'SKIP', note: 'no candidate booking' }); return; }

        // 1. Pozitif overbooking-check: conflict raporlanmalı.
        const checkR = await callTimed(request, 'get',
            `/api/pms-core/overbooking-check?room_id=${encodeURIComponent(candidate.room_id)}&check_in=${encodeURIComponent(candidate.check_in)}&check_out=${encodeURIComponent(candidate.check_out)}&exclude_booking_id=${encodeURIComponent(candidate.id)}`,
            undefined, stressTokens.stress_token);
        const hasConflict = checkR.body?.has_conflict === true;
        rec(testInfo, { module: MOD, step: 'overbook_check_positive', status: hasConflict ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/overbooking-check',
            note: `status=${checkR.status} has_conflict=${checkR.body?.has_conflict} conflicts_len=${(checkR.body?.conflicts || []).length}` });

        // 2. Negatif POST: duplicate booking attempt → reject bekle (400/409/422).
        const ts = Date.now();
        // tur-27b: Idempotency-Key proactive (overbooking attempt is itself
        // a mutation POST; backend reject ETMEDEN ÖNCE header validate ediyor
        // → 400 Missing Idempotency-Key bizim conflict guard testimizi maskler).
        const dupIdemKey = `${SUB_PREFIX}_overbook_dup_${ts}_${cryptoRandomUUID()}`;
        const dupR = await callTimed(request, 'post', '/api/pms/quick-booking', {
            room_id: candidate.room_id,
            guest_name: `${SUB_PREFIX}_OverbookAttempt_${ts}`,
            check_in: candidate.check_in.slice(0, 10),
            check_out: candidate.check_out.slice(0, 10),
            total_amount: 500,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': dupIdemKey } });
        const rejected = !dupR.ok && [400, 409, 422].includes(dupR.status);
        rec(testInfo, { module: MOD, step: 'overbook_post_reject', status: rejected ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms/quick-booking',
            note: `status=${dupR.status} rejected=${rejected} (expected 400/409/422; got body=${JSON.stringify(dupR.body).slice(0, 200)})` });
        if (dupR.ok) {
            // Eğer 2xx döndüyse → double-booking yaratılmış olabilir (P0 risk).
            recFinding(testInfo, 'P0', MOD, 'Overbooking guard yok — duplicate booking yaratıldı',
                `Aynı room_id (${candidate.room_id}) + aynı tarih (${candidate.check_in}→${candidate.check_out}) için POST 2xx döndü. Çift rezervasyon riski.`);
            // Yaratılan booking'i created listeye ekle ki cleanup yakalasın.
            const dupId = dupR.body?.id || dupR.body?.booking_id || dupR.body?.booking?.id;
            if (dupId) createdBookingIds.push(dupId);
        }
    });

    test('F) Group reservation create', async ({ request, stressTokens }, testInfo) => {
        const ts = Date.now();
        // tur-27b: Idempotency-Key proactive.
        const idemKey = `${SUB_PREFIX}_group_${ts}_${cryptoRandomUUID()}`;
        const r = await callTimed(request, 'post', '/api/pms/group-reservations', {
            stress_prefix: `${SUB_PREFIX}_Group_${ts}`,
            group_name: `${SUB_PREFIX}_Group_${ts}`,
            arrival_date: futureDateISO(60),
            departure_date: futureDateISO(62),
            total_rooms: 5,
            contact_person: `${SUB_PREFIX}_contact`,
            notes: 'F8A § 05 group test',
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey } });
        const status = r.ok ? 'PASS' : 'REVIEW';
        rec(testInfo, { module: MOD, step: 'group_reservation_create', status,
            endpoint: '/api/pms/group-reservations',
            note: `status=${r.status} group_id=${r.body?.id ?? 'n/a'}` });
        if (r.ok && r.body?.id) createdGroupIds.push(r.body.id);
    });

    test('G) Multi-room booking (1 guest, 3 rooms)', async ({ request, stressTokens }, testInfo) => {
        if (rooms.length < 3) { rec(testInfo, { module: MOD, step: 'multiroom_sample', status: 'SKIP' }); return; }
        const ts = Date.now();
        // Future date — mevcut seed ile çakışmasın.
        const arrival = futureDateISO(100);
        const departure = futureDateISO(102);
        // Pick 3 rooms farklı oda ID'leriyle.
        const pickRooms = rooms.slice(20, 23).map((r) => ({
            room_id: r.id,
            adults: 1,
            children: 0,
            guests_count: 1,
            total_amount: 1500,
        }));
        // tur-27b: Idempotency-Key proactive (multi-room booking gerektirir).
        const idemKey = `${SUB_PREFIX}_multiroom_${ts}_${cryptoRandomUUID()}`;
        const r = await callTimed(request, 'post', '/api/pms/bookings/multi-room', {
            guest: {
                name: `${SUB_PREFIX}_MultiRoom_${ts}`,
                email: `multiroom-${ts}@e2e-stress.example.com`,
                phone: '+905550000000',
                id_number: `E2EMR${ts}`,
            },
            arrival_date: arrival,
            departure_date: departure,
            rooms: pickRooms,
        }, stressTokens.stress_token, { headers: { 'Idempotency-Key': idemKey } });
        const status = r.ok ? 'PASS' : 'REVIEW';
        rec(testInfo, { module: MOD, step: 'multi_room_booking_create', status,
            endpoint: '/api/pms/bookings/multi-room',
            note: `status=${r.status} rooms_requested=${pickRooms.length} group_id=${r.body?.group_booking_id ?? r.body?.id ?? 'n/a'} bookings_created=${(r.body?.bookings || []).length}` });
        if (r.ok) {
            const gid = r.body?.group_booking_id;
            if (gid) createdMultiRoomGroupIds.push(gid);
            // Her sub-booking ID'sini de cleanup için yakala.
            for (const b of (r.body?.bookings || [])) {
                if (b?.id) createdBookingIds.push(b.id);
            }
        }
    });

    test('H) External calls invariant after lifecycle batch', async ({ request, stressTokens, stressState }, testInfo) => {
        const ok = await assertNoExternalCallsPostBatch(testInfo, MOD, 'reservation_lifecycle_full', stressState, request, stressTokens.pilot_token);
        expect(ok, 'Reservation lifecycle batch sonrası external_calls invariant ihlal').toBe(true);
    });

    test('I) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `pilot bookings before=${pilotBefore.count} after=${after?.count} drift=${drift} created_in_stress=${createdBookingIds.length} groups=${createdGroupIds.length} multi_room_groups=${createdMultiRoomGroupIds.length}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});

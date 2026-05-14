// F8A § 03 — Room move: positive (hedef boş), negative (hedef occupied / OOO), race.
//
// Stress dataset 500/500 occupied başlıyor. Pozitif move için önce hedefi boşaltmak gerekir.
// Bu spec 02-day-turnover'dan SONRA çalışırsa pozitif move başarısı yüksek olur (forced
// checkout sonrası boş odalar). Sırayla koştuğu için fixture order garanti.
import { test, expect, rec } from '../fixtures/stress-context.js';
import { fetchAllByPrefix, callTimed, recPerf, recFinding, pilotBookingsCount, assertNoExternalCallsPostBatch } from '../fixtures/stress-helpers.js';

const MOD = 'room-move';

test.describe.configure({ mode: 'serial' });

test.describe('F8A § 03 — Room move (positive + negative + race)', () => {
    let bookings = [];
    let rooms = [];
    let pilotBefore = null;

    test('Setup: stress bookings + rooms snapshot', async ({ request, stressTokens, stressState }, testInfo) => {
        const prefix = stressState.data_prefix;
        bookings = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/bookings', 'stress_prefix', prefix);
        rooms = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/rooms', 'stress_prefix', prefix);
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `bookings=${bookings.length} rooms=${rooms.length} pilot_before=${pilotBefore?.count}` });
    });

    test('A) Positive room-move: 50 (booking → vacant + same-category target) + post-move state transfer', async ({ request, stressTokens, stressState }, testInfo) => {
        // Brief contract: 50 positive move attempts (architect tur-3: 30 yetersiz).
        // Architect tur-5: hedef oda ZORUNLU olarak (a) boş ve (b) aynı kategori olmalı.
        // Eskiden `rooms.find(r.id !== b.room_id)` herhangi farklı oda alıyordu →
        // dolu/farklı-kategori hedeflere reject normalleşiyordu, gerçek pozitif test değildi.
        const checkedIn = bookings.filter((b) => b.status === 'checked_in');
        if (checkedIn.length < 5) {
            rec(testInfo, { module: MOD, step: 'positive_move_sample', status: 'SKIP',
                note: `checked_in=${checkedIn.length} (önceki spec hepsini checkout etmiş olabilir)` });
            return;
        }
        // Vacant set: room id'leri ki HİÇBİR checked_in booking onları işgal etmiyor.
        const occupiedRoomIds = new Set(checkedIn.map((b) => b.room_id).filter(Boolean));
        const vacantRooms = rooms.filter((r) => !occupiedRoomIds.has(r.id));
        // Same-category map: room_type → vacant rooms list.
        const vacantByType = new Map();
        for (const vr of vacantRooms) {
            const t = vr.room_type || vr.category || '__unknown__';
            if (!vacantByType.has(t)) vacantByType.set(t, []);
            vacantByType.get(t).push(vr);
        }
        const target = checkedIn.slice(0, 50);
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        let skippedNoTarget = 0;
        const moveLog = []; // { booking_id, old_room_id, new_room_id, target_room_type }
        for (let i = 0; i < target.length; i++) {
            const b = target[i];
            const bType = b.room_type || b.category || '__unknown__';
            const pool = vacantByType.get(bType);
            const candidate = (pool && pool.length > 0) ? pool.shift() : null;
            if (!candidate) { skippedNoTarget++; continue; }
            const r = await callTimed(request, 'post', '/api/pms-core/room-move', {
                booking_id: b.id, new_room_id: candidate.id, reason: `F8A positive move ${i}`,
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) {
                ok++;
                if (moveLog.length < 5) moveLog.push({
                    booking_id: b.id, old_room_id: b.room_id, new_room_id: candidate.id,
                    target_room_type: candidate.room_type || candidate.category || '__unknown__',
                });
            } else {
                fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1;
            }
        }
        const attempted = target.length - skippedNoTarget;
        const moveStatus = (attempted >= 5 && ok === 0) ? 'FAIL' : (ok > 0 ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'positive_room_move', status: moveStatus,
            endpoint: '/api/pms-core/room-move',
            note: `n=${target.length} attempted=${attempted} skipped_no_target=${skippedNoTarget} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)} target_contract=vacant+same_category (architect tur-5)` });
        recPerf(testInfo, MOD, 'room_move', samples, true);
        expect(moveStatus, `positive_room_move FAIL: n=${target.length} ok=${ok} fail_modes=${JSON.stringify(failModes)}`).not.toBe('FAIL');
        if (ok === 0 && checkedIn.length >= 50) {
            recFinding(testInfo, 'P2', MOD, 'Hiçbir room-move başarılı değil',
                `${target.length} move denendi, hepsi reject. Tüm hedef odalar dolu olabilir (500/500 seed) — pozitif test için 02-spec'in checkout sonrası boş room override gerekli.`);
        }
        // Post-move STATE transfer assertion (architect tur-3 feedback): RNL transfer
        // doğrulaması — başarılı move'lardan sonra booking.room_id GET ile yeni oda
        // olmalı. Bu, room_night_lock + booking pointer'ın atomik transfer edildiğinin
        // direkt kanıtı. fetchAllByPrefix ile bookings'i yeniden listele.
        if (moveLog.length > 0) {
            const after = await fetchAllByPrefix(request, stressTokens.stress_token,
                '/api/pms/bookings', 'stress_prefix', stressState.data_prefix);
            const byId = new Map(after.map((b) => [b.id, b]));
            let transferOk = 0, transferFail = 0; const failDetail = [];
            for (const m of moveLog) {
                const b = byId.get(m.booking_id);
                if (b && b.room_id === m.new_room_id) transferOk++;
                else {
                    transferFail++;
                    failDetail.push({ id: m.booking_id, expected: m.new_room_id, actual: b?.room_id ?? 'missing' });
                }
            }
            const transferStatus = transferFail === 0 ? 'PASS' : 'FAIL';
            rec(testInfo, { module: MOD, step: 'post_move_state_transfer', status: transferStatus,
                endpoint: '/api/pms/bookings (re-fetch)',
                note: `verified=${moveLog.length} transfer_ok=${transferOk} transfer_fail=${transferFail} ${transferFail > 0 ? `mismatch=${JSON.stringify(failDetail)}` : ''}` });
            if (transferFail > 0) {
                recFinding(testInfo, 'P0', MOD,
                    'Room move sonrası booking.room_id transfer edilmedi (RNL inconsistency)',
                    `${moveLog.length} başarılı move'dan ${transferFail}'inde booking.room_id eski odada kaldı. Atomicity / room_night_lock transfer kırık. Detay: ${JSON.stringify(failDetail)}`);
            }
            expect(transferStatus, 'post_move_state_transfer FAIL — RNL transfer kırık').not.toBe('FAIL');
        }
        // Post-batch external-call invariant re-assert (runtime endpoint).
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'positive_room_move_50', stressState, request, stressTokens.pilot_token);
    });

    test('B) Negative — occupied target reject', async ({ request, stressTokens }, testInfo) => {
        // İki occupied booking seç; A'yı B'nin odasına taşımaya çalış → 400 bekle
        const checkedIn = bookings.filter((b) => b.status === 'checked_in');
        if (checkedIn.length < 2) { rec(testInfo, { module: MOD, step: 'negative_occupied', status: 'SKIP', note: `checked_in=${checkedIn.length}` }); return; }
        let rejected = 0, accepted = 0, other = 0;
        const trials = Math.min(10, Math.floor(checkedIn.length / 2));
        for (let i = 0; i < trials; i++) {
            const a = checkedIn[i];
            const b = checkedIn[checkedIn.length - 1 - i];
            if (a.id === b.id) continue;
            const r = await callTimed(request, 'post', '/api/pms-core/room-move', {
                booking_id: a.id, new_room_id: b.room_id, reason: `F8A neg-occupied ${i}`,
            }, stressTokens.stress_token);
            if (r.status === 400 || r.status === 409 || r.status === 422) rejected++;
            else if (r.ok) accepted++;
            else other++;
        }
        rec(testInfo, { module: MOD, step: 'negative_occupied_target', status: rejected >= trials * 0.8 ? 'PASS' : 'REVIEW',
            note: `n=${trials} rejected=${rejected} accepted=${accepted} other=${other}` });
        if (accepted > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Occupied odaya room-move kabul edildi (overbook riski)',
                `${trials} occupied-target denemesi → ${accepted} kabul edildi. front_desk_service.room_move occupancy guard zayıf.`);
        }
    });

    test('C) Negative — OOO target reject', async ({ request, stressTokens }, testInfo) => {
        const checkedIn = bookings.filter((b) => b.status === 'checked_in');
        if (checkedIn.length < 1 || rooms.length < 5) { rec(testInfo, { module: MOD, step: 'ooo_setup', status: 'SKIP' }); return; }
        // 3 odayı OOO işaretle, oraya move dene
        const oooRooms = rooms.slice(rooms.length - 3);
        let oooSet = 0;
        for (const r of oooRooms) {
            const resp = await callTimed(request, 'post', '/api/pms-core/housekeeping/room-status',
                { room_id: r.id, new_status: 'out_of_order', notes: 'F8A OOO test', force: true },
                stressTokens.stress_token);
            if (resp.ok) oooSet++;
        }
        if (oooSet === 0) {
            rec(testInfo, { module: MOD, step: 'ooo_negative_move', status: 'REVIEW',
                note: 'OOO işaretlenemedi — HK status endpoint reddetti, negative move testi atlandı' });
            return;
        }
        let rejected = 0, accepted = 0;
        for (const b of checkedIn.slice(0, 3)) {
            for (const r of oooRooms) {
                if (b.room_id === r.id) continue;
                const resp = await callTimed(request, 'post', '/api/pms-core/room-move',
                    { booking_id: b.id, new_room_id: r.id, reason: 'F8A OOO neg' },
                    stressTokens.stress_token);
                if (resp.status === 400 || resp.status === 409 || resp.status === 422) rejected++;
                else if (resp.ok) accepted++;
                break;
            }
        }
        rec(testInfo, { module: MOD, step: 'ooo_negative_move', status: rejected > 0 && accepted === 0 ? 'PASS' : 'REVIEW',
            note: `ooo_set=${oooSet} rejected=${rejected} accepted=${accepted}` });
        if (accepted > 0) {
            recFinding(testInfo, 'P1', MOD, 'OOO odaya room-move kabul edildi',
                `OOO odaya ${accepted} move başarılı oldu. HK readiness check eksik.`);
        }
    });

    test('D) Race — aynı hedefe paralel iki move', async ({ request, stressTokens }, testInfo) => {
        const checkedIn = bookings.filter((b) => b.status === 'checked_in');
        if (checkedIn.length < 2) { rec(testInfo, { module: MOD, step: 'race', status: 'SKIP' }); return; }
        const a = checkedIn[0], b = checkedIn[1];
        const candidate = rooms.find((r) => r.id !== a.room_id && r.id !== b.room_id);
        if (!candidate) { rec(testInfo, { module: MOD, step: 'race', status: 'SKIP', note: 'no free target' }); return; }
        const [r1, r2] = await Promise.all([
            callTimed(request, 'post', '/api/pms-core/room-move',
                { booking_id: a.id, new_room_id: candidate.id, reason: 'F8A race A' }, stressTokens.stress_token),
            callTimed(request, 'post', '/api/pms-core/room-move',
                { booking_id: b.id, new_room_id: candidate.id, reason: 'F8A race B' }, stressTokens.stress_token),
        ]);
        const okCount = (r1.ok ? 1 : 0) + (r2.ok ? 1 : 0);
        rec(testInfo, { module: MOD, step: 'race_same_target', status: okCount === 1 ? 'PASS' : 'REVIEW',
            note: `r1=${r1.status} r2=${r2.status} ok_count=${okCount} (1 = healthy serialization)` });
        if (okCount === 2) {
            recFinding(testInfo, 'P1', MOD,
                'Race condition — aynı odaya iki move başarılı',
                `Paralel iki room-move aynı hedef için her ikisi başarılı (r1=${r1.status} r2=${r2.status}). Atomicity / unique index eksikliği.`);
        }
    });

    test('E) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `pilot bookings before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});

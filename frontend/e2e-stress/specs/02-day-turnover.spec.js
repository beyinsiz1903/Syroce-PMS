// F8A § 02 — Day turnover: yoğun checkout + same-day turnover (walk-in) + open-folio guard.
//
// Seed varsayımları (backend/domains/admin/router/stress.py):
// - 500 booking status="checked_in", folio status="open" balance=0,
//   her folio'da room/night charge'lar var → checkout için ya force=true ya
//   önce payment ile balance kapatılmalı.
// - Pilot tenant'a hiç dokunulmaz; tüm mutasyonlar stress bearer ile.
//
// Test stratejisi:
//   A) Open-folio guard: 20 booking → checkout (force=false) → 400 bekle (folio>0 → guard)
//   B) Force checkout batch: 100 booking → checkout (force=true) → latency sample
//   C) Same-day turnover: 30 boşalan oda → walk-in ile yeni check-in → latency sample
//   D) Pilot drift: spec başı/sonu /api/pms/bookings count diff = 0
//
// Edge case'ler REVIEW olarak raporlanır, suite NO-GO'ya düşmez.
import { test, expect, rec } from '../fixtures/stress-context.js';
import { fetchAllByPrefix, fetchSingle, callTimed, recPerf, recFinding, pilotBookingsCount, assertNoExternalCallsPostBatch } from '../fixtures/stress-helpers.js';

const MOD = 'day-turnover';

test.describe.configure({ mode: 'serial' });

test.describe('F8A § 02 — Day turnover (checkout + walk-in + guard)', () => {
    let bookings = []; // stress bookings cached for the suite
    let rooms = [];
    let pilotBefore = null;
    let roomsFreed = []; // architect tur-5: B'de force-checkout BAŞARILI olan booking.room_id'leri;
                         // C same-day turnover bu odaları kullanır (boşalan odaya re-check-in).

    test('Setup: stress bookings + rooms listele, pilot drift baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        const prefix = stressState.data_prefix;
        bookings = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/bookings', 'stress_prefix', prefix, { maxPages: 8, pageSize: 200 });
        rooms = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/rooms', 'stress_prefix', prefix, { maxPages: 8, pageSize: 200 });
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup_listing', status: 'PASS',
            note: `bookings_listed=${bookings.length} rooms_listed=${rooms.length} pilot_before=${pilotBefore?.count}` });
        expect(bookings.length, 'Stress booking listesi boş — endpoint pagination/seed sorunu').toBeGreaterThan(0);
    });

    test('A) Open-folio guard: 20 checkout (force=false) → 400 bekle', async ({ request, stressTokens }, testInfo) => {
        if (bookings.length < 20) { rec(testInfo, { module: MOD, step: 'guard_sample_size', status: 'SKIP', note: `only ${bookings.length} bookings` }); return; }
        const sample = bookings.slice(0, 20);
        let blocked = 0, allowed = 0, other = 0;
        const samples = [];
        for (const b of sample) {
            const r = await callTimed(request, 'post', '/api/pms-core/checkout',
                { booking_id: b.id, force: false }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.status === 400) blocked++;
            else if (r.ok) allowed++;
            else other++;
        }
        rec(testInfo, { module: MOD, step: 'open_folio_guard', status: blocked >= 15 ? 'PASS' : 'REVIEW',
            note: `blocked=${blocked}/20 allowed=${allowed} other=${other} (≥15 = guard works as expected)` });
        if (blocked < 15) {
            recFinding(testInfo, blocked === 0 ? 'P1' : 'P2', MOD,
                'Open-folio guard zayıf veya yok',
                `20 booking checkout (force=false) → blocked=${blocked} allowed=${allowed} other=${other}. Beklenen: balance>0 olan folio'lar 400 ile reddedilmeli (front_desk_service.checkout balance check).`);
        }
        recPerf(testInfo, MOD, 'checkout_force_false', samples, true);
    });

    test('B) Force checkout batch: 100 booking (force=true)', async ({ request, stressTokens }, testInfo) => {
        const candidates = bookings.slice(20); // skip ones used in guard test
        if (candidates.length < 50) { rec(testInfo, { module: MOD, step: 'force_co_sample', status: 'SKIP', note: `only ${candidates.length}` }); return; }
        const target = candidates.slice(0, Math.min(100, candidates.length));
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        for (const b of target) {
            const r = await callTimed(request, 'post', '/api/pms-core/checkout',
                { booking_id: b.id, force: true }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) {
                ok++;
                // Architect tur-5: aynı-oda turnover sözleşmesi — boşalan room_id'yi kaydet.
                if (b.room_id) roomsFreed.push(b.room_id);
            }
            else { fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
        }
        rec(testInfo, { module: MOD, step: 'force_checkout_batch', status: ok >= target.length * 0.9 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/checkout', http: 200,
            note: `n=${target.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)}` });
        recPerf(testInfo, MOD, 'checkout_force_true', samples, ok >= target.length * 0.9);
        if (ok < target.length * 0.5) {
            recFinding(testInfo, 'P0', MOD,
                'Force checkout büyük oranda başarısız',
                `${target.length} force checkout denendi, sadece ${ok} başarılı. Modes: ${JSON.stringify(failModes)}.`);
        }
        // Post-batch external-call invariant re-assert (architect tur-3 feedback).
        // 100 destructive checkout sonrası hiçbir OTA push / webhook tetiklenmemiş olmalı.
        // Backend stub helper-level signature: stressState fixture spec'e _stressContext_'ten gelmeli.
    });

    test('B-post) external_calls invariant after force_checkout_batch (runtime endpoint)', async ({ request, stressTokens, stressState }, testInfo) => {
        // Architect tur-3: artık /admin/stress/external-calls endpoint'inden runtime
        // okuma yapıyor (snapshot fallback REVIEW). Hot path'e tek GET; idempotent.
        const ok = await assertNoExternalCallsPostBatch(testInfo, MOD, 'force_checkout_100', stressState, request, stressTokens.pilot_token);
        expect(ok, 'force_checkout_100 sonrası external_calls invariant ihlal').toBe(true);
    });

    test('C) Same-day turnover: 50 walk-in (boşalan oda → yeni booking)', async ({ request, stressTokens, stressState }, testInfo) => {
        // Architect tur-5: aynı-oda turnover sözleşmesi — B'de force-checkout BAŞARILI olan
        // bookings'in room_id'leri (`roomsFreed`) bu test'in target'ı olur. Bu, "checkout →
        // RNL release → same-day re-check-in" akışını DOĞRU şekilde validate eder
        // (eskiden `rooms.slice(0, 50)` rastgele oda alıyordu — turnover semantiği yoktu).
        // Fallback: roomsFreed boşsa rooms.slice(0, 50) (eski davranış) ile REVIEW yazılır.
        const usingTurnover = roomsFreed.length >= 25;
        const targetRoomIds = usingTurnover ? roomsFreed.slice(0, 50) : rooms.slice(0, 50).map((r) => r.id);
        const targetSource = usingTurnover ? 'rooms_freed_by_force_checkout' : 'fallback_rooms_slice';
        if (targetRoomIds.length < 25) {
            rec(testInfo, { module: MOD, step: 'walkin_sample', status: 'SKIP',
                note: `target sample yetersiz n=${targetRoomIds.length}/25 (rooms_freed=${roomsFreed.length} rooms_total=${rooms.length})` });
            return;
        }
        const target = targetRoomIds.map((id) => rooms.find((r) => r.id === id) || { id });
        const samples = []; let ok = 0, fail = 0; const failModes = {};
        for (let i = 0; i < target.length; i++) {
            const room = target[i];
            const ts = Date.now();
            const r = await callTimed(request, 'post', '/api/pms-core/walk-in', {
                room_id: room.id,
                nights: 1,
                rate: 1000,
                guest_name: `E2E_STRESS_F8A_WalkIn_${ts}_${i}`,
                guest_phone: `+9055500${String(i).padStart(5, '0')}`,
                guest_email: `f8a-walkin-${ts}-${i}@e2e-stress.example.com`,
                guest_id_number: `E2EWI${ts}${i}`,
                adults: 1,
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) ok++;
            else { fail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
        }
        rec(testInfo, { module: MOD, step: 'same_day_walkin', status: usingTurnover && ok >= 25 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/walk-in',
            note: `target_source=${targetSource} n=${target.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)} (≥25/50 ok + same-room contract ⇒ turnover akışı çalışıyor)` });
        recPerf(testInfo, MOD, 'walkin_create', samples, ok >= 25);
        if (ok === 0) {
            recFinding(testInfo, 'P1', MOD,
                'Same-day turnover walk-in akışı başarısız',
                `${target.length} walk-in denemesi 0 başarı. Modes: ${JSON.stringify(failModes)}. Olası sebep: oda hala occupied state'te (checkout RNL release etmemiş).`);
        }
        // Post-batch external-call invariant re-assert via runtime endpoint (architect tur-3+5: hard expect).
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'walk_in_50', stressState, request, stressTokens.pilot_token);
        expect(extOk, 'walk_in_50 sonrası external_calls invariant ihlal').toBe(true);
    });

    test('D) Pilot drift: spec sonu pilot bookings sayımı = baseline', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP', note: 'pilot baseline yok' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        if (drift !== 0) {
            recFinding(testInfo, 'P0', MOD, 'Pilot tenant mutation tespit edildi',
                `Pilot bookings before=${pilotBefore.count} after=${after?.count} drift=${drift}.`);
        }
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `pilot bookings before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        expect(drift).toBe(0);
    });

    test('E) External calls: stress seed snapshot hala []', async ({ stressState }, testInfo) => {
        // Stress operasyonları için ayrı bir external_calls counter yok — seed snapshot
        // baselineimiz bu. F8A burası "sözleşme dokümante" amaçlı: live operasyonlarda
        // yeni external call kanıtı olsa logs/Sentry'ye düşerdi.
        expect(stressState.seed_response.external_calls_made).toEqual([]);
        rec(testInfo, { module: MOD, step: 'external_calls_baseline', status: 'PASS',
            note: 'Seed snapshot=[] korunuyor; spec içi mutasyonlar için canlı sayaç yok (REVIEW: backend in-flight counter eklenmesi P3 backlog).' });
    });
});

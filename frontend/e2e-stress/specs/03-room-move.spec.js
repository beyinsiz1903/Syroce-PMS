// F8A § 03 — Room move: positive (hedef boş), negative (hedef occupied / OOO), race.
//
// Stress dataset 500/500 occupied başlıyor. Pozitif move için önce hedefi boşaltmak gerekir.
// Spec'in kendi Setup'ı her room_type için yeterli boş oda yaratır (force-checkout) — bu
// sayede 02-day-turnover'dan bağımsız (ör. izole D/E chunk) çalışsa da positive_room_move
// 30/30 PASS verir. Sırayla koşumda da idempotent: zaten boşalmış odalar etkilenmez.
// Ref: task #162 (P2 finding — drill report 20260514 §11).
import { test, expect, rec } from '../fixtures/stress-context.js';
import { fetchAllByPrefix, callTimed, recPerf, recFinding, pilotBookingsCount, assertNoExternalCallsPostBatch } from '../fixtures/stress-helpers.js';

const MOD = 'room-move';

// Positive room-move target sample size (A testi).
const POSITIVE_MOVE_N = 50;
// Setup'ta tutturulması ZORUNLU minimum same-category eligible target sayısı.
// Task #162 acceptance: "30/30 positive room-move PASS". 30 → hard precondition.
const MIN_ELIGIBLE_TARGETS = 30;
// free-until-threshold loop iterasyon limiti (sonsuz döngü güvenlik kapısı).
const SETUP_FREE_ROUNDS = 4;

test.describe.configure({ mode: 'serial' });

// ── Pure helpers (setup + A için ortak hesap) ────────────────────────────────
// F8A tur-11 (Kapsam D.3-4 user-mandated): single normalizer used for BOTH
// rooms and bookings so room_type field-name drift (snake_case vs camelCase
// vs legacy `category`/`type`) cannot silently zero out the eligible count.
function normalizeRoomType(x) {
    if (!x || typeof x !== 'object') return '__unknown__';
    return x.room_type || x.roomType || x.category || x.type || '__unknown__';
}
function _computeVacantByType(bookingsList, roomsList) {
    const checkedIn = bookingsList.filter((b) => b.status === 'checked_in');
    const occupied = new Set(checkedIn.map((b) => b.room_id).filter(Boolean));
    const m = new Map();
    for (const r of roomsList) {
        if (occupied.has(r.id)) continue;
        const t = normalizeRoomType(r);
        m.set(t, (m.get(t) || 0) + 1);
    }
    return m;
}
function _computeDemand(bookingsList, n) {
    const target = bookingsList.filter((b) => b.status === 'checked_in').slice(0, n);
    const demand = new Map();
    for (const b of target) {
        const t = normalizeRoomType(b);
        demand.set(t, (demand.get(t) || 0) + 1);
    }
    return { demand, targetIds: new Set(target.map((b) => b.id)), total: target.length };
}
function _eligibleCount(demand, vacant) {
    let n = 0;
    for (const [t, d] of demand) n += Math.min(d, vacant.get(t) || 0);
    return n;
}

test.describe('F8A § 03 — Room move (positive + negative + race)', () => {
    let bookings = [];
    let rooms = [];
    let pilotBefore = null;

    test('Setup: stress bookings + rooms snapshot + guarantee vacant pool', async ({ request, stressTokens, stressState }, testInfo) => {
        const prefix = stressState.data_prefix;
        bookings = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/bookings', 'stress_prefix', prefix);
        // Architect tur-7 fix: /api/pms/rooms cache (redis + cache_warmer)
        // stale projection (stress_prefix eksik) ile dolmuş olabilir → filter
        // 0 döner → eligible=0 → setup FAIL. `include_virtual=true` query param'ı
        // endpoint'in `use_cache` koşulunu false yapar (pms_rooms.py:289) →
        // DB query path zorlanır, stress_prefix dahil fresh data döner.
        rooms = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/rooms?include_virtual=true', 'stress_prefix', prefix);

        // Tur-9 debug: rooms=0 case'inde direkt endpoint probe + raw response
        // attach et. fetchAllByPrefix sessizce 0 döndürdüğünde root cause görünmez:
        //  (a) endpoint 401/403/5xx — auth/health regression
        //  (b) endpoint 200 fakat response shape farklı (j.rooms / j.items / j.data
        //      beklentisi tutmuyor) → list parse 0
        //  (c) shape doğru fakat `stress_prefix` field'ı item'larda yok
        //      (cache_warmer projection drop veya backend serializer dropu)
        //  (d) prefix gerçekten match etmiyor (round prefix mismatch)
        if (!Array.isArray(rooms) || rooms.length === 0) {
            const probeUrl = '/api/pms/rooms?include_virtual=true&page=1&page_size=200&limit=200';
            let probeStatus = null, probeBody = null, probeKeys = null, probeListLen = null, probeFirst3 = null;
            try {
                const r = await request.get(probeUrl, {
                    headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                    failOnStatusCode: false, timeout: 30_000,
                });
                probeStatus = r.status();
                probeBody = await r.json().catch(() => null);
                if (probeBody && typeof probeBody === 'object') {
                    probeKeys = Array.isArray(probeBody) ? ['<array>'] : Object.keys(probeBody);
                    const list = Array.isArray(probeBody) ? probeBody
                        : (probeBody.rooms || probeBody.items || probeBody.data || []);
                    probeListLen = Array.isArray(list) ? list.length : null;
                    if (Array.isArray(list)) {
                        probeFirst3 = list.slice(0, 3).map((it) => ({
                            id: it?.id, room_number: it?.room_number, room_type: it?.room_type,
                            tenant_id: it?.tenant_id, stress_seed: it?.stress_seed,
                            stress_prefix: it?.stress_prefix,
                            // prefix match indicator
                            prefix_match: typeof it?.stress_prefix === 'string' && it.stress_prefix.startsWith(prefix),
                            keys: it && typeof it === 'object' ? Object.keys(it).slice(0, 30) : null,
                        }));
                    }
                }
            } catch (e) {
                probeBody = { _probe_error: String(e?.message || e) };
            }
            try {
                testInfo.attach('rooms-zero-debug.json', {
                    body: Buffer.from(JSON.stringify({
                        active_round_prefix: prefix,
                        seed_rooms_count: stressState?.seed_response?.counts?.rooms ?? null,
                        bookings_fetched: bookings.length,
                        rooms_fetched: rooms.length,
                        probe: {
                            url: probeUrl,
                            status: probeStatus,
                            response_keys: probeKeys,
                            parsed_list_length: probeListLen,
                            first_3_items: probeFirst3,
                            raw_body_truncated: probeBody && typeof probeBody === 'object'
                                ? JSON.stringify(probeBody).slice(0, 4000)
                                : String(probeBody).slice(0, 4000),
                        },
                        diagnosis_hints: [
                            'status != 200 → backend regression (auth/health)',
                            'parsed_list_length === 0 → endpoint döndü ama liste boş (cache_warmer/projection sorunu)',
                            'parsed_list_length > 0 fakat rooms_fetched === 0 → stress_prefix field item\'larda yok veya prefix mismatch',
                            'first_3_items[].prefix_match=false → backend serializer stress_prefix\'i drop ediyor',
                        ],
                    }, null, 2)),
                    contentType: 'application/json',
                });
            } catch (_) { /* attach is best-effort */ }
            // Eğer endpoint 200 + items mevcut ama prefix mismatch (cache_warmer
            // projection drop) → fallback: stress_seed=true filter'ı ile tekrar dene.
            // Bu cross-round leak risk taşır ama setup'ı kurtarmak için son çare.
            if (probeStatus && probeStatus >= 200 && probeStatus < 300 && probeListLen > 0) {
                const fallbackList = Array.isArray(probeBody) ? probeBody
                    : (probeBody.rooms || probeBody.items || probeBody.data || []);
                const fallbackRooms = fallbackList.filter((r) => r?.stress_seed === true);
                if (fallbackRooms.length > 0) {
                    rooms = fallbackRooms;
                    recFinding(testInfo, 'P2', MOD,
                        'Rooms fetch stress_prefix mismatch — stress_seed:true fallback\'e düşüldü',
                        `prefix_match=0 fakat stress_seed:true ile ${fallbackRooms.length} room recovered. Backend serializer stress_prefix\'i drop ediyor olabilir; root cause: pms_rooms.py response model.`);
                }
            }
        }

        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // ── Vacant-pool garantisi (task #162) ────────────────────────────────
        // Free-until-threshold: A testinin demand profilini (ilk 50 checked_in,
        // her birinin room_type'ı) çıkar; her tip için (demand − vacant_supply)
        // kadar EK booking force-checkout et — target sample havuzu kendisi
        // boşaltılmaz (`targetIds` muaf). Re-fetch & yeniden hesapla.
        // Birden fazla round: re-fetch sonrası order ufak kayabilir (status
        // değişen bookings dropladı), bu yüzden iteratif yakınsama gerekir.
        let totalFreedOk = 0;
        let totalFreedFail = 0;
        const failModes = {};
        let lastEligible = 0;
        let lastDemandTotal = 0;
        for (let round = 0; round < SETUP_FREE_ROUNDS; round++) {
            const { demand, targetIds, total } = _computeDemand(bookings, POSITIVE_MOVE_N);
            lastDemandTotal = total;
            const vacant = _computeVacantByType(bookings, rooms);
            lastEligible = _eligibleCount(demand, vacant);
            if (lastEligible >= Math.min(MIN_ELIGIBLE_TARGETS, total)) break;

            const checkedInByType = new Map();
            for (const b of bookings.filter((b) => b.status === 'checked_in' && !targetIds.has(b.id))) {
                // F8A tur-11 (architect review): MUST use the same normalizer here too.
                // If raw field is bucketed to '__unknown__' while demand uses normalized
                // key, the free-loop cannot match types → can never close the shortfall.
                const t = normalizeRoomType(b);
                if (!checkedInByType.has(t)) checkedInByType.set(t, []);
                checkedInByType.get(t).push(b);
            }
            const toFree = [];
            for (const [t, dem] of demand) {
                const have = vacant.get(t) || 0;
                const need = Math.max(0, dem - have);
                if (need <= 0) continue;
                const pool = checkedInByType.get(t) || [];
                const take = Math.min(need, pool.length);
                for (const b of pool.slice(-take)) toFree.push(b);
            }
            if (toFree.length === 0) break; // hiçbir tip için ek boşaltma kaynağı yok

            for (const b of toFree) {
                const r = await callTimed(request, 'post', '/api/pms-core/checkout',
                    { booking_id: b.id, force: true }, stressTokens.stress_token);
                if (r.ok) totalFreedOk++;
                else { totalFreedFail++; const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            }
            bookings = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/bookings', 'stress_prefix', prefix);
        }

        // Final eligible recount after loop exit.
        const { demand: demandFinal, total: totalFinal } = _computeDemand(bookings, POSITIVE_MOVE_N);
        const vacantFinal = _computeVacantByType(bookings, rooms);
        const eligibleFinal = _eligibleCount(demandFinal, vacantFinal);
        const requiredEligible = Math.min(MIN_ELIGIBLE_TARGETS, totalFinal);
        const setupStatus = eligibleFinal >= requiredEligible ? 'PASS' : 'FAIL';

        // Tur-10 debug (Kapsam A.2 + architect tur-10 review öneri #1): demand/vacant/
        // checked-in dağılımını her round attach et. Regression olduğunda hangi tipte
        // demand>supply olduğu tek dosyada görünür. PASS durumunda da yazılır (baseline).
        try {
            const checkedInByType = {};
            for (const b of bookings.filter((b) => b.status === 'checked_in')) {
                const t = normalizeRoomType(b);
                checkedInByType[t] = (checkedInByType[t] || 0) + 1;
            }
            const roomsByType = {};
            for (const r of rooms) {
                const t = normalizeRoomType(r);
                roomsByType[t] = (roomsByType[t] || 0) + 1;
            }
            const extraVacantRooms = rooms.filter((r) => r.room_move_target === true);
            // F8A tur-11 (Kapsam D.2): extras per-type so debug surfaces
            // whether the dedicated pool covers demand room-by-room.
            const extrasByType = {};
            for (const r of extraVacantRooms) {
                const t = normalizeRoomType(r);
                extrasByType[t] = (extrasByType[t] || 0) + 1;
            }
            // Sample first 3 raw item keys for field-name drift diagnosis.
            const sampleBookingKeys = bookings[0] ? Object.keys(bookings[0]).slice(0, 30) : null;
            const sampleRoomKeys = rooms[0] ? Object.keys(rooms[0]).slice(0, 30) : null;
            const seedBreakdown = stressState?.seed_response?.rooms_breakdown ?? null;
            const perTypeBreakdown = {};
            for (const t of new Set([...demandFinal.keys(), ...vacantFinal.keys()])) {
                const d = demandFinal.get(t) || 0;
                const v = vacantFinal.get(t) || 0;
                perTypeBreakdown[t] = {
                    demand: d, vacant_supply: v,
                    eligible_contrib: Math.min(d, v),
                    shortfall: Math.max(0, d - v),
                };
            }
            testInfo.attach('room-move-setup-debug.json', {
                body: Buffer.from(JSON.stringify({
                    verdict: setupStatus,
                    eligible_final: eligibleFinal,
                    required_min: requiredEligible,
                    target_total: totalFinal,
                    free_rounds_used: SETUP_FREE_ROUNDS,
                    freed_ok: totalFreedOk,
                    freed_fail: totalFreedFail,
                    fail_modes: failModes,
                    snapshot_sizes: {
                        bookings_total: bookings.length,
                        rooms_total: rooms.length,
                        extra_vacant_pool: extraVacantRooms.length,
                        rooms_with_stress_prefix_filter: rooms.length,
                    },
                    seed_contract: seedBreakdown,
                    distribution: {
                        demand_first_n: Object.fromEntries(demandFinal),
                        vacant_by_type: Object.fromEntries(vacantFinal),
                        checked_in_by_type: checkedInByType,
                        rooms_by_type: roomsByType,
                        room_move_target_by_type: extrasByType,
                        per_type_breakdown: perTypeBreakdown,
                    },
                    field_name_drift_check: {
                        sample_booking_keys: sampleBookingKeys,
                        sample_room_keys: sampleRoomKeys,
                        bookings_with_room_type: bookings.filter((b) => b.room_type).length,
                        bookings_with_camel_roomType: bookings.filter((b) => b.roomType).length,
                        bookings_with_category: bookings.filter((b) => b.category).length,
                        rooms_with_room_type: rooms.filter((r) => r.room_type).length,
                        rooms_with_camel_roomType: rooms.filter((r) => r.roomType).length,
                        rooms_with_category: rooms.filter((r) => r.category).length,
                        rooms_with_move_target_flag: extraVacantRooms.length,
                    },
                    diagnosis_hints: [
                        'shortfall>0 olan tipler eligible<required_min sebebidir',
                        'extra_vacant_pool=0 + seed_contract.extra_room_move_targets>0 → /api/pms/rooms projection room_move_target drop ediyor',
                        'rooms_total<seed_contract.total_rooms → fetchAllByPrefix snapshot eksik (pagination/prefix-mismatch)',
                        'bookings_with_room_type=0 + bookings_with_camel_roomType>0 → field-name drift, normalizeRoomType yetmedi',
                    ],
                }, null, 2)),
                contentType: 'application/json',
            });
        } catch (_) { /* attach best-effort */ }

        rec(testInfo, { module: MOD, step: 'setup', status: setupStatus,
            note: `bookings=${bookings.length} rooms=${rooms.length} pilot_before=${pilotBefore?.count} `
                + `vacant_pool_setup={freed_ok=${totalFreedOk} freed_fail=${totalFreedFail} `
                + `fail_modes=${JSON.stringify(failModes)} target_total=${totalFinal} `
                + `eligible_after=${eligibleFinal} required_min=${requiredEligible} `
                + `eligible_first_round=${lastEligible}/${lastDemandTotal} rounds=${SETUP_FREE_ROUNDS}}` });

        if (setupStatus === 'FAIL') {
            recFinding(testInfo, 'P1', MOD,
                'Setup vacant pool yetersiz — positive_room_move deterministic değil',
                `eligible=${eligibleFinal}/${requiredEligible}, freed_ok=${totalFreedOk} freed_fail=${totalFreedFail}, `
                + `fail_modes=${JSON.stringify(failModes)}. force-checkout endpoint reddediyor olabilir veya `
                + `dataset çok küçük (room_count<${MIN_ELIGIBLE_TARGETS}).`);
        }
        // F8A tur-11 (architect review action #2): if seed contract reports
        // ≥50 extra room-move targets but the fetched pool is <50, we have a
        // fetch/projection/prefix-mismatch problem (not normalize logic).
        // Fail fast with explicit diagnosis BEFORE generic eligible assertion.
        const expectedExtras = stressState?.seed_response?.seeded_counts?.extra_room_move_targets ?? 0;
        if (expectedExtras >= 50) {
            const fetchedExtras = rooms.filter((r) => r.room_move_target === true).length;
            expect(fetchedExtras,
                `seed reported ${expectedExtras} extra room_move_target rooms but only ${fetchedExtras} fetched — `
                + `likely /api/pms/rooms projection drop or fetchAllByPrefix pagination/prefix-mismatch. `
                + `Check room-move-setup-debug.json field_name_drift_check + seed_contract.`
            ).toBeGreaterThanOrEqual(50);
        }
        // Hard precondition (architect feedback task #162 review): setup
        // garantili miktarda eligible target sağlamadan A testine geçilmez.
        expect(eligibleFinal,
            `setup vacant pool yetersiz: eligible=${eligibleFinal} target_total=${totalFinal} required_min=${requiredEligible}`,
        ).toBeGreaterThanOrEqual(requiredEligible);
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
        // Deterministic pass criteria (architect feedback task #162 review):
        // Setup precondition zaten ≥30 eligible target garantiliyor, dolayısıyla
        // burada PASS = ok === attempted. Kısmi başarı (ok < attempted) FAIL —
        // room-move endpoint reddediyor demektir (race, RNL kilit, occupancy).
        const moveStatus = attempted === 0 ? 'SKIP'
            : (ok === attempted ? 'PASS' : (ok > 0 ? 'FAIL' : 'FAIL'));
        rec(testInfo, { module: MOD, step: 'positive_room_move', status: moveStatus,
            endpoint: '/api/pms-core/room-move',
            note: `n=${target.length} attempted=${attempted} skipped_no_target=${skippedNoTarget} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)} target_contract=vacant+same_category (architect tur-5) pass_contract=ok_eq_attempted (task #162)` });
        recPerf(testInfo, MOD, 'room_move', samples, true);
        if (moveStatus === 'FAIL') {
            recFinding(testInfo, ok === 0 ? 'P1' : 'P2', MOD,
                'positive_room_move kısmi/tamamen başarısız',
                `${attempted} same-category vacant target denendi, ${ok} başarılı (${fail} reject). `
                + `Modes: ${JSON.stringify(failModes)}. Setup ≥${MIN_ELIGIBLE_TARGETS} eligible garantiliyor; `
                + `burada FAIL backend room-move reject anlamına gelir (RNL conflict, occupancy guard, race).`);
        }
        expect(ok, `positive_room_move pass_contract: ok=${ok} attempted=${attempted} fail_modes=${JSON.stringify(failModes)}`)
            .toBe(attempted);
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
        // Post-batch external-call invariant re-assert (runtime endpoint, hard expect — architect tur-5).
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'positive_room_move_50', stressState, request, stressTokens.pilot_token);
        expect(extOk, 'positive_room_move_50 sonrası external_calls invariant ihlal').toBe(true);
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
        // Architect tur-5: race target ZORUNLU vacant + a/b dışı olmalı; aksi halde
        // 1 başarı/1 reject kontratı doğal occupancy reject ile karışır → REVIEW maskelenir.
        const occupiedRoomIds = new Set(checkedIn.map((bk) => bk.room_id).filter(Boolean));
        const candidate = rooms.find((r) => !occupiedRoomIds.has(r.id) && r.id !== a.room_id && r.id !== b.room_id);
        if (!candidate) { rec(testInfo, { module: MOD, step: 'race', status: 'SKIP',
            note: `no guaranteed-vacant target (occupied=${occupiedRoomIds.size}/${rooms.length}) — race kontratı deterministic değil` }); return; }
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

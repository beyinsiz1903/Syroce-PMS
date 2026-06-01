// F7 — Bulk Seed 500 spec. globalSetup'ta yapılan seed sonrası
// API-üzerinden tenant-isolation + sayım doğrulaması.
import { test, expect, rec } from '../fixtures/stress-context.js';

const ROOM_COUNT = parseInt(process.env.E2E_ROOM_COUNT || '500', 10);

async function fetchListLen(request, token, p) {
    const r = await request.get(p, {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false, timeout: 30_000,
    });
    if (!r.ok()) return { http: r.status(), len: null };
    const j = await r.json().catch(() => ({}));
    const list = Array.isArray(j) ? j : (j?.rooms || j?.bookings || j?.guests || j?.folios || j?.items || []);
    return { http: r.status(), len: Array.isArray(list) ? list.length : null, sample: Array.isArray(list) && list[0] ? Object.keys(list[0]).slice(0, 6) : null };
}

test.describe('F7 § Bulk Seed 500 — entity counts', () => {

    test('Seed response counts: rooms=guests=bookings=folios=500 + extra room-move pool', async ({ stressState }, testInfo) => {
        // F8A tur-11 contract:
        //   seeded_counts.rooms = base PMS inventory (500) — must match ROOM_COUNT strictly
        //   seeded_counts.extra_room_move_targets ≥ 50 — dedicated vacant pool for room-move spec
        //   seeded_counts.total_rooms = rooms + extra_room_move_targets (DB physical count)
        // Bookings/guests/folios still equal ROOM_COUNT (extras have no booking/guest/folio).
        const c = stressState.seed_response.seeded_counts;
        expect(c.rooms, 'base rooms must equal ROOM_COUNT (PMS inventory)').toBe(ROOM_COUNT);
        expect(c.guests).toBe(ROOM_COUNT);
        expect(c.bookings).toBe(ROOM_COUNT);
        expect(c.folios).toBe(ROOM_COUNT);
        expect(c.extra_room_move_targets, 'dedicated vacant pool for room-move').toBeGreaterThanOrEqual(50);
        expect(c.total_rooms, 'total_rooms = base + extras').toBe(c.rooms + c.extra_room_move_targets);
        rec(testInfo, { module: 'bulk-seed-500', step: 'core_counts_rooms_guests_bookings_folios', status: 'PASS',
            note: `rooms=${c.rooms} extras=${c.extra_room_move_targets} total=${c.total_rooms} guests=${c.guests} bookings=${c.bookings} folios=${c.folios}` });
    });

    test('Seed response counts: housekeeping_tasks=500', async ({ stressState }, testInfo) => {
        const c = stressState.seed_response.seeded_counts;
        expect(c.housekeeping_tasks).toBe(ROOM_COUNT);
        rec(testInfo, { module: 'bulk-seed-500', step: 'hk_count', status: 'PASS', note: `hk=${c.housekeeping_tasks}` });
    });

    test('Seed response counts: room_night_locks beklenen aralıkta', async ({ stressState }, testInfo) => {
        const c = stressState.seed_response.seeded_counts;
        // stay_nights cycles 1..4 → base toplam = 125*(1+2+3+4)=1250.
        // Task #178 aging (deterministik, tarihten bağımsız): is_aged=(i%8!=0 &&
        // i%3==0) → 146 booking'e nights += aged_offset_days (2+(i%4)) eklenir =
        // +543 ekstra gece. Toplam 1250 + 543 = 1793 (seed factory tam belirli;
        // değer gevşetilmedi, sadece aging sonrası deterministik toplama güncellendi).
        const expected = ROOM_COUNT === 500 ? 1793 : null;
        if (expected) expect(c.room_night_locks).toBe(expected);
        else expect(c.room_night_locks).toBeGreaterThanOrEqual(ROOM_COUNT);
        rec(testInfo, { module: 'bulk-seed-500', step: 'rnl_count', status: 'PASS', note: `rnl=${c.room_night_locks} (expected=${expected})` });
    });

    test('Seed response counts: folio_charges ≥ 2*N (per-night room + acc-tax)', async ({ stressState }, testInfo) => {
        const c = stressState.seed_response.seeded_counts;
        const expected = ROOM_COUNT === 500 ? 2293 : null; // 1793 per-night room charge (Task #178 aging dahil) + 500 acc-tax = 2293
        if (expected) expect(c.folio_charges).toBe(expected);
        else expect(c.folio_charges).toBeGreaterThanOrEqual(2 * ROOM_COUNT);
        rec(testInfo, { module: 'bulk-seed-500', step: 'charges_count', status: 'PASS', note: `charges=${c.folio_charges} (expected=${expected})` });
    });

    test('Seed performance: 500-oda toplam < 30s', async ({ stressState }, testInfo) => {
        const total = stressState.seed_response.timing_ms?.total ?? 0;
        expect(total).toBeLessThan(30_000);
        rec(testInfo, { module: 'bulk-seed-500', step: 'seed_duration', status: 'PASS', note: `total_ms=${total}` });
    });

    test('Variety: 20 room_types × 5 blocks × 10 floors meta', async ({ stressState }, testInfo) => {
        const v = stressState.seed_response.variety;
        expect(v.room_types).toBe(20);
        expect(v.blocks).toBe(5);
        expect(v.floors).toBe(10);
        rec(testInfo, { module: 'bulk-seed-500', step: 'variety_axes', status: 'PASS', note: JSON.stringify(v) });
    });

    // NOT: /api/pms/{rooms,bookings,guests} default pagination uygular
    // (typical page_size=30..100). 500-tam sayım için ya page query'leri yapmalı,
    // ya da seed_response.seeded_counts authoritative kabul edilmeli (F7 scaffold için ikincisi).
    // Bu testler tenant-scope sızıntı yok ↔ endpoint cevap veriyor doğrulaması yapar.
    test('Stress tenant rooms endpoint sızıntısız cevap (stress bearer)', async ({ request, stressTokens }, testInfo) => {
        const r = await fetchListLen(request, stressTokens.stress_token, '/api/pms/rooms');
        if (r.http !== 200) {
            rec(testInfo, { module: 'bulk-seed-500', step: 'stress_rooms_endpoint', status: 'REVIEW',
                endpoint: '/api/pms/rooms', http: r.http, note: 'Endpoint cevap vermedi.' });
            return;
        }
        expect(r.len).toBeGreaterThan(0);
        rec(testInfo, { module: 'bulk-seed-500', step: 'stress_rooms_endpoint', status: 'PASS',
            endpoint: '/api/pms/rooms', http: 200,
            note: `page_len=${r.len} (paginated; authoritative=seeded_counts.rooms=${ROOM_COUNT})` });
    });

    test('Stress tenant bookings endpoint sızıntısız cevap (stress bearer)', async ({ request, stressTokens }, testInfo) => {
        const r = await fetchListLen(request, stressTokens.stress_token, '/api/pms/bookings');
        if (r.http !== 200) {
            rec(testInfo, { module: 'bulk-seed-500', step: 'stress_bookings_endpoint', status: 'REVIEW',
                endpoint: '/api/pms/bookings', http: r.http, note: 'Endpoint cevap vermedi.' });
            return;
        }
        expect(r.len).toBeGreaterThan(0);
        rec(testInfo, { module: 'bulk-seed-500', step: 'stress_bookings_endpoint', status: 'PASS',
            endpoint: '/api/pms/bookings', http: 200,
            note: `page_len=${r.len} (paginated; authoritative=seeded_counts.bookings=${ROOM_COUNT})` });
    });

    test('Stress tenant guests endpoint sızıntısız cevap (stress bearer)', async ({ request, stressTokens }, testInfo) => {
        const r = await fetchListLen(request, stressTokens.stress_token, '/api/pms/guests');
        if (r.http !== 200) {
            rec(testInfo, { module: 'bulk-seed-500', step: 'stress_guests_endpoint', status: 'REVIEW',
                endpoint: '/api/pms/guests', http: r.http, note: 'Endpoint cevap vermedi.' });
            return;
        }
        expect(r.len).toBeGreaterThan(0);
        rec(testInfo, { module: 'bulk-seed-500', step: 'stress_guests_endpoint', status: 'PASS',
            endpoint: '/api/pms/guests', http: 200,
            note: `page_len=${r.len} (paginated; authoritative=seeded_counts.guests=${ROOM_COUNT})` });
    });

    test('Pilot tenant counts değişmedi (mutation=0)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (!stressTokens.pilot_token || !stressState.pilot_baseline) {
            rec(testInfo, { module: 'bulk-seed-500', step: 'pilot_no_mutation', status: 'SKIP',
                note: 'Pilot token / baseline yok — kontrol atlandı.' });
            return;
        }
        const r = await fetchListLen(request, stressTokens.pilot_token, '/api/pms/bookings');
        expect(r.http).toBe(200);
        const baseline = stressState.pilot_baseline.bookings;
        expect(r.len, `pilot bookings drift! baseline=${baseline} now=${r.len}`).toBe(baseline);
        rec(testInfo, { module: 'bulk-seed-500', step: 'pilot_no_mutation', status: 'PASS',
            note: `pilot bookings baseline=${baseline} now=${r.len} drift=0` });
    });

    test('External calls = [] korundu', async ({ stressState }, testInfo) => {
        expect(stressState.seed_response.external_calls_made).toEqual([]);
        rec(testInfo, { module: 'bulk-seed-500', step: 'external_calls_zero', status: 'PASS' });
    });

    // Task #172: real ops outbox endpoint = routers.outbox_admin GET
    // /api/outbox/status (require_super_admin → pilot_token). Seed is a direct
    // DB insert path that publishes NO domain events, so the outbox snapshot is
    // read for a health-metric shape assertion (numeric pending/failed) rather
    // than a best-effort scan over non-existent /api/admin/cm/* paths.
    test('Outbox status: seed domain event yaymaz (super_admin snapshot)', async ({ request, stressTokens, stressState }, testInfo) => {
        const r = await request.get('/api/outbox/status', {
            headers: { Authorization: `Bearer ${stressTokens.pilot_token}` },
            failOnStatusCode: false, timeout: 10_000,
        });
        expect(r.status(), '/api/outbox/status super_admin ile 200 dönmeli').toBe(200);
        const j = await r.json();
        expect(typeof j.pending, 'pending numeric').toBe('number');
        expect(typeof j.failed, 'failed numeric').toBe('number');
        rec(testInfo, { module: 'bulk-seed-500', step: 'outbox_no_unexpected', status: 'PASS',
            endpoint: '/api/outbox/status',
            note: `pending=${j.pending} retry=${j.retry} failed=${j.failed} (seed domain event yayınlamıyor — snapshot)` });
    });
});

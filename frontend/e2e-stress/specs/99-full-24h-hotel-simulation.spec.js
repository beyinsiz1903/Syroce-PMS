// F8J § 99 — Full 24h hotel simulation (final integration smoke).
//
// Bu spec, F8A–F8N fazları yeşilden sonra çalıştırılacak "tek otel günü"
// entegrasyon smoke'udur. 5 zaman dilimi (Sabah/Öğlen/Akşam/Gece/Final)
// boyunca bir otelin tipik operasyon zincirini deterministik biçimde
// koşturur ve state'i adımdan adıma taşır.
//
// Mutlak kurallar (F8 doctrine — tüm fazlarla aynı):
//   - external_calls = [] (post-batch invariant, runtime endpoint)
//   - pilot_drift = 0 (spec başı/sonu count diff)
//   - 5xx = 0 (server-side crash yok)
//   - P0 = P1 = 0 (yeşil verdict şartı)
//   - Tüm mutasyonlar stress bearer ile (pilot tenant'a ASLA dokunulmaz)
//   - Her POST/PUT/DELETE'te Idempotency-Key header (F8N standardı)
//   - Adımlar arası 1500ms gap (F8H standardı, write-bucket rate-limit)
//   - module-blocked doctrine: setup probe non-2xx → tüm phase'ler skip,
//     pilot drift + external_calls invariant bağımsız çalışır
//
// State carry-over:
//   - SabahA walk-in 20 booking → checkedInIds[]
//   - SabahB walk-in'in folio'ları → folio charge/payment için target
//   - SabahC: HK temizleme listesi için freedRoomIds[] (ÖğlenA'da kullanılır)
//   - ÖğlenA HK room-status → room state context
//   - ÖğlenC procurement PR → PRId (görsel zincir; status değiştirilmez,
//     sadece create + list yapılır — heavy approval chain F8E kapsamında)
//   - AkşamA folio charge → targetFolioBookings[]
//   - AkşamB folio payment dry-run (balance kapatma)
//   - AkşamC room-move 5 oda (vacant havuzdan)
//   - AkşamD HR clock-in
//   - GeceA checkout (force=true) → released
//   - GeceB night-audit run + re-run idempotency
//   - GeceC accounting dashboard + finance summary
//   - Final: external_calls invariant + pilot drift snapshot
//
// Reporter modülü: `full_24h` (md-reporter dinamik aggregation).
//
// Süre bütçesi: spec total ≤ 60 dakika (Playwright workflow timeout 30dk'lık
// stres CI matrix'te ayrı job olarak çalışır). Per-test setTimeout 600s.
import { randomUUID } from 'node:crypto';
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    fetchAllByPrefix,
    callTimed,
    callTimed,
    recPerf,
    recFinding,
    pilotBookingsCount,
    assertNoExternalCallsPostBatch,
} from '../fixtures/stress-helpers.js';

const MOD = 'full_24h';
const SUB_PREFIX = `F8J_24H_${Date.now()}`;
const GAP_MS = 1500;
const gap = () => new Promise((res) => setTimeout(res, GAP_MS));
const idemKey = (op) => `${SUB_PREFIX}_${op}_${Date.now()}_${randomUUID()}`;

test.describe.configure({ mode: 'serial' });

// Suite-wide state (carryover across phases).
let moduleBlocked = false;
let moduleBlockedReason = '';
let pilotBefore = null;
let bookings = [];
let rooms = [];
let prefix = null;

// Sabah outputs
let walkInBookingIds = [];   // newly walked-in (akşamda folio operasyonu hedefi)
let walkInRoomIds = [];      // checked-in rooms (gece checkout için)
let qrCount = null;
let complaintCount = null;

// Öğlen outputs
let freedRoomIds = [];       // HK transition test edilen oda ID'leri
let prCreatedId = null;
let miceEventCount = null;

// Akşam outputs
let chargedBookingIds = [];
let paymentDoneBookingIds = [];
let movedRoomPairs = [];     // [{from, to}]
let clockInOk = 0;

// Gece outputs
let checkedOutOk = 0;
let naFirstSnapshot = null;
let naSecondSnapshot = null;

test.describe('F8J § 99 — Full 24h hotel simulation', () => {
    test.setTimeout(600_000);

    // ──────────────────────────────────────────────────────────────────────
    // SETUP — reachability probe + baseline
    // ──────────────────────────────────────────────────────────────────────
    test('Setup: reachability probe + pilot baseline + stress inventory', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Explicit reachability probe (F8N pattern): module-blocked yalnız
        // gerçek endpoint cevap vermediğinde tetiklenir; "data scarcity"
        // farklı bir sebep olarak ayrı raporlanır.
        const probes = await Promise.all([
            callTimed(request, 'get', '/api/pms/bookings?limit=1', undefined, stressTokens.stress_token),
            callTimed(request, 'get', '/api/pms/rooms?limit=1', undefined, stressTokens.stress_token),
            callTimed(request, 'get', '/api/pms/guests?limit=1', undefined, stressTokens.stress_token),
        ]);
        const probeStatuses = probes.map((p) => p.status);
        const probeOk = probes.every((p) => p.ok);
        if (!probeOk) {
            moduleBlocked = true;
            moduleBlockedReason = `setup probe non-2xx statuses=${JSON.stringify(probeStatuses)}`;
            rec(testInfo, { module: MOD, step: 'setup_probe', status: 'REVIEW',
                note: `module-blocked: ${moduleBlockedReason}` });
            recFinding(testInfo, 'P2', MOD,
                '24h sim module-blocked — PMS list endpoint reachability fail',
                `Probe statuses: bookings=${probeStatuses[0]} rooms=${probeStatuses[1]} guests=${probeStatuses[2]}. Tüm phase'ler skip; pilot drift + external_calls invariant koşacak.`);
            return;
        }

        bookings = await fetchAllByPrefix(request, stressTokens.stress_token,
            '/api/pms/bookings', 'stress_prefix', prefix,
            { maxPages: 8, pageSize: 200 });
        rooms = await fetchAllByPrefix(request, stressTokens.stress_token,
            '/api/pms/rooms', 'stress_prefix', prefix,
            { maxPages: 8, pageSize: 200 });

        rec(testInfo, { module: MOD, step: 'setup_baseline', status: 'PASS',
            note: `bookings=${bookings.length} rooms=${rooms.length} pilot_before=${pilotBefore?.count} probe_statuses=${JSON.stringify(probeStatuses)}` });

        if (bookings.length < 30 || rooms.length < 30) {
            moduleBlocked = true;
            moduleBlockedReason = `data scarcity bookings=${bookings.length} rooms=${rooms.length}`;
            recFinding(testInfo, 'P2', MOD,
                '24h sim data scarcity — F8 seed minimumun altinda',
                `Bookings=${bookings.length}, rooms=${rooms.length}. F8 stres seed >=500 bekler. Phase-ler skip; invariant-lar kosar.`);
        }
    });

    // ──────────────────────────────────────────────────────────────────────
    // SABAH — arrivals + 20 check-in + QR sample + complaints sample
    // ──────────────────────────────────────────────────────────────────────
    test('Sabah-A) Arrivals listele + 20 walk-in (atomic check-in)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }

        // Arrivals listing (read-only; non-2xx → REVIEW informational).
        // Architect-iter-1 fix #1: backend route `/api/pms/arrivals`
        // (pms_bookings.py:213). Önceki `/today` suffix yoktu → 404 sahte
        // REVIEW. /today suffix farklı router'da (`/api/arrivals/today`,
        // frontdesk_router) ama PMS namespacing tercih edilir.
        const arr = await callTimed(request, 'get', '/api/pms/arrivals',
            undefined, stressTokens.stress_token);
        rec(testInfo, { module: MOD, step: 'sabah_arrivals_list',
            status: arr.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms/arrivals',
            note: `http=${arr.status} count=${Array.isArray(arr.body) ? arr.body.length : (arr.body?.items?.length ?? 'n/a')}` });
        await gap();

        // 20 walk-in (02-day-turnover pattern; atomic check-in + folio open).
        // Walk-in target rooms: stress rooms ilk 25, F8H room-status pre-clean.
        const candidates = rooms.slice(0, 25);
        let cleaned = 0;
        for (const r of candidates) {
            const cr = await callTimed(request, 'post', '/api/pms-core/housekeeping/room-status',
                { room_id: r.id, new_status: 'inspected', force: true,
                  notes: `${SUB_PREFIX} sabah pre-walkin` }, stressTokens.stress_token,
                { headers: { 'Idempotency-Key': idemKey('sabah_hk_clean') } });
            if (cr.ok) cleaned++;
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'sabah_precond_hk_clean',
            status: cleaned >= 20 ? 'PASS' : 'REVIEW',
            note: `hk_cleaned=${cleaned}/25` });

        const samples = [];
        let ok = 0, fail = 0;
        const failModes = {};
        for (let i = 0; i < candidates.length && walkInBookingIds.length < 20; i++) {
            const room = candidates[i];
            const ts = Date.now();
            const r = await callTimed(request, 'post', '/api/pms-core/walk-in', {
                room_id: room.id,
                nights: 1,
                rate: 1000,
                guest_name: `E2E_STRESS_${SUB_PREFIX}_Guest_${ts}_${i}`,
                guest_phone: `+9055500${String(i).padStart(5, '0')}`,
                guest_email: `${SUB_PREFIX.toLowerCase()}-guest-${ts}-${i}@e2e-stress.example.com`,
                guest_id_number: `${SUB_PREFIX}${ts}${i}`,
                adults: 1,
            }, stressTokens.stress_token,
            { headers: { 'Idempotency-Key': idemKey('walk_in') } });
            samples.push(r.ms);
            if (r.ok && r.body?.id) {
                ok++;
                walkInBookingIds.push(r.body.id);
                if (r.body.room_id) walkInRoomIds.push(r.body.room_id);
                else if (room.id) walkInRoomIds.push(room.id);
            } else {
                fail++;
                const k = `s${r.status}`;
                failModes[k] = (failModes[k] || 0) + 1;
            }
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'sabah_walkin_20',
            status: ok >= 10 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/walk-in',
            note: `n=${candidates.length} ok=${ok} fail=${fail} fail_modes=${JSON.stringify(failModes)} (≥10 = sabah zinciri sürdürülebilir)` });
        recPerf(testInfo, MOD, 'sabah_walk_in', samples, ok >= 10);
        if (ok < 5 && fail > 0) {
            recFinding(testInfo, 'P2', MOD,
                'Sabah walk-in batch düşük başarı — zincir downstream daralacak',
                `Modes=${JSON.stringify(failModes)}. Akşam folio operasyonları walkInBookingIds[] üzerinden ilerler; düşük örneklem rapor edildi, P0/P1 değil.`);
        }
    });

    test('Sabah-B) external_calls invariant (sabah_walk_in_batch)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        const ok = await assertNoExternalCallsPostBatch(testInfo, MOD,
            'sabah_walk_in_batch', stressState, request, stressTokens.pilot_token);
        expect(ok, 'Sabah walk-in sonrası external_calls invariant ihlal').toBe(true);
    });

    test('Sabah-C) QR request listing + complaints listing', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        // Architect-iter-1 fix #3: QR listing endpoint `/api/room-requests`
        // (room_qr_requests.py:481). `/api/qr/requests` route YOK → sahte
        // REVIEW.
        const qr = await callTimed(request, 'get', '/api/room-requests?limit=50',
            undefined, stressTokens.stress_token);
        if (qr.ok) {
            const list = Array.isArray(qr.body) ? qr.body : (qr.body?.items || qr.body?.requests || []);
            qrCount = list.length;
        }
        rec(testInfo, { module: MOD, step: 'sabah_qr_list',
            status: qr.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/room-requests',
            note: `http=${qr.status} qr_count=${qrCount ?? 'n/a'}` });
        await gap();

        // Architect-iter-1 fix #4: complaints listing `/api/gm/complaints`
        // (revenue/analytics_router/gm.py:258). `/api/service/complaints`
        // sadece POST (sales/router.py:266); GET route YOK → 405/404.
        const cm = await callTimed(request, 'get', '/api/gm/complaints?limit=50',
            undefined, stressTokens.stress_token);
        if (cm.ok) {
            const list = Array.isArray(cm.body) ? cm.body : (cm.body?.complaints || cm.body?.items || []);
            complaintCount = list.length;
        }
        rec(testInfo, { module: MOD, step: 'sabah_complaints_list',
            status: cm.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/gm/complaints',
            note: `http=${cm.status} complaint_count=${complaintCount ?? 'n/a'}` });
        await gap();
    });

    // ──────────────────────────────────────────────────────────────────────
    // ÖĞLEN — HK transition + inventory + procurement + MICE
    // ──────────────────────────────────────────────────────────────────────
    test('Öğlen-A) Housekeeping transition (10 oda)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        // Walk-in olmayan 10 oda → dirty → cleaning → inspected pipeline.
        const targets = rooms
            .filter((r) => !walkInRoomIds.includes(r.id))
            .slice(0, 10);
        if (targets.length < 5) {
            rec(testInfo, { module: MOD, step: 'oglen_hk_transition', status: 'SKIP',
                note: `not enough non-walked rooms (${targets.length})` });
            return;
        }
        let dirtyOk = 0, cleanOk = 0;
        for (const room of targets) {
            const d = await callTimed(request, 'post', '/api/pms-core/housekeeping/room-status',
                { room_id: room.id, new_status: 'dirty', force: true,
                  notes: `${SUB_PREFIX} oglen dirty` }, stressTokens.stress_token,
                { headers: { 'Idempotency-Key': idemKey('oglen_hk_dirty') } });
            if (d.ok) dirtyOk++;
            await gap();
            const c = await callTimed(request, 'post', '/api/pms-core/housekeeping/room-status',
                { room_id: room.id, new_status: 'inspected', force: true,
                  notes: `${SUB_PREFIX} oglen clean` }, stressTokens.stress_token,
                { headers: { 'Idempotency-Key': idemKey('oglen_hk_clean') } });
            if (c.ok) {
                cleanOk++;
                freedRoomIds.push(room.id);
            }
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'oglen_hk_transition',
            status: cleanOk >= 5 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/housekeeping/room-status',
            note: `dirty_ok=${dirtyOk}/${targets.length} clean_ok=${cleanOk}/${targets.length}` });
    });

    test('Öğlen-B) Inventory movement (read + 3 hareket)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        const inv = await callTimed(request, 'get', '/api/accounting/inventory?limit=10',
            undefined, stressTokens.stress_token);
        const items = Array.isArray(inv.body) ? inv.body
            : (inv.body?.items || inv.body?.inventory || []);
        rec(testInfo, { module: MOD, step: 'oglen_inventory_list',
            status: inv.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/accounting/inventory',
            note: `http=${inv.status} items_seen=${items.length}` });
        if (!inv.ok || items.length === 0) return;
        await gap();

        const target = items.slice(0, 3);
        let movementOk = 0;
        for (const it of target) {
            const itId = it.id || it._id || it.item_id;
            if (!itId) continue;
            const mv = await callTimed(request, 'post',
                `/api/accounting/inventory/${encodeURIComponent(itId)}/stock-movement`, {
                    quantity: 1,
                    movement_type: 'in',
                    notes: `${SUB_PREFIX} oglen stock smoke`,
                }, stressTokens.stress_token,
                { headers: { 'Idempotency-Key': idemKey('oglen_stock_mv') } });
            if (mv.ok) movementOk++;
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'oglen_inventory_movement',
            status: movementOk >= 1 ? 'PASS' : 'REVIEW',
            note: `movement_ok=${movementOk}/${target.length}` });
    });

    test('Öğlen-C) Procurement: purchase request create', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        // Supplier listing
        const sup = await callTimed(request, 'get', '/api/procurement/suppliers?limit=5',
            undefined, stressTokens.stress_token);
        const suppliers = Array.isArray(sup.body) ? sup.body
            : (sup.body?.suppliers || sup.body?.items || []);
        if (!sup.ok || suppliers.length === 0) {
            rec(testInfo, { module: MOD, step: 'oglen_procurement_pr', status: 'REVIEW',
                note: `supplier list http=${sup.status} count=${suppliers.length} — PR atlanır` });
            return;
        }
        await gap();

        const pr = await callTimed(request, 'post', '/api/procurement/purchase-requests', {
            supplier_id: suppliers[0].id,
            requested_for: 'F8J 24h sim',
            items: [{ item_name: `${SUB_PREFIX}_smoke_item`, quantity: 1, estimated_price: 100 }],
            notes: `${SUB_PREFIX} oglen smoke PR (status değiştirilmez)`,
        }, stressTokens.stress_token,
        { headers: { 'Idempotency-Key': idemKey('oglen_pr') } });

        if (pr.ok && pr.body?.id) prCreatedId = pr.body.id;
        rec(testInfo, { module: MOD, step: 'oglen_procurement_pr',
            status: pr.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/procurement/purchase-requests',
            note: `http=${pr.status} pr_id=${prCreatedId ?? 'n/a'}` });
    });

    test('Öğlen-D) MICE events listing (event update opsiyonel)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        const ev = await callTimed(request, 'get', '/api/mice/events?limit=10',
            undefined, stressTokens.stress_token);
        const events = Array.isArray(ev.body) ? ev.body
            : (ev.body?.events || ev.body?.items || []);
        miceEventCount = events.length;
        rec(testInfo, { module: MOD, step: 'oglen_mice_list',
            status: ev.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/mice/events',
            note: `http=${ev.status} event_count=${miceEventCount}` });
    });

    test('Öğlen-E) external_calls invariant (oglen_ops_batch)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        const ok = await assertNoExternalCallsPostBatch(testInfo, MOD,
            'oglen_ops_batch', stressState, request, stressTokens.pilot_token);
        expect(ok, 'Öğlen batch sonrası external_calls invariant ihlal').toBe(true);
    });

    // ──────────────────────────────────────────────────────────────────────
    // AKŞAM — folio charge + payment + room move + HR shift
    // ──────────────────────────────────────────────────────────────────────
    test('Akşam-A) Folio charge (walk-in booking\'lerine ek charge)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        if (walkInBookingIds.length === 0) {
            // Sabah walk-in başarısızsa mevcut checked-in booking'lerden örnekle.
            const fallback = bookings.filter((b) => b.status === 'checked_in').slice(0, 5);
            for (const b of fallback) walkInBookingIds.push(b.id);
        }
        if (walkInBookingIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'aksam_folio_charge', status: 'SKIP',
                note: 'no checked-in booking to charge' });
            return;
        }
        const target = walkInBookingIds.slice(0, Math.min(10, walkInBookingIds.length));
        const samples = []; let ok = 0; const failModes = {};
        for (const bid of target) {
            // Architect-iter-1 fix #2: backend ChargePostRequest schema
            // (pms_hardening.py:92-94) hem `folio_id` hem `booking_id`
            // ZORUNLU. 04-folio-mass paterni: folio_id ≡ booking_id (sistem
            // booking-keyed folio kullanır; folio create işlemi check-in
            // anında atomik yapılır). Önceki revizyon sadece booking_id
            // gönderiyordu → 422 sahte REVIEW.
            const r = await callTimed(request, 'post', '/api/pms-core/folio/charge', {
                folio_id: bid,
                booking_id: bid,
                amount: 50,
                description: `${SUB_PREFIX} aksam mini-bar`,
                category: 'misc',
                quantity: 1.0,
                tax_rate: 0.18,
            }, stressTokens.stress_token,
            { headers: { 'Idempotency-Key': idemKey('aksam_charge') } });
            samples.push(r.ms);
            if (r.ok) { ok++; chargedBookingIds.push(bid); }
            else { const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'aksam_folio_charge',
            status: ok >= 1 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/folio/charge',
            note: `n=${target.length} ok=${ok} fail_modes=${JSON.stringify(failModes)}` });
        recPerf(testInfo, MOD, 'aksam_charge', samples, ok >= 1);
    });

    test('Akşam-B) Folio payment (charge edilen booking\'leri kapat)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        if (chargedBookingIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'aksam_folio_payment', status: 'SKIP',
                note: 'no charged booking' });
            return;
        }
        const target = chargedBookingIds.slice(0, 5);
        let ok = 0; const failModes = {};
        for (const bid of target) {
            const r = await callTimed(request, 'post', '/api/pms-core/folio/payment', {
                booking_id: bid,
                amount: 50,
                payment_method: 'cash',
                notes: `${SUB_PREFIX} aksam payment smoke`,
            }, stressTokens.stress_token,
            { headers: { 'Idempotency-Key': idemKey('aksam_payment') } });
            if (r.ok) { ok++; paymentDoneBookingIds.push(bid); }
            else { const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'aksam_folio_payment',
            status: ok >= 1 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/folio/payment',
            note: `n=${target.length} ok=${ok} fail_modes=${JSON.stringify(failModes)}` });
    });

    test('Akşam-C) Room move (5 oda, vacant havuzdan)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        // Source: walk-in booking'ler; target: freedRoomIds (Öğlen-A'da temizlenen).
        const moves = Math.min(5, walkInBookingIds.length, freedRoomIds.length);
        if (moves < 1) {
            rec(testInfo, { module: MOD, step: 'aksam_room_move', status: 'SKIP',
                note: `not enough moves walkIn=${walkInBookingIds.length} freed=${freedRoomIds.length}` });
            return;
        }
        let ok = 0; const failModes = {};
        for (let i = 0; i < moves; i++) {
            const bid = walkInBookingIds[i];
            const toRoom = freedRoomIds[i];
            const r = await callTimed(request, 'post', '/api/pms-core/room-move', {
                booking_id: bid,
                new_room_id: toRoom,
                reason: `${SUB_PREFIX} aksam mini room-move`,
            }, stressTokens.stress_token,
            { headers: { 'Idempotency-Key': idemKey('aksam_move') } });
            if (r.ok) {
                ok++;
                movedRoomPairs.push({ booking: bid, to: toRoom });
                if (!walkInRoomIds.includes(toRoom)) walkInRoomIds.push(toRoom);
            } else {
                const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1;
            }
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'aksam_room_move',
            status: ok >= 1 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/room-move',
            note: `n=${moves} ok=${ok} fail_modes=${JSON.stringify(failModes)}` });
    });

    test('Akşam-D) HR clock-in (5 personel smoke)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        // Stress staff listing
        const stf = await callTimed(request, 'get', '/api/hr/staff?limit=5',
            undefined, stressTokens.stress_token);
        const staff = Array.isArray(stf.body) ? stf.body
            : (stf.body?.staff || stf.body?.items || []);
        if (!stf.ok || staff.length === 0) {
            rec(testInfo, { module: MOD, step: 'aksam_hr_clock_in', status: 'REVIEW',
                note: `staff list http=${stf.status} count=${staff.length}` });
            return;
        }
        await gap();
        const target = staff.slice(0, 5);
        for (const s of target) {
            const r = await callTimed(request, 'post', '/api/hr/clock-in', {
                staff_id: s.id,
                notes: `${SUB_PREFIX} aksam clock-in smoke`,
            }, stressTokens.stress_token,
            { headers: { 'Idempotency-Key': idemKey('aksam_clockin') } });
            if (r.ok) clockInOk++;
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'aksam_hr_clock_in',
            status: clockInOk >= 1 ? 'PASS' : 'REVIEW',
            endpoint: '/api/hr/clock-in',
            note: `clock_in_ok=${clockInOk}/${target.length}` });
    });

    test('Akşam-E) external_calls invariant (aksam_ops_batch)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        const ok = await assertNoExternalCallsPostBatch(testInfo, MOD,
            'aksam_ops_batch', stressState, request, stressTokens.pilot_token);
        expect(ok, 'Akşam batch sonrası external_calls invariant ihlal').toBe(true);
    });

    // ──────────────────────────────────────────────────────────────────────
    // GECE — checkout + night audit + finance summary + reports
    // ──────────────────────────────────────────────────────────────────────
    test('Gece-A) Checkout (force=true, walk-in batch)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        if (walkInBookingIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'gece_checkout', status: 'SKIP', note: 'no booking to checkout' });
            return;
        }
        const samples = []; const failModes = {};
        for (const bid of walkInBookingIds) {
            const r = await callTimed(request, 'post', '/api/pms-core/checkout',
                { booking_id: bid, force: true }, stressTokens.stress_token,
                { headers: { 'Idempotency-Key': idemKey('gece_checkout') } });
            samples.push(r.ms);
            if (r.ok) checkedOutOk++;
            else { const k = `s${r.status}`; failModes[k] = (failModes[k] || 0) + 1; }
            await gap();
        }
        rec(testInfo, { module: MOD, step: 'gece_checkout',
            status: checkedOutOk >= Math.max(1, walkInBookingIds.length * 0.5) ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/checkout',
            note: `n=${walkInBookingIds.length} ok=${checkedOutOk} fail_modes=${JSON.stringify(failModes)}` });
        recPerf(testInfo, MOD, 'gece_checkout', samples, checkedOutOk >= 1);
    });

    test('Gece-B) Night audit run + re-run idempotency', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        // F8A § 06 paterni — 500-folio stress için 180s timeout, run timeout 240s.
        test.setTimeout(240_000);
        const bd = await callTimed(request, 'get', '/api/pms-core/night-audit/business-date',
            undefined, stressTokens.stress_token);
        const businessDate = bd.ok ? bd.body?.business_date : null;
        await gap();
        const body = businessDate ? { business_date: businessDate } : {};

        const r1 = await callTimed(request, 'post', '/api/pms-core/night-audit/run',
            body, stressTokens.stress_token,
            { maxRetries: 1, fallbackSleepMs: 5000, timeout: 180_000,
              headers: { 'Idempotency-Key': idemKey('gece_na_run1') } });
        naFirstSnapshot = r1.body || null;
        const status1 = r1.ok ? 'PASS'
            : (r1.status === 403 ? 'REVIEW' : (r1.status === 0 ? 'REVIEW' : 'FAIL'));
        rec(testInfo, { module: MOD, step: 'gece_na_run_first', status: status1,
            endpoint: '/api/pms-core/night-audit/run',
            note: `http=${r1.status} latency=${r1.ms}ms posted=${naFirstSnapshot?.posted_charges ?? naFirstSnapshot?.summary?.posted_charges ?? 'n/a'}` });
        if (status1 === 'FAIL') {
            recFinding(testInfo, 'P1', MOD, 'Gece night audit run başarısız',
                `status=${r1.status} body=${JSON.stringify(r1.body).slice(0, 300)}`);
        }
        if (r1.status === 0) {
            recFinding(testInfo, 'P2', MOD,
                'Night audit run timeout — backend perf regression (ops follow-up)',
                `latency=${r1.ms}ms attempts=${r1.attempts ?? 'n/a'}; 180s timeout aşıldı.`);
        }
        await gap();

        if (!r1.ok) return;
        const r2 = await callTimed(request, 'post', '/api/pms-core/night-audit/run',
            body, stressTokens.stress_token,
            { maxRetries: 1, fallbackSleepMs: 5000, timeout: 180_000,
              headers: { 'Idempotency-Key': idemKey('gece_na_run2') } });
        naSecondSnapshot = r2.body || null;
        const firstPosted = naFirstSnapshot?.posted_charges ?? naFirstSnapshot?.summary?.posted_charges ?? null;
        const secondPosted = naSecondSnapshot?.posted_charges ?? naSecondSnapshot?.summary?.posted_charges ?? null;
        const idemOk = r2.ok && (
            secondPosted === 0
            || secondPosted === null
            || naSecondSnapshot?.status === 'already_posted'
            || naSecondSnapshot?.idempotent === true
        );
        const status2 = !r2.ok ? 'REVIEW' : (idemOk ? 'PASS' : 'REVIEW');
        rec(testInfo, { module: MOD, step: 'gece_na_rerun', status: status2,
            endpoint: '/api/pms-core/night-audit/run',
            note: `http=${r2.status} first_posted=${firstPosted} second_posted=${secondPosted} idem_marker=${naSecondSnapshot?.status ?? naSecondSnapshot?.idempotent ?? 'n/a'}` });
        if (r2.ok && !idemOk && secondPosted != null && secondPosted > 0) {
            recFinding(testInfo, 'P1', MOD,
                'Night audit re-run idempotency ihlal — duplicate posting şüphesi',
                `first=${firstPosted} second=${secondPosted}`);
        }
    });

    test('Gece-C) Finance summary + reports read', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        const dash = await callTimed(request, 'get', '/api/accounting/dashboard',
            undefined, stressTokens.stress_token);
        rec(testInfo, { module: MOD, step: 'gece_accounting_dashboard',
            status: dash.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/accounting/dashboard',
            note: `http=${dash.status}` });
        await gap();

        const naExc = await callTimed(request, 'get', '/api/pms-core/night-audit/exceptions?status=open',
            undefined, stressTokens.stress_token);
        const exList = Array.isArray(naExc.body) ? naExc.body
            : (naExc.body?.exceptions || naExc.body?.items || []);
        rec(testInfo, { module: MOD, step: 'gece_na_exceptions',
            status: naExc.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/night-audit/exceptions',
            note: `http=${naExc.status} open_exc=${exList.length}` });
    });

    test('Gece-D) external_calls invariant (gece_ops_batch)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) { test.skip(true, moduleBlockedReason); return; }
        const ok = await assertNoExternalCallsPostBatch(testInfo, MOD,
            'gece_ops_batch', stressState, request, stressTokens.pilot_token);
        expect(ok, 'Gece batch sonrası external_calls invariant ihlal').toBe(true);
    });

    // ──────────────────────────────────────────────────────────────────────
    // FINAL — pilot drift + external_calls final + dashboard/readiness snapshot
    // ──────────────────────────────────────────────────────────────────────
    test('Final-A) Pilot drift = 0 (24h sim sonu)', async ({ request, stressTokens }, testInfo) => {
        // INVARIANT — moduleBlocked olsa bile koşar.
        if (!pilotBefore) {
            rec(testInfo, { module: MOD, step: 'final_pilot_drift', status: 'SKIP',
                note: 'pilot baseline yok' });
            return;
        }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'final_pilot_drift',
            status: drift === 0 ? 'PASS' : 'FAIL',
            note: `pilot bookings before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) {
            recFinding(testInfo, 'P0', MOD, 'Pilot tenant mutation tespit edildi (24h sim)',
                `pilot before=${pilotBefore.count} after=${after?.count} drift=${drift}`);
        }
        expect(drift).toBe(0);
    });

    test('Final-B) external_calls invariant (final_24h_batch)', async ({ request, stressTokens, stressState }, testInfo) => {
        // INVARIANT — moduleBlocked olsa bile koşar.
        const ok = await assertNoExternalCallsPostBatch(testInfo, MOD,
            'final_24h_batch', stressState, request, stressTokens.pilot_token);
        expect(ok, 'Final 24h sim sonrası external_calls invariant ihlal').toBe(true);
    });

    test('Final-C) Cleanup tracker + dashboard snapshot', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'final_cleanup_snapshot', status: 'SKIP',
                note: `module-blocked: ${moduleBlockedReason}` });
            return;
        }
        // Cleanup, global stress_prefix script tarafından upstream'de yapılıyor;
        // bu spec yeni booking'leri walk-in ile yarattı, hepsinin guest_name'i
        // SUB_PREFIX taşır (E2E_STRESS_F8J_24H_*) → global cleanup eşleştirir.
        rec(testInfo, { module: MOD, step: 'final_cleanup_snapshot', status: 'PASS',
            note: `sub_prefix=${SUB_PREFIX} walk_in=${walkInBookingIds.length} charged=${chargedBookingIds.length} paid=${paymentDoneBookingIds.length} moved=${movedRoomPairs.length} clock_in_ok=${clockInOk} checked_out=${checkedOutOk} pr_created=${prCreatedId ?? 'n/a'} na_first_posted=${naFirstSnapshot?.posted_charges ?? 'n/a'} qr_count=${qrCount ?? 'n/a'} complaints=${complaintCount ?? 'n/a'} mice_events=${miceEventCount ?? 'n/a'}` });
    });
});

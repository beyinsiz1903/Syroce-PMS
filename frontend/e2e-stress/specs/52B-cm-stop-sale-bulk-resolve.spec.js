// F8L v2 § 52B — Stop-sale Circuit Breaker + Conflict Queue Bulk Resolve
// Stress Parity (Task #6 — CM-Hardening Turu #2 + #4 parity).
//
// Backend hardening kapsamı (DONE; bkz. docs/adr/2026-05-cm-hardening.md):
//   - Turu #2: POST /api/channel-manager/conflict-queue/bulk-resolve
//             (partial-success isolation, dedupe last-room-wins, max 50)
//   - Turu #4: GET  /api/channel-manager/unified-rate-manager/circuit-breakers
//             (per-connection, tenant-prefixed keys; foreign tenant key
//              suffix'leri response'a sızmaz)
//
// Threat-model surface (threat_model.md):
//   - § Information Disclosure: CB endpoint tenant-scope eksikse foreign
//     `{tenant_id}:connection_id` key'leri leak olur (cross-tenant
//     observability). Bulk-resolve list endpoint'i pending booking'lerin
//     guest PII alanlarını taşır — leak P0.
//   - § Tampering: bulk-resolve write surface; stress_token + pilot
//     booking_id ile bir hamlede pilot tenant'ın booking state'ini
//     değiştirmek mümkün olursa P0 (cross-tenant IDOR + integrity).
//   - § Elevation of Privilege: anon → 401/403 contract; stress_token'da
//     `view_system_diagnostics` veya `edit_booking` perm'i yoksa endpoint
//     reject etmeli.
//
// Mutlak kurallar (F8L doctrine, 50/51/52 mirror):
//   - pilot mutation YOK (drift=0): hiçbir write pilot tenant'a gitmez;
//     pilot_token sadece read-only baseline + cross-tenant IDOR negative
//     control için kullanılır.
//   - external_calls=[] (post-batch). CB read pure-mem ops; bulk-resolve
//     room_night_locks atomic insert — outbound HTTP tetiklemez.
//   - failedTests=0, P0=P1=0.
//
// Module-blocked pattern (F8L § 50/51/52 mirror):
//   - GET circuit-breakers veya GET conflict-queue non-2xx → ilgili alt-grup
//     SKIP + P2 informational; D-step (pilot_drift + external_calls)
//     bağımsız koşar.
//
// Pending booking seed stratejisi:
//   Backend stress seed (`backend/domains/admin/router/stress.py`)
//   pending_assignment booking üretmez (allocation_source="manual"). Gerçek
//   pending'leri sadece OTA import pipeline (reservation_import_service +
//   BookingConflictError fallback) üretir; bu da stres ortamında EXTERNAL
//   call gerektirir — invariant ihlali. Bu yüzden bulk-resolve happy-path
//   "real succeeded" coverage'ı için spec önce GET /conflict-queue ile
//   stres tenant'ta MEVCUT pending booking var mı diye bakar; varsa
//   gerçek partial-success (1 ok + 1 bogus room) koşar, yoksa P2 REVIEW
//   bırakır. ERROR-PATH coverage (room_not_found, not_pending, dedup,
//   max 50, RBAC, anon, P0 cross-tenant IDOR) sentetik ID'lerle deterministic
//   doğrulanır — gerçek pending bookinge ihtiyaç yok.
//
// Cleanup: spec stres tenant pending'ini resolve EDERSE, succeeded
// booking'i cancelled'a çekmez (pending → front_desk_resolve geçişi gerçek
// front-desk yolu; cleanup yalnız STRESS_COLLECTIONS unified sweep'e
// güvenir — booking + room_night_locks zaten kapsamda). Spec stres-prefix
// olmayan booking'lere asla dokunmaz.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, pilotBookingsCount,
    fetchSingle,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'cm_stop_sale_bulk_resolve';
const CB_PATH = '/api/channel-manager/unified-rate-manager/circuit-breakers';
const CQ_PATH = '/api/channel-manager/conflict-queue';
const BR_PATH = '/api/channel-manager/conflict-queue/bulk-resolve';

test.describe.configure({ mode: 'serial' });

test.describe('F8L v2 § 52B — Stop-sale CB + Bulk Resolve', () => {
    let pilotBefore = null;
    let prefix = null;
    let stressTid = null;
    let pilotTid = null;
    let cbBlocked = false;
    let cbBlockedReason = null;
    let cqBlocked = false;
    let cqBlockedReason = null;
    let stressRoomId = null;
    let existingPendingId = null;
    let pilotSampleBookingId = null;
    let cqProbeDiag = null;

    test('Setup: prefix + pilot baseline + CB/CQ probe + room sample + pending probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // 1) Circuit-breakers probe — stress_token, RBAC view_system_diagnostics.
        const cbProbe = await callTimed(request, 'get', CB_PATH, undefined, stressTokens.stress_token);
        if (!cbProbe.ok) {
            cbBlocked = true;
            cbBlockedReason = `cb_probe_non2xx_${cbProbe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Circuit-breakers endpoint probe non-2xx',
                `GET ${CB_PATH} status=${cbProbe.status} body=${JSON.stringify(cbProbe.body).slice(0, 160)} — view_system_diagnostics RBAC veya router deploy. CB alt-grubu skipped; D-step bağımsız.`);
        }

        // 2) Conflict-queue probe — stress_token, RBAC edit_booking.
        const cqProbe = await callTimed(request, 'get', `${CQ_PATH}?limit=50`,
            undefined, stressTokens.stress_token);
        if (!cqProbe.ok) {
            cqBlocked = true;
            cqBlockedReason = `cq_probe_non2xx_${cqProbe.status}`;
            recFinding(testInfo, 'P2', MOD, 'Conflict-queue endpoint probe non-2xx',
                `GET ${CQ_PATH} status=${cqProbe.status} body=${JSON.stringify(cqProbe.body).slice(0, 160)} — edit_booking RBAC veya router deploy. Bulk-resolve alt-grubu skipped; D-step bağımsız.`);
        } else {
            const items = cqProbe.body?.items || [];
            // Task #25: global-setup seeds N synthetic pending_assignment bookings
            // (room_id:null, status:confirmed) so a real partial-success can run.
            // Capture the first item carrying an id as the live happy-path sample.
            // (The old "cross-round seed yok → boş gelir" assumption predates the
            // Task #25 seeding and is obsolete — test G no longer relies on it.)
            for (const it of items) {
                if (it.id) { existingPendingId = it.id; break; }
            }
            // Self-diagnostic: the conflict-queue list is paginated + created_at
            // DESC, so the seeded rows can be absent from page 1 (depletion,
            // shadowing by newer pending, or a list-shape drift). Log the queue
            // shape + whether the persisted seeded ids appear on this page so a
            // root cause is decidable on the NEXT run instead of ~1.3h later
            // inside test G. test G falls back to the persisted seeded ids +
            // full-detail re-verify, so this never fake-greens.
            const seededIds = Array.isArray(stressState?.seeded_pending_ids) ? stressState.seeded_pending_ids : [];
            const itemsWithId = items.filter((it) => it.id).length;
            const cqTotal = typeof cqProbe.body?.total === 'number' ? cqProbe.body.total : null;
            const seededOnPage = seededIds.filter((sid) => items.some((it) => it.id === sid)).length;
            cqProbeDiag = { total: cqTotal, items: items.length, items_with_id: itemsWithId, seeded_ids: seededIds.length, seeded_on_page: seededOnPage };
            if (!existingPendingId) {
                recFinding(testInfo, 'P2', MOD, 'Conflict-queue live pending scan empty',
                    `GET ${CQ_PATH}?limit=50 → total=${cqTotal} items=${items.length} items_with_id=${itemsWithId} seeded_ids=${seededIds.length} seeded_on_page=${seededOnPage}. Live capture empty → test G falls back to persisted seeded_pending_ids + full-detail re-verify (no fake-green).`);
            }
        }

        // 3) Stress room sample (room_not_found vs valid room ayrımı için).
        const roomsRes = await fetchSingle(request, stressTokens.stress_token,
            '/api/pms/rooms?limit=5');
        if (roomsRes.list && roomsRes.list.length > 0) {
            // Stres tenant'taki herhangi bir oda yeterli; prefix match şart değil
            // çünkü bulk-resolve "room belongs to this tenant" guard'ı tenant_id
            // üzerinden çalışır, prefix'e bakmaz.
            stressRoomId = roomsRes.list[0].id;
        }

        // 4) Pilot booking sample — cross-tenant IDOR negative control için.
        try {
            const b = await callTimed(request, 'get', '/api/pms/bookings?limit=1',
                undefined, stressTokens.pilot_token);
            if (b.ok) {
                const list = Array.isArray(b.body) ? b.body
                    : (b.body?.bookings || b.body?.items || []);
                if (list[0]) pilotSampleBookingId = list[0].id || list[0]._id;
            }
        } catch (_) { /* best-effort */ }

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} cb_blocked=${cbBlocked} cq_blocked=${cqBlocked} stress_room=${!!stressRoomId} existing_pending=${!!existingPendingId} pilot_sample=${!!pilotSampleBookingId} cq_diag=${JSON.stringify(cqProbeDiag)}` });
    });

    // ──────────────────────────────────────────────────────────────────
    //  A) Stop-sale Circuit Breaker — tenant-scope contract
    // ──────────────────────────────────────────────────────────────────
    test('A) Circuit-breakers — shape + tenant-scope + token/PII guard', async ({ request, stressTokens }, testInfo) => {
        if (cbBlocked) {
            rec(testInfo, { module: MOD, step: 'cb_shape', status: 'SKIP', note: `cb blocked: ${cbBlockedReason}` });
            test.skip(true, 'cb blocked');
            return;
        }
        const r = await callTimed(request, 'get', CB_PATH, undefined, stressTokens.stress_token);
        if (!r.ok) {
            rec(testInfo, { module: MOD, step: 'cb_shape', status: 'REVIEW', http: r.status, note: `re-probe fail status=${r.status}` });
            return;
        }
        const breakers = r.body?.breakers;
        const shapeOk = Array.isArray(breakers);
        // Backend default: 2 breaker (hotelrunner + exely), bir touch yoksa CLOSED.
        const providers = shapeOk ? breakers.map((b) => b.provider).sort() : [];
        const providersOk = JSON.stringify(providers) === JSON.stringify(['exely', 'hotelrunner']);

        // Tenant-scope leak guard: connection_id alanı tenant prefix'siz dönmeli
        // (backend `local_conn_suffix = conn_id[len(tenant_id)+1:]` strip yapar).
        // Stres response'unda full `{stressTid}:` prefix ya da pilot_tid substring
        // ASLA görünmemeli.
        const blob = JSON.stringify(r.body);
        const stressPrefixLeak = stressTid ? blob.includes(`${stressTid}:`) : false;
        const pilotTidLeak = pilotTid ? blob.includes(pilotTid) : false;
        const leakDetected = stressPrefixLeak || pilotTidLeak;

        // Per-breaker connection_id alanı tenant prefix'li olmamalı.
        let connIdLeaks = [];
        if (shapeOk) {
            for (const b of breakers) {
                const cid = b.connection_id ?? '';
                if (typeof cid === 'string' && stressTid && cid.startsWith(`${stressTid}:`)) {
                    connIdLeaks.push(cid);
                }
            }
        }

        const pass = shapeOk && providersOk && !leakDetected && connIdLeaks.length === 0;
        rec(testInfo, { module: MOD, step: 'cb_shape',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: `GET ${CB_PATH}`, http: r.status,
            note: `shape_ok=${shapeOk} providers=${JSON.stringify(providers)} stress_prefix_leak=${stressPrefixLeak} pilot_tid_leak=${pilotTidLeak} conn_id_leaks=${connIdLeaks.length}` });

        if (leakDetected) {
            recFinding(testInfo, 'P0', MOD,
                'Circuit-breakers response\'unda tenant prefix/cross-tenant leak',
                `stress_prefix_leak=${stressPrefixLeak} pilot_tid_leak=${pilotTidLeak} body=${blob.slice(0, 280)}. Backend local_conn_suffix strip mantığı kırık veya foreign breaker key sızıyor. Threat-model § Information Disclosure.`);
        }
        if (connIdLeaks.length > 0) {
            recFinding(testInfo, 'P0', MOD,
                'Circuit-breakers connection_id alanı tenant prefix\'i taşıyor',
                `connection_id leaks=${JSON.stringify(connIdLeaks)}. Backend local_conn_suffix strip mantığı kırık.`);
        }

        // PII + token guard — breaker payload provider/last_failure içerir;
        // credential/JWT/PII içermemeli.
        assertPiiMasked(testInfo, MOD, r.body, ['phone', 'email', 'identity_number', 'guest_phone']);
        assertNoTokenLeak(testInfo, MOD, r.body, 'cb_breakers_list');
    });

    test('A2) Circuit-breakers — anonymous deny (401/403)', async ({ request }, testInfo) => {
        if (cbBlocked) {
            rec(testInfo, { module: MOD, step: 'cb_anon', status: 'SKIP', note: `cb blocked: ${cbBlockedReason}` });
            test.skip(true, 'cb blocked');
            return;
        }
        const r = await callTimed(request, 'get', CB_PATH, undefined, '');
        const denyOk = r.status === 401 || r.status === 403;
        rec(testInfo, { module: MOD, step: 'cb_anon',
            status: denyOk ? 'PASS' : 'FAIL',
            endpoint: `GET ${CB_PATH} (no auth)`, http: r.status,
            note: `expected=401/403 got=${r.status}` });
        if (r.status >= 200 && r.status < 300) {
            recFinding(testInfo, 'P0', MOD,
                'Circuit-breakers anonymous disclosure',
                `GET ${CB_PATH} no-auth status=${r.status} + data. Auth guard yok. Threat-model § Elevation of Privilege.`);
        }
    });

    // ──────────────────────────────────────────────────────────────────
    //  B) Bulk Resolve — partial-failure isolation + error parity
    // ──────────────────────────────────────────────────────────────────
    test('B) Bulk-resolve — partial isolation (room_not_found + not_pending parity)', async ({ request, stressTokens }, testInfo) => {
        if (cqBlocked) {
            rec(testInfo, { module: MOD, step: 'br_partial', status: 'SKIP', note: `cq blocked: ${cqBlockedReason}` });
            test.skip(true, 'cq blocked');
            return;
        }
        // Sentetik ID'ler: ikisi de pending değil → her ikisi de failed[]'a düşer.
        // Biri valid stres odasıyla (not_pending), biri bogus room ile
        // (room_not_found). PARTIAL-FAILURE ISOLATION sözleşmesi: tek
        // request, iki bağımsız sonuç; biri diğerinin işlemini etkilemez.
        const bogusBookingA = `${prefix || 'STRESS'}_BR_NOTPENDING_${Date.now()}`;
        const bogusBookingB = `${prefix || 'STRESS'}_BR_NOROOM_${Date.now()}`;
        const items = [
            { booking_id: bogusBookingA, room_id: stressRoomId || 'BOGUS_ROOM_X' },
            { booking_id: bogusBookingB, room_id: 'STRESS_NONEXISTENT_ROOM_999' },
        ];
        const r = await callTimed(request, 'post', BR_PATH, { items }, stressTokens.stress_token);
        if (!r.ok) {
            rec(testInfo, { module: MOD, step: 'br_partial', status: 'FAIL', http: r.status,
                note: `expected 200 partial-success body, got ${r.status} body=${JSON.stringify(r.body).slice(0, 160)}` });
            recFinding(testInfo, 'P1', MOD,
                'Bulk-resolve partial-failure isolation contract — 200 dönmedi',
                `POST ${BR_PATH} status=${r.status}. Per-item failure 200 + failed[] yerine top-level error attı.`);
            return;
        }
        const succeeded = r.body?.succeeded || [];
        const failed = r.body?.failed || [];
        const total = r.body?.total;

        // Her iki entry de failed'a düşmeli. Eğer stressRoomId yoksa A da
        // room_not_found alır (yine isolation OK).
        const failedIds = failed.map((f) => f.booking_id);
        const aFailed = failedIds.includes(bogusBookingA);
        const bFailed = failedIds.includes(bogusBookingB);

        // Hata kodları beklenenler:
        //   A: stressRoomId varsa → not_pending; yoksa → room_not_found
        //   B: room_not_found (her zaman, bogus room)
        const aEntry = failed.find((f) => f.booking_id === bogusBookingA);
        const bEntry = failed.find((f) => f.booking_id === bogusBookingB);
        const aErrExpected = stressRoomId ? 'not_pending' : 'room_not_found';
        const aErrOk = aEntry?.error === aErrExpected;
        const bErrOk = bEntry?.error === 'room_not_found';

        const totalOk = total === 2;
        const succeededOk = succeeded.length === 0;
        const pass = aFailed && bFailed && aErrOk && bErrOk && totalOk && succeededOk;

        rec(testInfo, { module: MOD, step: 'br_partial',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: `POST ${BR_PATH}`, http: r.status,
            note: `total=${total} succeeded=${succeeded.length} failed=${failed.length} a_err=${aEntry?.error}(want=${aErrExpected}) b_err=${bEntry?.error}(want=room_not_found)` });

        if (!pass) {
            recFinding(testInfo, 'P1', MOD,
                'Bulk-resolve partial-failure isolation contract drift',
                `Body=${JSON.stringify(r.body).slice(0, 320)}. Beklenen: 2 item failed (a=${aErrExpected}, b=room_not_found), succeeded=0. Gerçek ifşa edildi.`);
        }

        // Token leak guard — failed[] entry'leri internal state taşımamalı.
        assertNoTokenLeak(testInfo, MOD, r.body, 'br_partial_response');
    });

    test('C) Bulk-resolve — duplicate booking_id dedup (last room_id wins)', async ({ request, stressTokens }, testInfo) => {
        if (cqBlocked) {
            rec(testInfo, { module: MOD, step: 'br_dedup', status: 'SKIP', note: `cq blocked: ${cqBlockedReason}` });
            test.skip(true, 'cq blocked');
            return;
        }
        const dupBookingId = `${prefix || 'STRESS'}_BR_DEDUP_${Date.now()}`;
        const roomA = 'STRESS_DEDUP_ROOM_A_999';
        const roomB = 'STRESS_DEDUP_ROOM_B_999';
        // Aynı booking_id 3 kez, farklı room_id'lerle — backend dedup map
        // last-write-wins, yani sadece roomB ile 1 entry görünmeli.
        const items = [
            { booking_id: dupBookingId, room_id: roomA },
            { booking_id: dupBookingId, room_id: roomA },
            { booking_id: dupBookingId, room_id: roomB },
        ];
        const r = await callTimed(request, 'post', BR_PATH, { items }, stressTokens.stress_token);
        if (!r.ok) {
            rec(testInfo, { module: MOD, step: 'br_dedup', status: 'FAIL', http: r.status,
                note: `dedup test expected 200 got ${r.status}` });
            return;
        }
        const failed = r.body?.failed || [];
        const succeeded = r.body?.succeeded || [];
        const total = r.body?.total;
        const dupEntries = failed.filter((f) => f.booking_id === dupBookingId);

        // Contract: total = 1 (dedup edildi), dupEntries.length = 1, room_id = roomB.
        const totalOk = total === 1;
        const dedupOk = dupEntries.length === 1;
        const lastWinsOk = dupEntries[0]?.room_id === roomB;
        const noSucceededOk = succeeded.length === 0;
        const pass = totalOk && dedupOk && lastWinsOk && noSucceededOk;

        rec(testInfo, { module: MOD, step: 'br_dedup',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: `POST ${BR_PATH}`, http: r.status,
            note: `total=${total}(want=1) dup_entries=${dupEntries.length}(want=1) last_room=${dupEntries[0]?.room_id}(want=${roomB}) succeeded=${succeeded.length}` });

        if (!pass) {
            recFinding(testInfo, 'P1', MOD,
                'Bulk-resolve duplicate booking_id dedup contract drift',
                `Body=${JSON.stringify(r.body).slice(0, 320)}. Aynı booking_id 3x → backend last-room-wins dedup tutmadı. Self-conflict race riski.`);
        }
    });

    test('D) Bulk-resolve — max 50 limit (51 items → 422)', async ({ request, stressTokens }, testInfo) => {
        if (cqBlocked) {
            rec(testInfo, { module: MOD, step: 'br_max_limit', status: 'SKIP', note: `cq blocked: ${cqBlockedReason}` });
            test.skip(true, 'cq blocked');
            return;
        }
        const items = [];
        for (let i = 0; i < 51; i++) {
            items.push({ booking_id: `${prefix || 'STRESS'}_BR_OVER_${i}`, room_id: `BOGUS_${i}` });
        }
        const r = await callTimed(request, 'post', BR_PATH, { items }, stressTokens.stress_token);
        // Pydantic max_length=50 → 422 beklenir. Backend non-validation fail
        // (400/500) tutmazsa contract drift.
        const limitOk = r.status === 422;
        rec(testInfo, { module: MOD, step: 'br_max_limit',
            status: limitOk ? 'PASS' : 'FAIL',
            endpoint: `POST ${BR_PATH} (51 items)`, http: r.status,
            note: `expected=422 got=${r.status} body=${JSON.stringify(r.body).slice(0, 160)}` });
        if (r.status >= 200 && r.status < 300) {
            recFinding(testInfo, 'P1', MOD,
                'Bulk-resolve max_length=50 contract bypass',
                `51 item POST status=${r.status} (accept edildi). Backend Pydantic max_length validator çalışmıyor. DoS surface.`);
        }
    });

    test('E) Bulk-resolve — anonymous deny + RBAC contract', async ({ request, stressTokens }, testInfo) => {
        if (cqBlocked) {
            rec(testInfo, { module: MOD, step: 'br_auth', status: 'SKIP', note: `cq blocked: ${cqBlockedReason}` });
            test.skip(true, 'cq blocked');
            return;
        }
        const payload = { items: [{ booking_id: 'STRESS_ANON_X', room_id: 'STRESS_ANON_R' }] };
        const anon = await callTimed(request, 'post', BR_PATH, payload, '');
        const anonOk = anon.status === 401 || anon.status === 403;
        rec(testInfo, { module: MOD, step: 'br_anon',
            status: anonOk ? 'PASS' : 'FAIL',
            endpoint: `POST ${BR_PATH} (no auth)`, http: anon.status,
            note: `expected=401/403 got=${anon.status}` });
        if (anon.status >= 200 && anon.status < 300) {
            recFinding(testInfo, 'P0', MOD,
                'Bulk-resolve anonymous mutation surface',
                `POST ${BR_PATH} no-auth status=${anon.status}. edit_booking RBAC guard bypass. Threat-model § Elevation of Privilege + Tampering.`);
        }
    });

    test('F) Bulk-resolve — P0 cross-tenant IDOR (stress token + pilot booking_id)', async ({ request, stressTokens }, testInfo) => {
        if (cqBlocked) {
            rec(testInfo, { module: MOD, step: 'br_idor', status: 'SKIP', note: `cq blocked: ${cqBlockedReason}` });
            test.skip(true, 'cq blocked');
            return;
        }
        if (!pilotSampleBookingId) {
            rec(testInfo, { module: MOD, step: 'br_idor', status: 'REVIEW',
                note: 'pilot booking sample alınamadı — IDOR negative control koşamadı' });
            recFinding(testInfo, 'P2', MOD,
                'Cross-tenant IDOR negative control için pilot booking sample yok',
                `pilot_token /api/pms/bookings boş döndü; IDOR contract bu run\'da assert edilemedi. Pilot baseline'a en az 1 booking ekleyin.`);
            return;
        }
        const stressRoom = stressRoomId || `${prefix || 'STRESS'}_ANY_ROOM`;
        const payload = { items: [{ booking_id: pilotSampleBookingId, room_id: stressRoom }] };
        // Stres token + pilot booking_id → backend `PENDING_QUERY + tenant_id=stress_tid`
        // filtresi gereği find_one null döner → failed[] entry "not_pending".
        // Succeeded'da pilot booking görünürse VEYA pilot booking_id'nin pilot
        // tenant'taki room_id'si değişirse P0.
        const r = await callTimed(request, 'post', BR_PATH, payload, stressTokens.stress_token);

        // Best-effort: pilot booking'in mevcut room_id'sini baseline al.
        let pilotRoomBefore = null;
        try {
            const b = await callTimed(request, 'get', `/api/pms/bookings/${pilotSampleBookingId}`,
                undefined, stressTokens.pilot_token);
            if (b.ok) pilotRoomBefore = b.body?.room_id ?? null;
        } catch (_) { /* best-effort */ }

        let succeeded = r.body?.succeeded || [];
        const failed = r.body?.failed || [];
        const pilotInSucceeded = succeeded.some((s) => s.booking_id === pilotSampleBookingId);

        // Post-check: pilot booking'in room_id'si değişti mi?
        let pilotRoomAfter = pilotRoomBefore;
        let driftDetected = false;
        try {
            const b = await callTimed(request, 'get', `/api/pms/bookings/${pilotSampleBookingId}`,
                undefined, stressTokens.pilot_token);
            if (b.ok) pilotRoomAfter = b.body?.room_id ?? null;
            if (pilotRoomBefore !== null && pilotRoomAfter !== pilotRoomBefore) {
                driftDetected = true;
            }
        } catch (_) { /* best-effort */ }

        // 4xx beklenir DEĞİL (200 + failed[]); ama eğer 4xx dönerse de OK
        // (defense-in-depth — endpoint hiç işlemedi).
        const httpOk = r.ok || (r.status >= 400 && r.status < 500);
        const isolationOk = !pilotInSucceeded && !driftDetected;
        const pass = httpOk && isolationOk;

        rec(testInfo, { module: MOD, step: 'br_idor',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: `POST ${BR_PATH} (stress→pilot)`, http: r.status,
            note: `pilot_sample=${pilotSampleBookingId.slice(0, 12)}… pilot_in_succeeded=${pilotInSucceeded} pilot_room_before=${pilotRoomBefore} pilot_room_after=${pilotRoomAfter} drift=${driftDetected}` });

        if (pilotInSucceeded || driftDetected) {
            recFinding(testInfo, 'P0', MOD,
                'Bulk-resolve cross-tenant IDOR — stress token pilot booking\'i resolve etti',
                `pilot_sample=${pilotSampleBookingId} stress_token ile bulk-resolve → pilot_in_succeeded=${pilotInSucceeded} pilot_room_before=${pilotRoomBefore} pilot_room_after=${pilotRoomAfter}. Tenant filter (PENDING_QUERY + tenant_id) bypass. Threat-model § Tampering + Information Disclosure.`);
        }
    });

    test('G) Bulk-resolve — real partial-success (deterministic; seeded pending)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (cqBlocked) {
            rec(testInfo, { module: MOD, step: 'br_real_partial', status: 'SKIP', note: `cq blocked: ${cqBlockedReason}` });
            test.skip(true, 'cq blocked');
            return;
        }
        // F8L v2 (Task #25): global-setup.js seeds N synthetic pending_assignment
        // bookings via the stress seed endpoint (`seed_pending_bookings`) so this
        // test asserts the real succeeded[]/failed[] partial-success contract on
        // every run instead of degrading to an informational P2 review. The
        // seeded bookings carry stress_seed=True + stress_prefix=<prefix> and
        // a far-future stay window, so `_claim_room_for_pending_booking` cannot
        // collide with the baseline RNLs on any stress room.
        // Resolve a REAL still-pending booking deterministically. Prefer the live
        // conflict-queue sample (existingPendingId); fall back to the authoritative
        // seeded ids persisted by global-setup at seed time (when they provably
        // matched PENDING_QUERY + stress_prefix). The live page-1 scan can miss them
        // (pagination / created_at DESC / shadowing) while the rows still exist.
        const seededPendingIds = Array.isArray(stressState?.seeded_pending_ids) ? stressState.seeded_pending_ids : [];
        const candidateIds = [...new Set([existingPendingId, ...seededPendingIds].filter(Boolean))];
        if (candidateIds.length === 0) {
            rec(testInfo, { module: MOD, step: 'br_real_partial', status: 'FAIL',
                note: 'no_candidate_pending — neither live conflict-queue nor persisted seeded_pending_ids yielded a pending id (global-setup seed/persist regression)' });
            recFinding(testInfo, 'P1', MOD,
                'Bulk-resolve real-succeeded seed missing',
                `Neither GET ${CQ_PATH} nor stressState.seeded_pending_ids produced a candidate although global-setup hard-asserts seed_pending_bookings>0 + queryable>0. `+
                `Check backend stress seed (pending_bookings_docs / post_insert_verification.pending_ids) and global-setup persistence.`);
            expect(candidateIds.length, 'seed_pending_bookings must produce at least one candidate pending id').toBeGreaterThan(0);
            return;
        }
        // Re-verify each candidate's CURRENT state via full-detail; pick the first
        // that is still pending (room_id empty + status in the accepted set). On
        // failure this also captures EXACTLY how each consumed candidate now looks.
        let resolvedPendingId = null;
        const candidateStates = [];
        for (const cid of candidateIds) {
            const det = await callTimed(request, 'get',
                `/api/pms/reservations/${encodeURIComponent(cid)}/full-detail`,
                undefined, stressTokens.stress_token);
            const bk = det.ok ? (det.body?.booking || {}) : {};
            // Mirror backend PENDING_QUERY EXACTLY: allocation_source=pending_assignment
            // + room_id empty + status in the accepted set. Omitting allocation_source
            // could falsely pick a row whose allocation drifted while room_id stayed
            // empty, then bulk-resolve would reject it as not_pending — masking the
            // real "consumed" signal. (cm_conflict_queue.PENDING_QUERY)
            const stillPending = det.ok && !bk.room_id
                && bk.allocation_source === 'pending_assignment'
                && ['confirmed', 'guaranteed', 'pending'].includes(bk.status);
            candidateStates.push({ id: cid, http: det.status,
                room_id: det.ok ? (bk.room_id ?? null) : undefined,
                status: det.ok ? (bk.status ?? null) : undefined,
                allocation_source: det.ok ? (bk.allocation_source ?? null) : undefined,
                pending: stillPending });
            if (stillPending) { resolvedPendingId = cid; break; }
        }
        if (!resolvedPendingId) {
            // Every seeded/live candidate exists but is NO LONGER pending (room
            // assigned / status or allocation changed) — a genuine test-isolation
            // or external-mutation defect. Task #25 made this precondition
            // deterministic, so this is a HARD FAIL with the consumed-state
            // evidence inlined (NOT a REVIEW / skip-as-pass).
            rec(testInfo, { module: MOD, step: 'br_real_partial', status: 'FAIL',
                note: `pending_consumed — none of ${candidateIds.length} candidates still pending: ${JSON.stringify(candidateStates).slice(0, 300)}` });
            recFinding(testInfo, 'P1', MOD,
                'Seeded pending consumed before bulk-resolve',
                `global-setup proved pending rows existed at seed (queryable + CQ probe), but by test-G time none remain pending. `+
                `Candidate current states (room_id/status): ${JSON.stringify(candidateStates).slice(0, 400)}. `+
                `A spec or background path mutated a far-future pending_assignment booking (claimed a room / changed status / allocation_source). Investigate test isolation.`);
            expect(resolvedPendingId, 'at least one seeded pending booking must still be pending at bulk-resolve time').toBeTruthy();
            return;
        }
        if (!stressRoomId) {
            rec(testInfo, { module: MOD, step: 'br_real_partial', status: 'FAIL',
                note: 'no_stress_room — baseline seed should expose at least one room via /api/pms/rooms' });
            expect(stressRoomId, 'stress room sample required for real-succeeded path').toBeTruthy();
            return;
        }
        // Deterministic partial-success: 1 valid pending + 1 bogus room_id.
        const bogusBooking = `${prefix || 'STRESS'}_BR_REAL_BOGUS_${Date.now()}`;
        const items = [
            { booking_id: resolvedPendingId, room_id: stressRoomId },
            { booking_id: bogusBooking, room_id: 'STRESS_NONEXISTENT_ROOM_999' },
        ];
        const r = await callTimed(request, 'post', BR_PATH, { items }, stressTokens.stress_token);
        const succeeded = r.body?.succeeded || [];
        const failed = r.body?.failed || [];
        const realInSucceeded = succeeded.some((s) => s.booking_id === resolvedPendingId && s.room_id === stressRoomId);
        const bogusInFailed = failed.some((f) => f.booking_id === bogusBooking && f.error === 'room_not_found');
        const totalOk = r.body?.total === 2;
        const succeededCountOk = succeeded.length === 1;
        const failedCountOk = failed.length === 1;
        const pass = r.ok && realInSucceeded && bogusInFailed && totalOk && succeededCountOk && failedCountOk;

        rec(testInfo, { module: MOD, step: 'br_real_partial',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: `POST ${BR_PATH}`, http: r.status,
            note: `real_in_succeeded=${realInSucceeded} bogus_in_failed=${bogusInFailed} total=${r.body?.total} succeeded=${succeeded.length}(want=1) failed=${failed.length}(want=1)` });

        if (!pass) {
            recFinding(testInfo, 'P1', MOD,
                'Bulk-resolve real partial-success contract drift',
                `Body=${JSON.stringify(r.body).slice(0, 320)}. Expected 1 succeeded (pending=${resolvedPendingId} → room=${stressRoomId}) + 1 failed (bogus_room=room_not_found), total=2.`);
        }

        expect(r.status, 'bulk-resolve should return 200 for partial-success').toBe(200);
        expect(succeeded.length, 'exactly 1 succeeded entry expected').toBe(1);
        expect(failed.length, 'exactly 1 failed entry expected').toBe(1);
        expect(realInSucceeded, 'seeded pending booking must appear in succeeded[]').toBe(true);
        expect(bogusInFailed, 'bogus room_id must surface as room_not_found in failed[]').toBe(true);
        expect(r.body?.total, 'total must reflect dedup\'d item count').toBe(2);
    });

    // ──────────────────────────────────────────────────────────────────
    //  Z) Invariants — pilot_drift + external_calls
    // ──────────────────────────────────────────────────────────────────
    test('Z) external_calls invariant + pilot_drift=0', async ({ request, stressTokens }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'cm_stop_sale_bulk_resolve_done', stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });
});

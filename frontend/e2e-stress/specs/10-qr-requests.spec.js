// F8B § 10 — Room QR requests: public submit, staff transitions, SLA/overdue,
// token guard, external_calls invariant, pilot drift.
//
// Tasarım notları:
// - Public QR submit token gerektirir: /api/rooms/{id}/qr-code → token (HMAC).
//   Stress tenant'taki gerçek odalardan farklı 50 oda kullanılır (rate-limit
//   20/10min per room+IP; aynı oda 20'yi aşarsa 429). Token bulk endpoint
//   tek istekle 500 oda için döner → setup ucuz.
// - Staff transitions seed'den gelen 'new' QR'ları kullanır (her oda için 1).
// - SLA/overdue: seed'de %25 oranında ~25h yaşlı QR var → liste endpoint
//   stats üzerinden non-zero open count bekleriz.
// - external_calls invariant: assertNoExternalCallsPostBatch — QR submit
//   ve PATCH yalnız local Mongo yazar, dispatcher tetiklenmez.
// - Pilot drift = 0: tüm yazma stress tenant'a, pilot bookings sayısı sabit.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    fetchAllByPrefix, fetchSingle, callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'qr_requests';

test.describe.configure({ mode: 'serial' });

test.describe('F8B § 10 — Room QR requests', () => {
    let rooms = [];
    let qrSeed = [];
    let pilotBefore = null;

    test('Setup: fetch rooms + seeded QR requests + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        const prefix = stressState.data_prefix;
        // CI 2026-05-28 NO-GO follow-up (mirror 03/05 fix): `?include_virtual=true`
        // backend `pms_rooms.py:289` use_cache koşulunu false yapar → cache_warmer'ın
        // stress_prefix'siz projection (`cache_warmer.py:176-179`) drop'undan kaçar.
        rooms = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/rooms?include_virtual=true', 'stress_prefix', prefix);
        const qrList = await fetchSingle(request, stressTokens.stress_token, '/api/room-requests?limit=500');
        qrSeed = Array.isArray(qrList.list) ? qrList.list.filter((r) =>
            typeof r.title === 'string' && r.title.startsWith(prefix)) : [];
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `rooms=${rooms.length} qr_seed_found=${qrSeed.length} pilot_before=${pilotBefore?.count}` });
        expect(rooms.length).toBeGreaterThanOrEqual(50);
        expect(qrSeed.length).toBeGreaterThan(0);
    });

    test('A) 50 public QR submit (different rooms — under per-room RL)', async ({ request, stressTokens, stressState }, testInfo) => {
        // Aynı oda için 20/10min limit → 50 farklı oda kullanılır (rate-limit
        // saf IP+room key olduğundan oda başına 1 submit güvenli kalır).
        // CI #47 fix: per-room `/api/rooms/{id}/qr-code` endpoint PNG üretiyor
        // (slow + bilinmeyen deploy hatasıyla 0/50 token returned). BULK
        // endpoint URL içine HMAC token gömüyor (`?t=TOKEN` param) ve PNG
        // üretmeden 500 oda için tek istek döner. URL'den token parse edip
        // direkt submit'e geç.
        // tur-24 fix: state file actually persists `stress_tid` (see
        // global-setup.js:159); `target_tenant_id` was undefined → URL
        // built as `/api/public/room-qr/undefined/...` → 403 across the
        // board (CI #48 0/50). seed_response.target_tenant_id is the
        // server-side echo and remains as a defensive fallback.
        const stressTid = stressState.stress_tid || stressState.seed_response?.target_tenant_id;
        // tur-24 hard precondition: fail fast if state shape regresses
        // (CI #48 silently built `/undefined/...` URLs → 50× 403).
        expect(stressTid, 'stress tenant id present in state file').toBeTruthy();
        const target = rooms.slice(0, 50);
        if (target.length < 50) {
            rec(testInfo, { module: MOD, step: 'public_submit', status: 'SKIP',
                note: `not enough rooms (${target.length})` });
            return;
        }
        // Bulk token map (1 GET → tüm odalar)
        const bulkR = await request.get('/api/rooms/qr-codes/bulk', {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false, timeout: 60_000,
        });
        const tokenByRoom = {};
        let bulkErr = null;
        if (bulkR.ok()) {
            const j = await bulkR.json().catch(() => null);
            for (const it of (j?.items || [])) {
                const m = typeof it?.url === 'string' ? it.url.match(/[?&]t=([^&]+)/) : null;
                if (m && it.room_id) tokenByRoom[it.room_id] = decodeURIComponent(m[1]);
            }
        } else {
            bulkErr = `bulk_status=${bulkR.status()}`;
        }
        if (Object.keys(tokenByRoom).length === 0) {
            rec(testInfo, { module: MOD, step: 'public_submit', status: 'FAIL',
                endpoint: '/api/rooms/qr-codes/bulk',
                note: `bulk token map boş — ${bulkErr || 'parse failed'}` });
            recFinding(testInfo, 'P1', MOD, 'QR bulk endpoint token map boş',
                `bulk_status=${bulkR.status()} items_with_token=0 — URL'den token parse edilemedi.`);
            expect(Object.keys(tokenByRoom).length, 'bulk token map > 0').toBeGreaterThan(0);
            return;
        }

        let ok = 0, fail = 0, throttled = 0;
        const samples = [];
        const errors = [];
        for (let i = 0; i < target.length; i++) {
            const room = target[i];
            const token = tokenByRoom[room.id];
            if (!token) { fail++; if (errors.length < 3) errors.push({ status: 0, room: room.id, why: 'no_token_in_map' }); continue; }
            const subUrl = `/api/public/room-qr/${stressTid}/${room.id}/submit?t=${encodeURIComponent(token)}`;
            const t0 = Date.now();
            const r = await request.post(subUrl, {
                headers: { 'Origin': process.env.E2E_BASE_URL || 'http://localhost:8000' },
                    data: {
                    category: 'cleaning',
                    description: `F8B public submit ${i}`,
                    priority: 'normal', language: 'tr',
                    guest_name: null, guest_phone: null,
                },
                failOnStatusCode: false, timeout: 15_000,
            });
            samples.push(Date.now() - t0);
            const status = r.status();
            if (status === 200 || status === 201) ok++;
            else if (status === 429) { throttled++; fail++; }
            else {
                fail++;
                if (errors.length < 3) {
                    let bodySnip = '';
                    try { bodySnip = JSON.stringify(await r.json()).slice(0, 100); } catch { /* ignore */ }
                    errors.push({ status, room: room.id, body: bodySnip });
                }
            }
        }
        recPerf(testInfo, MOD, 'public_submit', samples, ok >= 45);
        const passLine = ok >= 45;
        rec(testInfo, { module: MOD, step: 'public_submit', status: passLine ? 'PASS' : 'FAIL',
            endpoint: '/api/public/room-qr/{tid}/{room_id}/submit',
            note: `n=${target.length} ok=${ok} fail=${fail} throttled_429=${throttled} samples_max_ms=${samples.length ? Math.max(...samples) : 0} errs=${JSON.stringify(errors)}` });
        if (!passLine) {
            recFinding(testInfo, 'P1', MOD, 'Public QR submit floor (>=45/50) ihlal',
                `ok=${ok}/${target.length} throttled_429=${throttled} errs=${JSON.stringify(errors)}`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'public_submit_50', stressState, request, stressTokens.pilot_token);
        expect(extOk, 'public_submit_50 sonrası external_calls invariant').toBe(true);
        expect(ok, `public submit ok>=45/50 floor; got ok=${ok} fail=${fail} throttled=${throttled}`).toBeGreaterThanOrEqual(45);
    });

    test('B) 30 staff status transitions (new→assigned→in_progress→completed)', async ({ request, stressTokens, stressState }, testInfo) => {
        // tur-26: 90 PATCH × (latency + gap) baseline ~180s @ 1500ms gap;
        // backoff retries push over default 180s timeout. Bump to 300s.
        test.setTimeout(300_000);
        const open = qrSeed.filter((r) => r.status === 'new').slice(0, 30);
        if (open.length < 5) {
            rec(testInfo, { module: MOD, step: 'transitions', status: 'SKIP',
                note: `open new<5 (have ${open.length})` });
            return;
        }
        const steps = ['assigned', 'in_progress', 'completed'];
        let ok = 0, fail = 0;
        const samples = [];
        // CI #47 throttle: prod write rate-limit = 120/min/token (apm_middleware.py:366).
        // F8B cumulative writes by stress_token: 10-B(90) + 11-B(20) + 12-A(30) + 13-A(50) = 190
        // tek 60s window'da budget aşıyor. tur-24 700ms→ok=83/90, 7×429 retry'sız fail.
        // tur-25 1500ms→test timeout 180s aşıldı (90×(500+1500)=180s baseline + retries).
        // tur-26: 1000ms gap + 300s test budget + callTimed (cap 15s).
        // 60s/1000ms = 60 writes/min ceiling vs 120 prod limit = %50 marj; baseline
        // 90×(500+1000)=135s, retry'lerle worst ~200s, 300s budget güvenli.
        let throttled = 0;
        for (const req of open) {
            for (const next of steps) {
                const r = await callTimed(request, 'patch', `/api/room-requests/${req.id}`, {
                    status: next, note: `F8B transition → ${next}`,
                }, stressTokens.stress_token);
                samples.push(r.ms);
                if (r.throttled) throttled++;
                if (r.ok) ok++; else fail++;
                await new Promise((res) => setTimeout(res, 1000));
            }
        }
        const expectedCalls = open.length * steps.length;
        const floor = Math.ceil(expectedCalls * 0.95);
        recPerf(testInfo, MOD, 'staff_transition', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'staff_transitions', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'PATCH /api/room-requests/{id}',
            note: `n=${open.length} steps=${steps.length} total=${expectedCalls} ok=${ok} fail=${fail} throttled_429=${throttled} floor>=${floor}` });
        if (ok < floor) {
            recFinding(testInfo, 'P1', MOD, 'QR staff transition floor (>=95%) ihlal',
                `${expectedCalls} PATCH attempted; ok=${ok} (<${floor}).`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'staff_transitions', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(ok, `staff transitions floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('C) SLA / overdue surface: stats summary returns non-trivial distribution', async ({ request, stressTokens }, testInfo) => {
        const samples = [];
        let body = null;
        for (let i = 0; i < 3; i++) {
            const r = await callTimed(request, 'get', '/api/room-requests/stats/summary', undefined, stressTokens.stress_token);
            samples.push(r.ms);
            body = r.body;
        }
        recPerf(testInfo, MOD, 'stats_summary', samples, true);
        const total = body?.total ?? 0;
        const open = body?.open ?? 0;
        rec(testInfo, { module: MOD, step: 'stats_summary', status: total > 0 ? 'PASS' : 'REVIEW',
            endpoint: '/api/room-requests/stats/summary',
            note: `total=${total} open=${open} by_status_keys=${Object.keys(body?.by_status || {}).join(',')} by_dept_keys=${Object.keys(body?.by_department || {}).join(',')} max_ms=${Math.max(...samples)}` });
        expect(total).toBeGreaterThan(0);
        if (samples.some((m) => m > 3000)) {
            recFinding(testInfo, 'P3', MOD, 'stats summary yavaş',
                `max=${Math.max(...samples)}ms (>3s). 500-oda dağılımı için izlenmeli.`);
        }
    });

    test('D) Token guard: invalid token → 403; cross-tenant token → 403', async ({ request, stressState }, testInfo) => {
        if (rooms.length === 0) { rec(testInfo, { module: MOD, step: 'token_guard', status: 'SKIP' }); return; }
        const stressTid = stressState.stress_tid || stressState.seed_response?.target_tenant_id;
        expect(stressTid, 'stress tenant id present in state file').toBeTruthy();
        const room = rooms[0];
        // Bad token
        const badUrl = `/api/public/room-qr/${stressTid}/${room.id}?t=deadbeefxxxx`;
        const r1 = await request.get(badUrl, { failOnStatusCode: false, timeout: 10_000 });
        const r1Status = r1.status();
        // Empty token (different from missing — backend requires `t` query param)
        const emptyUrl = `/api/public/room-qr/${stressTid}/${room.id}?t=`;
        const r2 = await request.get(emptyUrl, { failOnStatusCode: false, timeout: 10_000 });
        const r2Status = r2.status();
        const guardOk = r1Status === 403 && (r2Status === 403 || r2Status === 422);
        rec(testInfo, { module: MOD, step: 'token_guard', status: guardOk ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/public/room-qr/{tid}/{rid}',
            note: `bad_token_status=${r1Status} empty_token_status=${r2Status} expected=403`,
        });
        if (!guardOk) {
            recFinding(testInfo, 'P0', MOD, 'QR token guard bypass',
                `Bad token=${r1Status} Empty=${r2Status}. HMAC verify atlanabiliyor.`);
        }
        expect(guardOk).toBe(true);
    });

    test('E) external_calls invariant post-suite', async ({ request, stressTokens, stressState }, testInfo) => {
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'suite_final', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('F) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});

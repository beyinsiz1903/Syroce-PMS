// ─────────────────────────────────────────────────────────────────────────
// F9E § 08B — Housekeeping Live Broadcast + Cleaning-Status Surface stress.
// ─────────────────────────────────────────────────────────────────────────
//
// Otel kullanım senaryosu: kat görevlisi bir odayı "temizliğe başla" der,
// resepsiyon/kat amiri canlı panelde odanın "cleaning"e geçtiğini ANINDA
// görür; temizlik bitince "clean" olur ve panel güncellenir. Bu akış HTTP
// read-only testleriyle yakalanmaz — hem (1) cleaning durum geçişinin
// kalıcı/okunabilir sonucu hem (2) PMS Socket.IO üzerinden gerçek canlı
// yayın frame'i ayrıca stres testi ister.
//
// Backend yüzey:
//   GET  /api/housekeeping/rooms?status=<s>   (enterprise_router.py:187)
//        → housekeeping_status/hk_status filtreler, hk_status döndürür.
//   POST /api/housekeeping/rooms/{id}/start    (enterprise_router.py:215)
//        → housekeeping_status/hk_status='cleaning' + WS broadcast 'cleaning'.
//        RBAC: require_module_v99("housekeeping").
//   POST /api/housekeeping/rooms/{id}/complete (enterprise_router.py:237)
//        body {cleaned_by} → 'clean' + WS broadcast 'clean'. RBAC aynı.
//   PMS Socket.IO: app.mount("/ws"), client path /ws/socket.io, auth:{token}
//        connect → otomatik `pms:{tenant_id}` room join; event
//        `room_status_update` envelope {room_id,status,tenant_id,timestamp}
//        (websocket_server.py:474 broadcast_room_status_update — tenant_id
//        YOKSA drop ⇒ cross-tenant safe).
//
// Senaryolar:
//   A) Cleaning lifecycle (REST read-back, deterministik):
//        start → GET ?status=cleaning içinde oda hk_status='cleaning';
//        complete → GET ?status=clean içinde oda hk_status='clean'.
//   B) Live broadcast (Socket.IO room_status_update frame capture):
//        stress token ile connect → start tetikle → frame yakala.
//        Güvenlik invariantı (HARD): yakalanan frame'in tenant_id'si
//        stress_tid olmalı; pilot_tid LİTERAL sızarsa P0. Frame yakalanamaz
//        veya socket.io-client yoksa → REVIEW (PASS DEĞİL, skip-as-pass YOK).
//   C) Cross-tenant mutation: stress_token PILOT room_id'de start →
//        4xx/404 zorunlu. 2xx = P0 cross-tenant tampering (update_one
//        tenant filtresi matched_count==0 → 404 beklenir).
//   D) Final invariants: pilot_drift=0 + external_calls=[].
//
// Mutlak kurallar (F9 doctrine):
//   - external_calls = []  (assertNoExternalCallsPostBatch after batch)
//   - pilot mutation = 0   (assertPilotDriftZero)
//   - P0 = P1 = 0; 5xx = 0; skip-as-pass YOK
//   - Module-blocked (RBAC housekeeping yok / oda yok) → A/B SKIP + P2 REVIEW;
//     C (security) bağımsız çalışır.
//   - Mutasyon SADECE stress-tenant scope; pilot tarafı yalnız read-only.
//
// Reporter satırı: `housekeeping_live`.
// ─────────────────────────────────────────────────────────────────────────

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    fetchAllByPrefix, callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, harvestWindow,
} from '../fixtures/stress-helpers.js';

const MOD = 'housekeeping_live';
const GAP_MS = 1000;

// socket.io-client optional — yoksa B SKIP (REVIEW), A/C/D bağımsız.
let SIO = null;
async function ensureSocketIo() {
    if (SIO) return SIO;
    try {
        SIO = (await import('socket.io-client')).io || (await import('socket.io-client')).default;
        return SIO;
    } catch (e) {
        return null;
    }
}

// PMS Socket.IO frame capture probe. connectTimeoutMs içinde bağlanır, varsa
// triggerFn() çağırılıp collectMs boyunca `room_status_update` frame'leri
// toplanır. Döner: { connected, connectError, frames:[envelope...], ... }.
async function sioRoomStatusProbe(io, base, token, opts = {}) {
    const connectTimeoutMs = opts.connectTimeoutMs ?? 8000;
    const collectMs = opts.collectMs ?? 4000;
    const triggerFn = opts.triggerFn ?? null;
    return await new Promise((resolve) => {
        let socket = null;
        let connected = false;
        let connectError = null;
        let resolved = false;
        const frames = [];
        const settle = (extra = {}) => {
            if (resolved) return;
            resolved = true;
            try { socket && socket.disconnect(); } catch { /* ignore */ }
            resolve({ connected, connectError, frames, framesIn: frames.length, ...extra });
        };
        let socketPath = '/ws/socket.io';
        try {
            socket = io(base, {
                path: socketPath,
                auth: { token },
                transports: ['websocket'],
                reconnection: false,
                timeout: connectTimeoutMs,
                forceNew: true,
            });
        } catch (e) {
            return settle({ connectError: `ctor_${String(e?.message || e).slice(0, 80)}` });
        }
        const killer = setTimeout(() => settle({ timedOut: !connected }), connectTimeoutMs + collectMs + 1000);
        socket.on('connect', async () => {
            connected = true;
            if (triggerFn) {
                try { await triggerFn(); } catch (e) { /* trigger error recorded by caller */ }
            }
            setTimeout(() => { clearTimeout(killer); settle(); }, collectMs);
        });
        socket.on('connect_error', (e) => {
            connectError = String(e?.message || e).slice(0, 100);
            // connect_error reconnection:false ile terminal — kısa bekle settle.
            setTimeout(() => { clearTimeout(killer); settle(); }, 300);
        });
        socket.on('room_status_update', (payload) => {
            frames.push(payload);
        });
    });
}

test.describe.configure({ mode: 'serial' });

test.describe('F9E § 08B — Housekeeping Live Broadcast + Cleaning Status', () => {
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let pilotBaseline = null;
    let stressTid = null;
    let pilotTid = null;
    let baseUrl = null;

    let stressRoomId = null;       // stress-tenant temizlik mutasyonları için
    let pilotRoomId = null;        // C) IDOR (read-only pilot harvest)

    async function gap(ms = GAP_MS) {
        await new Promise((r) => setTimeout(r, ms));
    }

    // ──────────────────────────────────────────────────────────────
    test('Setup: stress token + module probe + room harvest + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        baseUrl = stressState.base_url || process.env.E2E_BASE_URL;
        expect(prefix, 'stressState.data_prefix yok').toBeTruthy();

        // Pilot booking baseline (drift guard).
        if (stressTokens.pilot_token) {
            const snap = await pilotBookingsCount(request, stressTokens.pilot_token);
            pilotBaseline = (snap?.count != null && !snap.unreachable) ? snap.count : null;
        }
        rec(testInfo, {
            module: MOD, step: 'setup_pilot_baseline',
            status: 'PASS', note: `pilot_baseline=${pilotBaseline}`,
        });

        // Module probe — GET /api/housekeeping/rooms (require_module_v99 housekeeping
        // mutasyonlarda; GET yalnız get_current_user). Non-2xx → A/B SKIP.
        const probe = await callTimed(
            request, 'get', '/api/housekeeping/rooms', null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        if (probe.status !== 200) {
            moduleBlocked = true;
            blockedReason = `hk_rooms_probe http=${probe.status}`;
            recFinding(testInfo, 'P2', MOD,
                `Housekeeping live module blocked (http=${probe.status})`,
                `stress_token HK rooms reach yok — A/B SKIP, C bağımsız.`);
            rec(testInfo, { module: MOD, step: 'setup_module_probe', status: 'REVIEW', http: probe.status, note: blockedReason });
        } else {
            rec(testInfo, { module: MOD, step: 'setup_module_probe', status: 'PASS', http: 200 });
        }

        // Stress-tenant oda harvest. 08-mass spec ile self-depletion çakışmasını
        // önlemek için ayrı harvestWindow cursor key kullan; mutasyonlar yalnız
        // status (PMS state machine) DEĞİL housekeeping_status alanını etkiler,
        // o yüzden 08'in transition odalarıyla çakışsa bile ortogonal.
        if (!moduleBlocked) {
            const rooms = await fetchAllByPrefix(
                request, stressTokens.stress_token,
                '/api/pms/rooms?include_virtual=true', 'stress_prefix', prefix,
            );
            const { window } = harvestWindow(`${MOD}:rooms`, rooms, 1);
            const room = window[0] || rooms[0] || null;
            if (room?.id) {
                stressRoomId = room.id;
                rec(testInfo, {
                    module: MOD, step: 'setup_harvest_stress_room',
                    status: 'PASS', note: `stress_room_id=${stressRoomId} pool=${rooms.length}`,
                });
            } else {
                rec(testInfo, {
                    module: MOD, step: 'setup_harvest_stress_room',
                    status: 'REVIEW', note: 'no stress room harvested — A/B will SKIP',
                });
            }
        }

        // Pilot oda harvest (C IDOR için, read-only). Pilot HK rooms erişilemezse
        // C bogus-uuid fallback'e düşer.
        if (stressTokens.pilot_token) {
            const pr = await callTimed(
                request, 'get', '/api/housekeeping/rooms', null,
                stressTokens.pilot_token, { timeout: 15_000 },
            );
            if (pr.status === 200) {
                const pRooms = pr.body?.rooms || (Array.isArray(pr.body) ? pr.body : []);
                const pf = pRooms.find((r) => r.id) || null;
                if (pf?.id) {
                    pilotRoomId = pf.id;
                    rec(testInfo, {
                        module: MOD, step: 'setup_harvest_pilot_room',
                        status: 'PASS', note: `pilot_room_id=${String(pilotRoomId).slice(0, 8)}…`,
                    });
                } else {
                    rec(testInfo, {
                        module: MOD, step: 'setup_harvest_pilot_room',
                        status: 'REVIEW', note: 'pilot HK rooms empty — C uses bogus uuid',
                    });
                }
            } else {
                rec(testInfo, {
                    module: MOD, step: 'setup_harvest_pilot_room',
                    status: 'REVIEW', http: pr.status, note: 'pilot HK rooms non-200 — C uses bogus uuid',
                });
            }
        }
    });

    // ──────────────────────────────────────────────────────────────
    // A) Cleaning lifecycle (REST read-back): start→cleaning, complete→clean.
    test('A) Cleaning lifecycle start→cleaning→clean (status filter read-back)', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked || !stressRoomId) {
            const reason = moduleBlocked ? blockedReason : 'no_stress_room';
            rec(testInfo, { module: MOD, step: 'A_lifecycle', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }

        // 1) start → cleaning
        const startR = await callTimed(
            request, 'post', `/api/housekeeping/rooms/${stressRoomId}/start`, {},
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'A_start', [startR.ms], startR.status === 200);
        expect(startR.status, `A_start 5xx=${startR.status}`).toBeLessThan(500);
        // RBAC (require_module_v99) reddederse 403 → module-blocked benzeri; oda
        // yoksa 404. İkisi de stress-token kapsamında "yetki/durum" — REVIEW.
        const startOkStatuses = [200, 403, 404];
        expect(startOkStatuses, `A_start unexpected=${startR.status}`).toContain(startR.status);
        if (startR.status !== 200) {
            recFinding(testInfo, 'P2', MOD,
                `HK start non-200 status=${startR.status}`,
                `stress_token housekeeping module/start yetkisi yok ya da oda yok (room=${stressRoomId}). A read-back atlanır.`);
            rec(testInfo, { module: MOD, step: 'A_start', status: 'REVIEW', http: startR.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'A_start', status: 'PASS', http: 200 });
        await gap();

        // 2) read-back ?status=cleaning → oda listede + hk_status='cleaning'
        const cleaningR = await callTimed(
            request, 'get', '/api/housekeeping/rooms?status=cleaning', null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        expect(cleaningR.status, `A_cleaning_read 5xx=${cleaningR.status}`).toBeLessThan(500);
        const cleaningRooms = cleaningR.body?.rooms || (Array.isArray(cleaningR.body) ? cleaningR.body : []);
        const cleaningHit = cleaningRooms.find((r) => r.id === stressRoomId) || null;
        // GET list cache'li (ttl=120) — read-back gecikebilir; bulunamazsa
        // REVIEW (cache stale), bulunduysa hk_status hard-kontrol.
        if (cleaningHit) {
            const ok = (cleaningHit.hk_status === 'cleaning' || cleaningHit.housekeeping_status === 'cleaning');
            rec(testInfo, {
                module: MOD, step: 'A_cleaning_readback',
                status: ok ? 'PASS' : 'REVIEW',
                note: `hk_status=${cleaningHit.hk_status} housekeeping_status=${cleaningHit.housekeeping_status}`,
            });
            if (!ok) {
                recFinding(testInfo, 'P2', MOD,
                    'cleaning read-back hk_status uyumsuz',
                    `room=${stressRoomId} filtre=cleaning ama hk_status=${cleaningHit.hk_status}.`);
            }
        } else {
            rec(testInfo, {
                module: MOD, step: 'A_cleaning_readback',
                status: 'REVIEW', note: `room not in ?status=cleaning page (cache ttl=120 stale olası); count=${cleaningRooms.length}`,
            });
        }
        await gap();

        // 3) complete → clean
        const completeR = await callTimed(
            request, 'post', `/api/housekeeping/rooms/${stressRoomId}/complete`,
            { cleaned_by: `${prefix}_hk_live` },
            stressTokens.stress_token, { timeout: 15_000 },
        );
        recPerf(testInfo, MOD, 'A_complete', [completeR.ms], completeR.status === 200);
        expect(completeR.status, `A_complete 5xx=${completeR.status}`).toBeLessThan(500);
        expect([200, 403, 404], `A_complete unexpected=${completeR.status}`).toContain(completeR.status);
        if (completeR.status !== 200) {
            rec(testInfo, { module: MOD, step: 'A_complete', status: 'REVIEW', http: completeR.status });
            return;
        }
        rec(testInfo, { module: MOD, step: 'A_complete', status: 'PASS', http: 200 });
        await gap();

        // 4) read-back ?status=clean → oda listede + hk_status='clean'
        const cleanR = await callTimed(
            request, 'get', '/api/housekeeping/rooms?status=clean', null,
            stressTokens.stress_token, { timeout: 15_000 },
        );
        expect(cleanR.status, `A_clean_read 5xx=${cleanR.status}`).toBeLessThan(500);
        const cleanRooms = cleanR.body?.rooms || (Array.isArray(cleanR.body) ? cleanR.body : []);
        const cleanHit = cleanRooms.find((r) => r.id === stressRoomId) || null;
        if (cleanHit) {
            const ok = (cleanHit.hk_status === 'clean' || cleanHit.housekeeping_status === 'clean');
            rec(testInfo, {
                module: MOD, step: 'A_clean_readback',
                status: ok ? 'PASS' : 'REVIEW',
                note: `hk_status=${cleanHit.hk_status} housekeeping_status=${cleanHit.housekeeping_status}`,
            });
        } else {
            rec(testInfo, {
                module: MOD, step: 'A_clean_readback',
                status: 'REVIEW', note: `room not in ?status=clean page (cache stale olası); count=${cleanRooms.length}`,
            });
        }
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // B) Live broadcast — PMS Socket.IO room_status_update frame capture.
    test('B) Live broadcast room_status_update frame (Socket.IO) — stress-scoped, no pilot leak', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || !stressRoomId) {
            const reason = moduleBlocked ? blockedReason : 'no_stress_room';
            rec(testInfo, { module: MOD, step: 'B_broadcast', status: 'SKIP', note: reason });
            test.skip(true, reason);
        }
        const io = await ensureSocketIo();
        if (!io) {
            recFinding(testInfo, 'P2', MOD, 'socket.io-client yüklü değil — live broadcast probe yapılamadı',
                'frontend/node_modules/socket.io-client yok; B SKIP (REVIEW), C/D bağımsız.');
            rec(testInfo, { module: MOD, step: 'B_broadcast', status: 'SKIP', note: 'socket.io-client missing' });
            test.skip(true, 'socket.io-client not installed');
        }
        if (!baseUrl) {
            rec(testInfo, { module: MOD, step: 'B_broadcast', status: 'REVIEW', note: 'base_url unset — Socket.IO connect denenemedi' });
            return;
        }

        // Connect with stress token, then trigger a cleaning transition and
        // capture room_status_update frames for the collection window.
        const res = await sioRoomStatusProbe(io, baseUrl, stressTokens.stress_token, {
            connectTimeoutMs: 8000,
            collectMs: 5000,
            triggerFn: async () => {
                // start (cleaning) — connect sonrası tetiklenir, böylece frame
                // yakalanma penceresi içinde yayınlanır.
                await callTimed(
                    request, 'post', `/api/housekeeping/rooms/${stressRoomId}/start`, {},
                    stressTokens.stress_token, { timeout: 15_000 },
                );
            },
        });

        // Güvenlik invariantı (HARD): yakalanan hiçbir frame pilot_tid LİTERAL
        // taşımamalı; stress odaya ait frame'in tenant_id'si stress_tid olmalı.
        let pilotLeak = false;
        let stressScopedFrame = false;
        for (const f of (res.frames || [])) {
            const tid = f?.tenant_id;
            if (pilotTid && tid === pilotTid) pilotLeak = true;
            // Defansif: serialize edilmiş payload'ta pilot_tid string'i geçerse de leak.
            try {
                if (pilotTid && JSON.stringify(f).includes(pilotTid)) pilotLeak = true;
            } catch { /* ignore */ }
            if (stressTid && tid === stressTid) stressScopedFrame = true;
        }
        const ourRoomFrame = (res.frames || []).find((f) => f?.room_id === stressRoomId) || null;

        if (pilotLeak) {
            recFinding(testInfo, 'P0', MOD,
                'Socket.IO room_status_update frame\'inde pilot tenant_id sızdı',
                `frames=${JSON.stringify((res.frames || []).slice(0, 3))}. Cross-tenant canlı yayın leak.`);
        }

        // Hedef oda frame'i yakalandıysa tenant_id'si MUTLAKA stress_tid olmalı —
        // yanlış/boş tenant_id ile PASS verilmez (scope kanıtı zorunlu).
        const ourFrameTenantOk = !!(ourRoomFrame && stressTid && ourRoomFrame.tenant_id === stressTid);

        // Frame doğru scope ile yakalandıysa → PASS. Yanlış tenant_id → REVIEW.
        // Hiç frame yok → REVIEW (transport gözlemlenemedi; PASS DEĞİL — skip-as-pass YOK).
        let status;
        let note;
        if (pilotLeak) {
            status = 'FAIL';
            note = `pilot_leak=true frames=${res.framesIn}`;
        } else if (ourRoomFrame && ourFrameTenantOk) {
            status = 'PASS';
            note = `room_status_update yakalandı room=${stressRoomId} status=${ourRoomFrame.status} tenant_id==stress_tid frames=${res.framesIn}`;
        } else if (ourRoomFrame && !ourFrameTenantOk) {
            status = 'REVIEW';
            note = `hedef room frame yakalandı ama tenant_id eşleşmedi: frame_tid=${ourRoomFrame.tenant_id} stress_tid=${stressTid || 'unset'}`;
            recFinding(testInfo, 'P2', MOD,
                'room_status_update frame tenant_id beklenenle eşleşmedi',
                `room=${stressRoomId} frame_tid=${ourRoomFrame.tenant_id} stress_tid=${stressTid || 'unset'} — scope kanıtı doğrulanamadı.`);
        } else if (res.framesIn > 0) {
            // Frame geldi ama bizim odamız değil (başka stress mutasyonu) — yine de
            // scope temiz; broadcast kanalı canlı. REVIEW (kendi tetiklememiz gözlenmedi).
            status = 'REVIEW';
            note = `frames var ama hedef room frame yok: frames=${res.framesIn} connected=${res.connected}`;
        } else {
            status = 'REVIEW';
            note = `frame yakalanamadı connected=${res.connected} connect_error=${res.connectError || 'none'} — Socket.IO yayın gözlemlenemedi (Redis/adapter env'e bağlı).`;
        }
        rec(testInfo, { module: MOD, step: 'B_broadcast', status, note });

        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'B_broadcast', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        // HARD security gate: pilot tenant_id frame'i SIZAMAZ.
        expect(pilotLeak, `Socket.IO room_status_update pilot_tid leak=${pilotLeak}`).toBe(false);
        // HARD scope gate: hedef oda frame'i yakalandıysa tenant_id stress_tid OLMALI
        // (yanlış/boş tenant_id ile yayın = scope bütünlüğü ihlali).
        if (ourRoomFrame && stressTid) {
            expect(ourRoomFrame.tenant_id, `room_status_update frame tenant_id stress_tid değil: ${JSON.stringify(ourRoomFrame).slice(0, 150)}`).toBe(stressTid);
        }

        // complete ile odayı kapat (stress-tenant teardown — clean state bırak).
        await gap(400);
        await callTimed(
            request, 'post', `/api/housekeeping/rooms/${stressRoomId}/complete`,
            { cleaned_by: `${prefix}_hk_live_B` },
            stressTokens.stress_token, { timeout: 15_000 },
        ).catch(() => null);
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // C) Cross-tenant mutation — stress_token PILOT room start MUST be 4xx.
    test('C) Cross-tenant: stress_token start cleaning on pilot room → 4xx', async ({ request, stressTokens }, testInfo) => {
        // Bogus UUID ek bir sanity probe — ASLA tek başına IDOR kanıtı değil.
        // Gerçek cross-tenant denemesi yalnız harvest edilmiş PILOT oda ile yapılır.
        const bogusId = '00000000-0000-4000-8000-000000000000';
        const bogusR = await callTimed(
            request, 'post', `/api/housekeeping/rooms/${bogusId}/start`, {},
            stressTokens.stress_token, { timeout: 15_000 },
        );
        expect(bogusR.status, `C_bogus 5xx=${bogusR.status}`).toBeLessThan(500);
        // Bogus 2xx başlı başına şüpheli (var olmayan oda mutasyonu) → kaydet.
        const bogusBreach = bogusR.status >= 200 && bogusR.status < 300;
        if (bogusBreach) {
            recFinding(testInfo, 'P1', MOD,
                'HK start var olmayan oda için 2xx döndü',
                `bogus=${bogusId} status=${bogusR.status} — mutasyon var olmayan kaynak üzerinde başarılı görünüyor.`);
        }
        rec(testInfo, { module: MOD, step: 'C_bogus_probe', status: bogusBreach ? 'FAIL' : 'PASS', http: bogusR.status, note: 'bogus uuid sanity probe' });
        expect(bogusBreach, `bogus HK start unexpected 2xx=${bogusR.status}`).toBe(false);

        // Gerçek IDOR: pilot oda harvest edilemediyse PASS VERME → SKIP+P2 REVIEW.
        if (!pilotRoomId) {
            recFinding(testInfo, 'P2', MOD,
                'Cross-tenant HK start gerçek kanıtı yapılamadı (pilot oda harvest edilemedi)',
                'Pilot HK rooms erişilemediği için gerçek cross-tenant denemesi atlandı; sadece bogus probe çalıştı.');
            rec(testInfo, { module: MOD, step: 'C_cross_tenant_start', status: 'SKIP', note: 'no_pilot_room — real IDOR unverifiable' });
            test.skip(true, 'pilot room not harvested — real cross-tenant attempt unverifiable');
        }

        const r = await callTimed(
            request, 'post', `/api/housekeeping/rooms/${pilotRoomId}/start`, {},
            stressTokens.stress_token, { timeout: 15_000 },
        );
        expect(r.status, `C_idor 5xx=${r.status}`).toBeLessThan(500);
        // update_one tenant filtresi: pilot oda stress tenant'ta yok → matched_count
        // 0 → 404. RBAC reddi → 403. İkisi de kabul. 2xx = cross-tenant breach.
        const crossTenantBreach = r.status >= 200 && r.status < 300;
        if (crossTenantBreach) {
            recFinding(testInfo, 'P0', MOD,
                'Cross-tenant HK start — stress_token pilot odayı cleaning yaptı',
                `target=${pilotRoomId} status=${r.status}. Tenant izolasyon ihlali (threat-model § Tampering/EoP).`);
        }
        rec(testInfo, {
            module: MOD, step: 'C_cross_tenant_start',
            status: crossTenantBreach ? 'FAIL' : 'PASS',
            http: r.status, note: 'target=pilot_room expected≥400',
        });
        expect(crossTenantBreach, `cross-tenant HK start breach status=${r.status}`).toBe(false);
        await gap();
    });

    // ──────────────────────────────────────────────────────────────
    // D) Final invariants — pilot drift = 0 + external_calls = [].
    test('D) Final invariants (pilot_drift=0 + external_calls=[])', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBaseline);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, {
            module: MOD, step: 'final_invariants',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}`,
        });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});

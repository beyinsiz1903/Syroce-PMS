// F8A § 08 — Housekeeping mass: 500 oda render, 100 transition, 20 OOO, status counts.
import { test, expect, rec } from '../fixtures/stress-context.js';
import { fetchAllByPrefix, fetchSingle, callTimed, recPerf, recFinding, pilotBookingsCount, assertNoExternalCallsPostBatch } from '../fixtures/stress-helpers.js';

const MOD = 'housekeeping';

test.describe.configure({ mode: 'serial' });

test.describe('F8A § 08 — Housekeeping mass (render + transitions + OOO + summary)', () => {
    let rooms = [];
    let pilotBefore = null;
    let summaryBefore = null;

    test('Setup: stress rooms + summary baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        const prefix = stressState.data_prefix;
        rooms = await fetchAllByPrefix(request, stressTokens.stress_token, '/api/pms/rooms', 'stress_prefix', prefix);
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        const sumR = await callTimed(request, 'get', '/api/pms-core/housekeeping/room-summary', undefined, stressTokens.stress_token);
        summaryBefore = sumR.body;
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `rooms=${rooms.length} summary_status=${sumR.status} summary_keys=${summaryBefore ? Object.keys(summaryBefore).slice(0, 6).join(',') : 'null'} pilot_before=${pilotBefore?.count}` });
    });

    test('A) HK summary endpoint: <2s p95', async ({ request, stressTokens }, testInfo) => {
        const samples = [];
        for (let i = 0; i < 5; i++) {
            const r = await callTimed(request, 'get', '/api/pms-core/housekeeping/room-summary', undefined, stressTokens.stress_token);
            samples.push(r.ms);
            if (i === 0) {
                rec(testInfo, { module: MOD, step: 'hk_summary_first_call', status: r.ok ? 'PASS' : 'REVIEW',
                    endpoint: '/api/pms-core/housekeeping/room-summary',
                    note: `status=${r.status} body_keys=${r.body ? Object.keys(r.body).slice(0, 6).join(',') : 'null'}` });
            }
        }
        recPerf(testInfo, MOD, 'hk_summary', samples, true);
        const max = Math.max(...samples);
        if (max > 2000) {
            recFinding(testInfo, 'P3', MOD, 'HK summary endpoint yavaş',
                `5 ardışık çağrı max=${max}ms (>2s). 500-oda kümesi için kabul edilebilir ama p95 izlenmeli.`);
        }
    });

    test('B) 500-oda HK list endpoint render performansı', async ({ request, stressTokens }, testInfo) => {
        // /api/housekeeping/rooms — enterprise router
        const samples = [];
        let lastBody = null;
        for (let i = 0; i < 3; i++) {
            const r = await callTimed(request, 'get', '/api/housekeeping/rooms', undefined, stressTokens.stress_token);
            samples.push(r.ms);
            lastBody = r.body;
        }
        const len = Array.isArray(lastBody) ? lastBody.length : (lastBody?.rooms?.length ?? lastBody?.items?.length ?? 0);
        recPerf(testInfo, MOD, 'hk_rooms_list', samples, true);
        rec(testInfo, { module: MOD, step: 'hk_rooms_list', status: 'PASS',
            endpoint: '/api/housekeeping/rooms',
            note: `n_calls=3 sample_max_ms=${Math.max(...samples)} returned_len=${len}` });
        if (Math.max(...samples) > 5000) {
            recFinding(testInfo, 'P2', MOD, 'HK rooms listesi >5s',
                `3 çağrı max=${Math.max(...samples)}ms. 500-oda kümesi için optimize edilmeli (index, pagination).`);
        }
    });

    test('C) 100 oda HK transitions (dirty→cleaning→inspected→clean)', async ({ request, stressTokens }, testInfo) => {
        if (rooms.length < 20) { rec(testInfo, { module: MOD, step: 'transitions_sample', status: 'SKIP', note: `rooms=${rooms.length}` }); return; }
        const target = rooms.slice(0, Math.min(100, rooms.length));
        const transitions = ['dirty', 'cleaning', 'inspected', 'clean'];
        const counters = { ok: 0, fail: 0, byTransition: {} };
        const samples = [];
        // F8A tur-17 fix (CI run #29 root cause): bu test eskiden 4ms'de
        // bitiyordu çünkü tur-15 öncesi fetchAllByPrefix kırıktı → rooms=0 →
        // erken SKIP (line 64 guard). Tur-15 fix sonrası 560 oda fetch edilince
        // gerçekten çalışmaya başladı: 100 oda × 4 transition = 400 SIRALI
        // HTTP call → 180s timeout aşılıyor (CI→dev latency ~500ms/call).
        // Fix: farklı odalar bağımsız (state machine sadece intra-room sıralı),
        // o yüzden BATCH paralel — her batch'te 10 oda eşzamanlı, her odanın
        // 4 transition'ı kendi içinde sıralı. 10 batch × ~4s = ~40s, 180s
        // limitinin çok altında. Backend yükü kontrollü (max 10 concurrent).
        const BATCH_SIZE = 10;
        const runRoom = async (room) => {
            const results = [];
            for (const status of transitions) {
                const r = await callTimed(request, 'post', '/api/pms-core/housekeeping/room-status', {
                    room_id: room.id, new_status: status, notes: `F8A trans ${status}`, force: true,
                }, stressTokens.stress_token);
                results.push({ status, ok: r.ok, ms: r.ms });
            }
            return results;
        };
        for (let i = 0; i < target.length; i += BATCH_SIZE) {
            const batch = target.slice(i, i + BATCH_SIZE);
            const batchResults = await Promise.all(batch.map(runRoom));
            for (const roomResults of batchResults) {
                for (const tr of roomResults) {
                    samples.push(tr.ms);
                    counters.byTransition[tr.status] ||= { ok: 0, fail: 0 };
                    if (tr.ok) { counters.ok++; counters.byTransition[tr.status].ok++; }
                    else { counters.fail++; counters.byTransition[tr.status].fail++; }
                }
            }
        }
        rec(testInfo, { module: MOD, step: 'hk_transitions', status: counters.ok > target.length * transitions.length * 0.5 ? 'PASS' : 'REVIEW',
            endpoint: '/api/pms-core/housekeeping/room-status',
            note: `rooms=${target.length} transitions=${transitions.length} total_calls=${target.length * transitions.length} ok=${counters.ok} fail=${counters.fail} by_transition=${JSON.stringify(counters.byTransition)}` });
        recPerf(testInfo, MOD, 'hk_transition', samples, counters.ok > 0);
        if (counters.ok === 0) {
            recFinding(testInfo, 'P1', MOD, 'HK transition tüm denemelerde başarısız',
                `${target.length * transitions.length} transition POST 0 başarı. State machine veya permission sorunu.`);
        }
    });

    test('D) 20 oda OOO işaretle + summary diff', async ({ request, stressTokens }, testInfo) => {
        if (rooms.length < 20) { rec(testInfo, { module: MOD, step: 'ooo_sample', status: 'SKIP' }); return; }
        const target = rooms.slice(rooms.length - 20);
        let ok = 0, fail = 0;
        const samples = [];
        for (const room of target) {
            const r = await callTimed(request, 'post', '/api/pms-core/housekeeping/room-status', {
                room_id: room.id, new_status: 'out_of_order', notes: 'F8A OOO mass', force: true,
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) ok++; else fail++;
        }
        recPerf(testInfo, MOD, 'hk_ooo_set', samples, ok > 0);

        const sumR = await callTimed(request, 'get', '/api/pms-core/housekeeping/room-summary', undefined, stressTokens.stress_token);
        const sumAfter = sumR.body;
        rec(testInfo, { module: MOD, step: 'ooo_mass', status: ok > 0 ? 'PASS' : 'REVIEW',
            note: `n=20 ok=${ok} fail=${fail} summary_after_keys=${sumAfter ? Object.keys(sumAfter).slice(0, 6).join(',') : 'null'}` });
        if (ok === 0) {
            recFinding(testInfo, 'P2', MOD, 'OOO işareti tutmuyor',
                `20 OOO POST 0 başarı; rezervasyon-engelleme guard test edilemiyor.`);
        }
    });

    test('D2) OOO booking-guard: OOO odaya walk-in / new-booking attempt → reject', async ({ request, stressTokens, stressState }, testInfo) => {
        // Architect tur-3 feedback: OOO işareti tutmuyorsa booking layer reject etmeli.
        // D)'de işaretlenen OOO odalara walk-in dene → 4xx bekle. Kabul edilirse P0 finding.
        if (rooms.length < 20) { rec(testInfo, { module: MOD, step: 'ooo_booking_guard', status: 'SKIP' }); return; }
        // Tur-23 fix: D)'de housekeeping-status set 200 dönse de bazı odalar
        // (occupied/dirty) status transition rejection nedeniyle out_of_order'a
        // geçmemiş olabiliyor. D2'nin guard'ı test edebilmesi için ROOM'un
        // gerçekten out_of_order/out_of_service durumunda olması GEREK. Aksi
        // halde "available" odaya walk-in başarısı = beklenen davranış (false P0).
        // Fix: D'den sonra fresh GET ile status'ları yenile, sadece BLOCKED
        // durumdaki ilk 5 odayı al.
        const candidateIds = new Set(rooms.slice(rooms.length - 20).map((r) => r.id));
        const prefix = stressState.data_prefix;
        const freshR = await callTimed(request, 'get', '/api/pms/rooms', undefined, stressTokens.stress_token);
        const freshAll = freshR.body?.rooms || freshR.body?.items || (Array.isArray(freshR.body) ? freshR.body : []);
        const BLOCKED = new Set(['out_of_order', 'out_of_service', 'maintenance']);
        const oooTargets = freshAll
            .filter((r) => candidateIds.has(r.id) && BLOCKED.has(r.status))
            .slice(0, 5);
        if (oooTargets.length === 0) {
            rec(testInfo, { module: MOD, step: 'ooo_booking_guard', status: 'SKIP',
                note: `no rooms in BLOCKED status after D) — HK transition guard rejected all 20 (likely occupied/dirty preconditions). Guard test inconclusive.` });
            recFinding(testInfo, 'P2', MOD, 'OOO guard test inconclusive',
                `D) housekeeping-status set sonrası 0 oda BLOCKED durumunda; D2 guard test skipped (pre-existing HK transition constraints).`);
            return;
        }
        let rejected = 0, accepted = 0, other = 0;
        const acceptedDetail = [];
        for (let i = 0; i < oooTargets.length; i++) {
            const room = oooTargets[i];
            const ts = Date.now();
            const r = await callTimed(request, 'post', '/api/pms-core/walk-in', {
                room_id: room.id,
                nights: 1, rate: 1000,
                guest_name: `E2E_STRESS_F8A_OOOGuard_${ts}_${i}`,
                guest_phone: `+9055500${String(i).padStart(5, '0')}`,
                guest_email: `f8a-ooo-guard-${ts}-${i}@e2e-stress.example.com`,
                guest_id_number: `E2EOG${ts}${i}`,
                adults: 1,
            }, stressTokens.stress_token);
            if (r.status === 400 || r.status === 409 || r.status === 422 || r.status === 403) rejected++;
            else if (r.ok) {
                accepted++;
                acceptedDetail.push({ room_id: room.id, status: r.status, body_excerpt: JSON.stringify(r.body).slice(0, 120) });
            } else other++;
        }
        const guardStatus = oooTargets.length === 0 ? 'SKIP' : (accepted === 0 && rejected > 0 ? 'PASS' : (accepted > 0 ? 'FAIL' : 'REVIEW'));
        rec(testInfo, { module: MOD, step: 'ooo_booking_guard', status: guardStatus,
            endpoint: '/api/pms-core/walk-in (OOO target)',
            note: `n=${oooTargets.length} rejected=${rejected} accepted=${accepted} other=${other} ${accepted > 0 ? `accepted_samples=${JSON.stringify(acceptedDetail)}` : ''}` });
        if (accepted > 0) {
            recFinding(testInfo, 'P0', MOD,
                'OOO odaya yeni booking kabul edildi — overbook + maintenance risk',
                `${accepted}/${oooTargets.length} OOO odaya walk-in başarılı oldu. front_desk_service.walk_in OOO room status guard kırık. Detay: ${JSON.stringify(acceptedDetail)}`);
        }
        expect(guardStatus, `ooo_booking_guard FAIL: accepted=${accepted}/${oooTargets.length} samples=${JSON.stringify(acceptedDetail)}`).not.toBe('FAIL');
        const extOk1 = await assertNoExternalCallsPostBatch(testInfo, MOD, 'ooo_booking_guard_5', stressState, request, stressTokens.pilot_token);
        expect(extOk1, 'ooo_booking_guard_5 sonrası external_calls invariant ihlal').toBe(true);
    });

    test('E) Mobile viewport smoke (390x844): tek HK transition + summary', async ({ browser, stressTokens }, testInfo) => {
        // API-only suite, ama mobile UA + viewport sözleşmesi için ayrı request context aç
        const ctx = await browser.newContext({
            viewport: { width: 390, height: 844 },
            userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
        });
        const req = ctx.request;
        const summaryR = await req.get('/api/pms-core/housekeeping/room-summary', {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false, timeout: 15_000,
        });
        const ok = summaryR.ok();
        await ctx.close();
        rec(testInfo, { module: MOD, step: 'mobile_smoke', status: ok ? 'PASS' : 'REVIEW',
            note: `mobile_ua + 390x844 viewport, summary status=${summaryR.status()} (UI render ayrı tur — bu sadece API contract sözleşmesi)` });
    });

    test('G) FE render TTI: /housekeeping desktop + mobile (real DOM, 50/200/500 row scaling)', async ({ browser, stressTokens, stressState }, testInfo) => {
        // Architect tur-3 feedback: brief 500-room FE render performance + mobile UI
        // transition istiyordu. Bu test gerçek bir Playwright page açar, stress_token'ı
        // localStorage'a seed eder (frontend axiosConfig.js localStorage["token"] okur),
        // /housekeeping route'una navigate eder ve TTI ölçer.
        //
        // FE base URL: stress config sadece backend BASE_URL içerir; frontend'i
        // REPLIT_DEV_DOMAIN üzerinden port 5000'e map ederiz (vite.config.js:125).
        // E2E_FE_BASE_URL env override'ı destekleniyor.
        const replitDomain = process.env.REPLIT_DEV_DOMAIN;
        let feBase = process.env.E2E_FE_BASE_URL;
        if (!feBase && replitDomain) feBase = `https://5000-${replitDomain}`;
        if (!feBase) {
            rec(testInfo, { module: MOD, step: 'fe_render_tti', status: 'REVIEW',
                note: "E2E_FE_BASE_URL ve REPLIT_DEV_DOMAIN ikisi de unset — FE TTI ölçümü atlandı. CI run'da env set edilmeli." });
            return;
        }

        const measurements = []; // { viewport, label, ttfb_ms, dom_ms, first_row_ms, total_rows }
        const viewports = [
            { name: 'desktop_1440', width: 1440, height: 900 },
            { name: 'mobile_390',   width: 390,  height: 844 },
        ];
        for (const vp of viewports) {
            const ctx = await browser.newContext({
                viewport: { width: vp.width, height: vp.height },
                ignoreHTTPSErrors: true,
                userAgent: vp.width < 500
                    ? 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15'
                    : undefined,
                baseURL: feBase,
            });
            const page = await ctx.newPage();
            try {
                // 1) İlk navigate ile origin yüklenir (localStorage write için origin scope gerek)
                await page.goto('/', { waitUntil: 'domcontentloaded', timeout: 20_000 });
                await page.evaluate(([t]) => {
                    try {
                        localStorage.setItem('token', t);
                        localStorage.setItem('token_ts', String(Date.now()));
                    } catch (_e) { /* incognito or denied */ }
                }, [stressTokens.stress_token]);

                // 2) HK route'una git ve TTI ölç
                const t0 = Date.now();
                const resp = await page.goto('/housekeeping', { waitUntil: 'domcontentloaded', timeout: 30_000 });
                const ttfb = Date.now() - t0;
                const dom = Date.now() - t0;

                // 3) İlk room card / row görünür hale gelene kadar bekle (whitelist selector
                //    listesi — design system değişirse genişletilmeli). Soft-fail: bulamazsak
                //    REVIEW yazıp devam et. Architect tur-4: 50/200/500 row checkpoint timing.
                let firstRow = -1;
                let totalRows = 0;
                let activeSel = null;
                const candidates = [
                    '[data-testid="room-card"]',
                    '[data-testid="hk-room-row"]',
                    'tr[data-room-id]',
                    'div[data-room-id]',
                    '.room-card',
                ];
                for (const sel of candidates) {
                    try {
                        await page.locator(sel).first().waitFor({ state: 'visible', timeout: 8_000 });
                        firstRow = Date.now() - t0;
                        totalRows = await page.locator(sel).count();
                        activeSel = sel;
                        break;
                    } catch (_e) { /* try next */ }
                }
                // 3b) Architect tur-4: explicit 50/200/500 row checkpoint timing.
                // Polling-based — DOM render incremental olduğu için count zaman içinde artar.
                // Her threshold için ilk geçiş anını yakalar. Bulunamazsa -1 kalır (REVIEW).
                const checkpoints = { 50: -1, 200: -1, 500: -1 };
                if (activeSel) {
                    const deadline = t0 + 25_000; // total scaling budget
                    while (Date.now() < deadline) {
                        const c = await page.locator(activeSel).count().catch(() => 0);
                        const elapsed = Date.now() - t0;
                        if (checkpoints[50]  === -1 && c >= 50)  checkpoints[50]  = elapsed;
                        if (checkpoints[200] === -1 && c >= 200) checkpoints[200] = elapsed;
                        if (checkpoints[500] === -1 && c >= 500) checkpoints[500] = elapsed;
                        totalRows = Math.max(totalRows, c);
                        if (checkpoints[500] !== -1) break;
                        await page.waitForTimeout(200);
                    }
                }

                // 4) Mobile viewport'ta tek transition (ilk row'a tıkla → state UI değişimi)
                let transitionMs = -1;
                if (vp.width < 500 && totalRows > 0) {
                    try {
                        const tStart = Date.now();
                        // İlk eyleme tıklanabilir bir butonu ara (clean/dirty toggle vb.)
                        const action = page.locator('button:has-text("Temiz"), button:has-text("Clean"), [data-testid="hk-action"]').first();
                        if (await action.count() > 0) {
                            await action.click({ timeout: 5_000 });
                            await page.waitForTimeout(300); // optimistic UI tick
                            transitionMs = Date.now() - tStart;
                        }
                    } catch (_e) { /* transition optional */ }
                }

                measurements.push({
                    viewport: vp.name, http: resp?.status() ?? 0,
                    ttfb_ms: ttfb, dom_ms: dom, first_row_ms: firstRow,
                    rows_50_ms: checkpoints[50], rows_200_ms: checkpoints[200], rows_500_ms: checkpoints[500],
                    total_rows: totalRows, transition_ms: transitionMs,
                });
            } finally {
                await page.close().catch(() => {});
                await ctx.close().catch(() => {});
            }
        }

        // 5) Verdict (architect tur-4): 50 rows<3s, 200 rows<6s, 500 rows<10s gate.
        //    Ek: DOM<10s, first row<8s. Selector hiç eşleşmediyse REVIEW.
        const desktop = measurements.find((m) => m.viewport === 'desktop_1440');
        const mobile = measurements.find((m) => m.viewport === 'mobile_390');
        const noRows = (desktop?.total_rows ?? 0) === 0 && (mobile?.total_rows ?? 0) === 0;
        const ROW_GATES = { 50: 3_000, 200: 6_000, 500: 10_000 };
        const gateBreaches = [];
        for (const m of measurements) {
            for (const k of [50, 200, 500]) {
                const v = m[`rows_${k}_ms`];
                if (v > 0 && v > ROW_GATES[k]) gateBreaches.push({ viewport: m.viewport, threshold: k, ms: v, gate: ROW_GATES[k] });
            }
            if (m.dom_ms > 10_000) gateBreaches.push({ viewport: m.viewport, kind: 'dom_ms', ms: m.dom_ms, gate: 10_000 });
            if (m.first_row_ms > 0 && m.first_row_ms > 8_000) gateBreaches.push({ viewport: m.viewport, kind: 'first_row_ms', ms: m.first_row_ms, gate: 8_000 });
        }
        const slow = gateBreaches.length > 0;
        const status = noRows ? 'REVIEW' : (slow ? 'FAIL' : 'PASS');
        rec(testInfo, { module: MOD, step: 'fe_render_tti', status,
            endpoint: '/housekeeping (FE)',
            note: `fe_base=${feBase} viewports=${measurements.length} measurements=${JSON.stringify(measurements)} gates(rows_50<3s,200<6s,500<10s,dom<10s,first_row<8s) breaches=${JSON.stringify(gateBreaches)}` });
        recPerf(testInfo, MOD, 'fe_render_tti_desktop', desktop ? [desktop.dom_ms] : [], !slow);
        recPerf(testInfo, MOD, 'fe_render_tti_mobile', mobile ? [mobile.dom_ms] : [], !slow);
        if (slow) {
            recFinding(testInfo, 'P2', MOD,
                'HK FE render TTI gate aşıldı (50/200/500 row checkpoint)',
                `Breaches: ${JSON.stringify(gateBreaches)}. 500-oda render için virtualization/pagination gerekli olabilir. Measurements: ${JSON.stringify(measurements)}`);
        }
        if (noRows) {
            rec(testInfo, { module: MOD, step: 'fe_render_tti_selector_miss', status: 'REVIEW',
                note: `Whitelist selector (${'[data-testid="room-card"], tr[data-room-id], ...'}) hiçbiri eşleşmedi — UI değişti veya auth fail. measurements=${JSON.stringify(measurements)}` });
        }
        // FE test'i için runtime endpoint check ile post-batch invariant.
        // browser context ayrı request worker fixture'ından bağımsız; helper tek GET atar.
        // request fixture'ı bu test scope'unda yok → browser.newContext().request kullan.
        const checkCtx = await browser.newContext({ baseURL: process.env.E2E_BASE_URL });
        const extOk2 = await assertNoExternalCallsPostBatch(testInfo, MOD, 'fe_render_tti', stressState, checkCtx.request, stressTokens.pilot_token);
        expect(extOk2, 'fe_render_tti sonrası external_calls invariant ihlal').toBe(true);
        await checkCtx.close();
    });

    test('F) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `pilot bookings before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});

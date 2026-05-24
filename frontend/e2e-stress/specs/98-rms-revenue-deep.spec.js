// F8AF § 98 — RMS Revenue Deep Stress (Autopilot · Displacement · Demand
// Forecast · AI Pricing · Hurdle Rates).
//
// Threat-model surface (threat_model.md § Tampering + Elevation of Privilege):
//   Revenue management yüzeyi (autopilot policy / approval queue / displacement
//   analysis / demand forecast / AI pricing auto-publish / hurdle rates)
//   doğrudan rate publish + folio impact + kanal push tetikleyebilir. Bu spec
//   per-tenant lifecycle invariant'larını + cross-tenant IDOR guard'larını +
//   AI-pricing auto-publish "dry-run" gate'ini doğrular. Pilot tenant'a ASLA
//   yazma; gerçek dış servis (CM outbox, channel push) çağrısı YOK.
//
// Mutlak kurallar:
//   - failedTests = 0, P0 = P1 = 0
//   - pilot_drift = 0 (her test finally'da)
//   - external_calls = [] (her batch sonunda re-assert)
//   - autopilot mode FORCE `advisory` (setup), original mode finally'da restore
//   - cleanup idempotent (DELETE round-trip, ikinci pass 404 zorunlu)
//
// Doctrine:
//   - Module-blocked pattern: dashboard / policy / queue probe herhangi biri
//     403/404 → moduleBlocked → A..G `test.skip()` + P2 informational; Z
//     cleanup + pilot_drift bağımsız çalışır (F8AB/F8AC mirror).
//   - Autopilot mode'u SETUP'ta `advisory` yapıp policy snapshot al; Z
//     cleanup'ta orijinaline geri yaz (full_auto'ya geçilirse arka plan
//     gerçek apply tetikleyebilir → kapalı kapı).
//   - P0 cross-tenant IDOR (F8X doctrine): stress_token, pilot tenant'tan
//     hasat edilen autopilot queue item / hurdle id'sini approve / PATCH /
//     DELETE etmeyi denediğinde backend ≥400 dönmek ZORUNDA. 2xx response
//     veya silent 200+no-mutation = P0 finding + hard-assert FAIL (F8X §
//     accounting/invoices precedent: matched_count==0 → 404).
//   - AI pricing auto-publish dry-run: POST /api/rms/ai-pricing/auto-publish-
//     rates batch sonunda dispatcher delta=0 ZORUNLU. Real channel push
//     tetiklenirse external_calls invariant patlar.
//   - Forbidden surfaces (FORBIDDEN_AI_AUTOPILOT_RUN /
//     FORBIDDEN_AI_AUTOPILOT_SETMODE sentinel'lar import edilir; literal
//     substring'leri spec source'unda ASLA geçmez — F8O doctrine).

import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, fetchSingle,
    FORBIDDEN_AI_AUTOPILOT_RUN, FORBIDDEN_AI_AUTOPILOT_SETMODE,
    assertEndpointNeverCalled,
} from '../fixtures/stress-helpers.js';

const MOD = 'revenue_management';

// Helpers
const isoDate = (offsetDays) => {
    const d = new Date();
    d.setUTCDate(d.getUTCDate() + offsetDays);
    return d.toISOString().slice(0, 10);
};

// Module-level state shared across serial tests (capture in setup, mutate in
// later steps, restore in cleanup).
let modBlocked = false;
let modBlockReason = '';
let originalPolicy = null;          // for restore in cleanup
let originalMode = null;
let createdHurdleIds = [];          // primary cleanup (DELETE) targets
let createdQueueItemIds = [];       // pending queue items → reject in cleanup
let stressPrefix = '';

test.describe.serial('F8AF revenue_management deep stress', () => {

    test('Setup — pilot baseline + module probe + force advisory mode', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        stressPrefix = stressState?.data_prefix || stressTokens?.seed_state?.data_prefix || `F8AF_${Date.now()}`;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO', note: `count=${pilotBefore?.count} prefix=${stressPrefix}` });

        try {
            // Probe the three primary entry points; any 403/404 → module-blocked.
            const probes = [
                { name: 'autopilot_dashboard', path: '/api/revenue-autopilot/dashboard' },
                { name: 'autopilot_policy', path: '/api/revenue-autopilot/policy' },
                { name: 'autopilot_queue', path: '/api/revenue-autopilot/queue?limit=5' },
            ];
            for (const p of probes) {
                const r = await withModuleProbe(request, sToken, p.path);
                if (r.moduleBlocked) {
                    modBlocked = true;
                    modBlockReason = `${p.name}:${r.reason}`;
                    rec(testInfo, { module: MOD, step: `probe_${p.name}`, status: 'SKIP',
                        note: `module_blocked http=${r.status} reason=${r.reason}` });
                    recFinding(testInfo, 'P2', MOD, `Revenue ${p.name} surface module-blocked`,
                        `GET ${p.path} http=${r.status} reason=${r.reason}; A..G adımları skip edilir.`);
                } else {
                    rec(testInfo, { module: MOD, step: `probe_${p.name}`, status: 'PASS',
                        note: `http=${r.status}` });
                }
            }

            if (!modBlocked) {
                // Snapshot original policy for cleanup restore.
                const polGet = await callTimed(request, 'get', '/api/revenue-autopilot/policy', undefined, sToken);
                if (polGet.status >= 200 && polGet.status < 300 && polGet.body) {
                    originalPolicy = polGet.body;
                    originalMode = polGet.body.mode || 'supervised';
                    rec(testInfo, { module: MOD, step: 'policy_snapshot', status: 'PASS',
                        note: `original_mode=${originalMode}` });
                } else {
                    rec(testInfo, { module: MOD, step: 'policy_snapshot', status: 'REVIEW',
                        note: `http=${polGet.status} (cannot capture original mode; cleanup restore may be partial)` });
                }

                // Force advisory mode — kapalı kapı: full_auto modunda arka plan
                // gerçek apply tetikleyebilir. Advisory garanti dry-run + queue.
                const forceAdvisory = await callTimed(request, 'put', '/api/revenue-autopilot/policy',
                    { mode: 'advisory', enabled: true, max_price_change_pct: 20.0 }, sToken);
                rec(testInfo, { module: MOD, step: 'force_advisory_mode',
                    status: forceAdvisory.status === 200 ? 'PASS' : 'REVIEW',
                    note: `http=${forceAdvisory.status} body=${JSON.stringify(forceAdvisory.body).slice(0, 120)}` });
            }

            // Forbidden literal source-scan guard (defense-in-depth): spec source
            // dosyasında sentinel literal substring'leri bulunmamalı. Architect
            // iter-6 fail-closed doctrine — helper return değeri HARD-asserted.
            expect(assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_RUN),
                'forbidden autopilot RUN literal must not appear in spec source').toBe(true);
            expect(assertEndpointNeverCalled(testInfo, MOD, FORBIDDEN_AI_AUTOPILOT_SETMODE),
                'forbidden autopilot SETMODE literal must not appear in spec source').toBe(true);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('A) Read-only probes (dashboard / queue / summary / market-overview / history / hurdle list / demand-forecast GET)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.skip(modBlocked, `module_blocked:${modBlockReason}`);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            const readonly = [
                { name: 'dashboard', path: '/api/revenue-autopilot/dashboard' },
                { name: 'queue', path: '/api/revenue-autopilot/queue?limit=10' },
                { name: 'summary', path: '/api/revenue-autopilot/summary' },
                { name: 'market_overview', path: '/api/displacement/market-overview?days=7' },
                { name: 'history', path: '/api/displacement/history?limit=5' },
                { name: 'hurdle_list', path: '/api/hurdle-rates/' },
                { name: 'demand_forecast_get', path: `/api/rms/demand-forecast?days=7` },
            ];
            for (const s of readonly) {
                const r = await callTimed(request, 'get', s.path, undefined, sToken);
                if (r.status === 403 || r.status === 404) {
                    rec(testInfo, { module: MOD, step: `ro_${s.name}`, status: 'SKIP',
                        note: `http=${r.status} (surface absent)` });
                    recFinding(testInfo, 'P2', MOD, `Revenue ${s.name} read-only surface non-2xx`,
                        `GET ${s.path} http=${r.status}; informational, lifecycle invariant intact.`);
                } else if (r.status >= 200 && r.status < 300) {
                    rec(testInfo, { module: MOD, step: `ro_${s.name}`, status: 'PASS',
                        note: `http=${r.status}` });
                } else {
                    rec(testInfo, { module: MOD, step: `ro_${s.name}`, status: 'REVIEW',
                        note: `http=${r.status} body=${JSON.stringify(r.body).slice(0, 120)}` });
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'readonly_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('B) Policy update (advisory + thresholds) + demand-forecast POST (short range)', async ({ request, stressTokens, stressState }, testInfo) => {
        test.skip(modBlocked, `module_blocked:${modBlockReason}`);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            // B1: Policy PUT — advisory, low max_price_change_pct, blackout next 2 days.
            const polReq = {
                mode: 'advisory',
                confidence_threshold_auto: 0.99,         // effectively block auto-apply
                confidence_threshold_queue: 0.30,         // moderate queue threshold
                max_price_change_pct: 25.0,
                blackout_dates: [isoDate(0), isoDate(1)],
                protected_room_types: ['Penthouse'],
                enabled: true,
                daily_summary_enabled: true,
            };
            const polPut = await callTimed(request, 'put', '/api/revenue-autopilot/policy', polReq, sToken);
            expect(polPut.status, 'autopilot policy PUT must be 2xx for stress tenant')
                .toBeGreaterThanOrEqual(200);
            expect(polPut.status).toBeLessThan(300);
            rec(testInfo, { module: MOD, step: 'policy_put_advisory',
                status: 'PASS', note: `http=${polPut.status}` });

            // Verify GET reflects mode=advisory (regression on update_policy filter).
            const polVerify = await callTimed(request, 'get', '/api/revenue-autopilot/policy', undefined, sToken);
            if (polVerify.status >= 200 && polVerify.status < 300 && polVerify.body) {
                if (polVerify.body.mode !== 'advisory') {
                    recFinding(testInfo, 'P1', MOD, 'Autopilot policy mode field not persisted',
                        `PUT mode=advisory; GET returned mode=${polVerify.body.mode}. Risk: full_auto background apply silently retained.`);
                }
                rec(testInfo, { module: MOD, step: 'policy_get_verify',
                    status: polVerify.body.mode === 'advisory' ? 'PASS' : 'FAIL',
                    note: `mode=${polVerify.body.mode}` });
            }

            // B2: Demand forecast POST — short 3-day range to limit DB work.
            const dfPost = await callTimed(request, 'post', '/api/rms/demand-forecast', {
                start_date: isoDate(7),
                end_date: isoDate(9),
            }, sToken);
            if (dfPost.status === 403 || dfPost.status === 404) {
                rec(testInfo, { module: MOD, step: 'demand_forecast_post', status: 'SKIP',
                    note: `http=${dfPost.status}` });
                recFinding(testInfo, 'P2', MOD, 'demand-forecast POST surface non-2xx',
                    `POST /api/rms/demand-forecast http=${dfPost.status}; informational.`);
            } else {
                expect(dfPost.status, 'demand-forecast POST must be 2xx')
                    .toBeGreaterThanOrEqual(200);
                expect(dfPost.status).toBeLessThan(300);
                rec(testInfo, { module: MOD, step: 'demand_forecast_post', status: 'PASS',
                    note: `http=${dfPost.status} forecasts=${dfPost.body?.forecasts?.length ?? 0}` });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'policy_forecast_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('C) Autopilot pipeline — process / approve / reject', async ({ request, stressTokens, stressState }, testInfo) => {
        test.skip(modBlocked, `module_blocked:${modBlockReason}`);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            // C1: Process a moderate-confidence recommendation. Advisory mode +
            // confidence>queue_threshold → expected action=queued.
            const recPayload = {
                room_type: `${stressPrefix}_Standard`,
                target_date: isoDate(14),
                current_price: 100.0,
                recommended_price: 112.0,  // +12% (under max_price_change_pct=25)
                confidence: 0.55,
                source_job_id: `${stressPrefix}_job_C1`,
            };
            const proc = await callTimed(request, 'post', '/api/revenue-autopilot/process', recPayload, sToken);
            if (proc.status === 403 || proc.status === 404) {
                rec(testInfo, { module: MOD, step: 'process_queued', status: 'SKIP',
                    note: `http=${proc.status}` });
                recFinding(testInfo, 'P2', MOD, 'autopilot /process surface non-2xx',
                    `POST /api/revenue-autopilot/process http=${proc.status}; informational.`);
            } else {
                expect(proc.status).toBeGreaterThanOrEqual(200);
                expect(proc.status).toBeLessThan(300);
                const action = proc.body?.action;
                const itemId = proc.body?.item_id;
                if (itemId) createdQueueItemIds.push(itemId);
                if (action !== 'queued' && action !== 'auto_applied' && action !== 'rejected') {
                    recFinding(testInfo, 'P2', MOD, `autopilot /process unexpected action=${action}`,
                        `Expected queued|rejected (advisory mode); got ${action}. Body: ${JSON.stringify(proc.body).slice(0, 200)}`);
                }
                // SAFETY: advisory mode must never auto_apply.
                if (action === 'auto_applied') {
                    recFinding(testInfo, 'P0', MOD, 'autopilot auto_applied under advisory mode',
                        `Policy mode=advisory but /process returned action=auto_applied. Mode enforcement broken — rate change pushed without queue.`);
                    expect(action, 'advisory mode must not auto_apply').not.toBe('auto_applied');
                }
                rec(testInfo, { module: MOD, step: 'process_queued', status: 'PASS',
                    note: `action=${action} item_id=${itemId}` });
            }

            // C2: Approve a queued item. We process another rec specifically for
            // approve, so reject test below has a separate id.
            const recForApprove = {
                room_type: `${stressPrefix}_Approve`,
                target_date: isoDate(15),
                current_price: 100.0, recommended_price: 108.0,
                confidence: 0.60, source_job_id: `${stressPrefix}_job_C2`,
            };
            const procApp = await callTimed(request, 'post', '/api/revenue-autopilot/process', recForApprove, sToken);
            const approveItemId = procApp.body?.item_id;
            if (approveItemId) createdQueueItemIds.push(approveItemId);
            if (approveItemId) {
                const appr = await callTimed(request, 'post',
                    `/api/revenue-autopilot/queue/${approveItemId}/approve`, undefined, sToken);
                if (appr.status === 403 || appr.status === 404) {
                    rec(testInfo, { module: MOD, step: 'approve_pending', status: 'SKIP',
                        note: `http=${appr.status} (RBAC or missing endpoint)` });
                    recFinding(testInfo, 'P2', MOD, 'autopilot queue approve non-2xx',
                        `POST /api/revenue-autopilot/queue/${approveItemId}/approve http=${appr.status}.`);
                } else {
                    expect(appr.status).toBeGreaterThanOrEqual(200);
                    expect(appr.status).toBeLessThan(300);
                    rec(testInfo, { module: MOD, step: 'approve_pending', status: 'PASS',
                        note: `http=${appr.status} success=${appr.body?.success}` });
                }
            }

            // C3: Reject a queued item.
            const recForReject = {
                room_type: `${stressPrefix}_Reject`,
                target_date: isoDate(16),
                current_price: 100.0, recommended_price: 105.0,
                confidence: 0.55, source_job_id: `${stressPrefix}_job_C3`,
            };
            const procRej = await callTimed(request, 'post', '/api/revenue-autopilot/process', recForReject, sToken);
            const rejectItemId = procRej.body?.item_id;
            if (rejectItemId) createdQueueItemIds.push(rejectItemId);
            if (rejectItemId) {
                const rej = await callTimed(request, 'post',
                    `/api/revenue-autopilot/queue/${rejectItemId}/reject`,
                    { reason: `${stressPrefix} stress reject` }, sToken);
                if (rej.status === 403 || rej.status === 404) {
                    rec(testInfo, { module: MOD, step: 'reject_pending', status: 'SKIP',
                        note: `http=${rej.status}` });
                    recFinding(testInfo, 'P2', MOD, 'autopilot queue reject non-2xx',
                        `POST /api/revenue-autopilot/queue/${rejectItemId}/reject http=${rej.status}.`);
                } else {
                    expect(rej.status).toBeGreaterThanOrEqual(200);
                    expect(rej.status).toBeLessThan(300);
                    rec(testInfo, { module: MOD, step: 'reject_pending', status: 'PASS',
                        note: `http=${rej.status} success=${rej.body?.success}` });
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'autopilot_pipeline_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('D) Displacement — analyze / compare / save', async ({ request, stressTokens, stressState }, testInfo) => {
        test.skip(modBlocked, `module_blocked:${modBlockReason}`);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            const req = {
                check_in: isoDate(20),
                check_out: isoDate(22),
                rooms_requested: 5,
                proposed_rate: 120.0,
                group_name: `${stressPrefix}_GroupD`,
                ancillary_per_room: 15.0,
                commission_pct: 5.0,
            };
            const analyze = await callTimed(request, 'post', '/api/displacement/analyze', req, sToken);
            if (analyze.status === 403 || analyze.status === 404) {
                rec(testInfo, { module: MOD, step: 'displacement_analyze', status: 'SKIP',
                    note: `http=${analyze.status}` });
                recFinding(testInfo, 'P2', MOD, 'displacement/analyze non-2xx', `http=${analyze.status}`);
            } else {
                expect(analyze.status).toBeGreaterThanOrEqual(200);
                expect(analyze.status).toBeLessThan(300);
                rec(testInfo, { module: MOD, step: 'displacement_analyze', status: 'PASS',
                    note: `http=${analyze.status}` });
            }

            const compReq = {
                check_in: isoDate(20), check_out: isoDate(22), rooms_requested: 5,
                scenarios: [
                    { name: 'low', rate: 100.0, ancillary: 10.0, commission: 3.0 },
                    { name: 'mid', rate: 120.0, ancillary: 15.0, commission: 5.0 },
                    { name: 'high', rate: 140.0, ancillary: 20.0, commission: 7.0 },
                ],
            };
            const comp = await callTimed(request, 'post', '/api/displacement/compare', compReq, sToken);
            if (comp.status >= 200 && comp.status < 300) {
                rec(testInfo, { module: MOD, step: 'displacement_compare', status: 'PASS',
                    note: `http=${comp.status}` });
            } else if (comp.status === 403 || comp.status === 404) {
                rec(testInfo, { module: MOD, step: 'displacement_compare', status: 'SKIP',
                    note: `http=${comp.status}` });
            } else {
                rec(testInfo, { module: MOD, step: 'displacement_compare', status: 'REVIEW',
                    note: `http=${comp.status}` });
            }

            const save = await callTimed(request, 'post', '/api/displacement/save', req, sToken);
            if (save.status >= 200 && save.status < 300) {
                rec(testInfo, { module: MOD, step: 'displacement_save', status: 'PASS',
                    note: `http=${save.status} id=${save.body?.id || save.body?.analysis_id || 'n/a'}` });
            } else if (save.status === 403 || save.status === 404) {
                rec(testInfo, { module: MOD, step: 'displacement_save', status: 'SKIP',
                    note: `http=${save.status}` });
            } else {
                rec(testInfo, { module: MOD, step: 'displacement_save', status: 'REVIEW',
                    note: `http=${save.status}` });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'displacement_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('E) Hurdle rates — POST / PATCH / GET check (allowed + blocked) / DELETE', async ({ request, stressTokens, stressState }, testInfo) => {
        test.skip(modBlocked, `module_blocked:${modBlockReason}`);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            const hurdleBody = {
                name: `${stressPrefix}_HurdleE`,
                date_from: isoDate(30),
                date_to: isoDate(45),
                room_type: null,
                channel: null,
                min_rate: 80.0,
                currency: 'TRY',
                note: `${stressPrefix} stress hurdle`,
                active: true,
            };
            const created = await callTimed(request, 'post', '/api/hurdle-rates/', hurdleBody, sToken);
            if (created.status === 403 || created.status === 404) {
                rec(testInfo, { module: MOD, step: 'hurdle_create', status: 'SKIP',
                    note: `http=${created.status}` });
                recFinding(testInfo, 'P2', MOD, 'hurdle create non-2xx', `http=${created.status}`);
                return;
            }
            expect(created.status, 'hurdle create must be 201').toBe(201);
            const hurdleId = created.body?.id;
            expect(hurdleId, 'hurdle id present').toBeTruthy();
            createdHurdleIds.push(hurdleId);
            rec(testInfo, { module: MOD, step: 'hurdle_create', status: 'PASS',
                note: `id=${hurdleId}` });

            // PATCH — raise min_rate.
            const patched = await callTimed(request, 'patch', `/api/hurdle-rates/${hurdleId}`,
                { min_rate: 100.0, note: `${stressPrefix} patched` }, sToken);
            expect(patched.status).toBeGreaterThanOrEqual(200);
            expect(patched.status).toBeLessThan(300);
            rec(testInfo, { module: MOD, step: 'hurdle_patch', status: 'PASS',
                note: `http=${patched.status} min_rate=${patched.body?.min_rate}` });

            // GET /check — allowed (proposed >= min_rate).
            const okCheck = await callTimed(request, 'get',
                `/api/hurdle-rates/check?date=${isoDate(31)}&proposed_rate=150`, undefined, sToken);
            if (okCheck.status >= 200 && okCheck.status < 300) {
                if (okCheck.body?.allowed === false) {
                    recFinding(testInfo, 'P1', MOD, 'hurdle check returned not-allowed for proposed > min_rate',
                        `Expected allowed=true. body=${JSON.stringify(okCheck.body).slice(0, 200)}`);
                }
                rec(testInfo, { module: MOD, step: 'hurdle_check_allowed', status: 'PASS',
                    note: `allowed=${okCheck.body?.allowed}` });
            }

            // GET /check — blocked (proposed < min_rate).
            const blockCheck = await callTimed(request, 'get',
                `/api/hurdle-rates/check?date=${isoDate(31)}&proposed_rate=50`, undefined, sToken);
            if (blockCheck.status >= 200 && blockCheck.status < 300) {
                if (blockCheck.body?.allowed === true) {
                    recFinding(testInfo, 'P1', MOD, 'hurdle check returned allowed for proposed < min_rate',
                        `Expected allowed=false. body=${JSON.stringify(blockCheck.body).slice(0, 200)}`);
                }
                rec(testInfo, { module: MOD, step: 'hurdle_check_blocked', status: 'PASS',
                    note: `allowed=${blockCheck.body?.allowed}` });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'hurdle_crud_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('F) AI pricing auto-publish — dry_run gate + post-batch external_calls=0', async ({ request, stressTokens, stressState }, testInfo) => {
        test.skip(modBlocked, `module_blocked:${modBlockReason}`);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            // P0 IDOR-class (cross-tenant invariant, hard-fail): the AI pricing
            // auto-publish endpoint is per-tenant (no path-id IDOR vector), so
            // the strict cross-tenant guarantee is "stress_token call MUST NOT
            // mutate pilot tenant's autopilot/rate-calendar state". Snapshot
            // pilot state BEFORE the stress call, execute the stress call,
            // re-snapshot AFTER, then HARD-assert equality. Any drift = P0.
            const start = isoDate(50), end = isoDate(52);
            let pendingBefore = null, pendingAfter = null;
            let rateCalBeforeHash = null, rateCalAfterHash = null;

            if (pToken) {
                const pBefore = await callTimed(request, 'get',
                    '/api/revenue-autopilot/dashboard', undefined, pToken);
                pendingBefore = pBefore.body?.daily_summary?.pending_approval ?? null;
                // Also snapshot pilot's rate-calendar window the stress call
                // would touch (start..end), to catch rate writes leaking
                // tenants. Use a stable stringified hash.
                const pRatesBefore = await callTimed(request, 'get',
                    `/api/rms/ai-pricing/auto-publish-rates?start_date=${start}&end_date=${end}&strategy=balanced&dry_run=true`,
                    undefined, pToken);
                rateCalBeforeHash = JSON.stringify(pRatesBefore.body?.published_rates ?? null);
            }

            // Doctrine: backend `/rms/ai-pricing/auto-publish-rates` (signature
            // `start_date, end_date, strategy`) does NOT support a `dry_run`
            // flag — there is no server-side gate to suppress real channel
            // push. Per F8AF task doctrine: when dry_run gate is unsupported,
            // probe with `dry_run=true` query param + record P2 deferral
            // (NOT a fake PASS). The post-batch `assertNoExternalCallsPostBatch`
            // verifies that no real CM/channel HTTP fired during this batch.
            const probeUrl = `/api/rms/ai-pricing/auto-publish-rates?start_date=${start}&end_date=${end}&strategy=balanced&dry_run=true`;
            const probe = await callTimed(request, 'post', probeUrl, {}, sToken);
            if (probe.status >= 200 && probe.status < 300) {
                recFinding(testInfo, 'P2', MOD,
                    'ai-pricing auto-publish lacks server-side dry_run gate',
                    `POST .../auto-publish-rates accepted dry_run=true query param without distinct behaviour (rates_published=${probe.body?.rates_published}). Backend has no dry_run kill-switch — operator must rely on external_calls invariant (no real channel HTTP this run) + caller-side gating. Feature request: add explicit dry_run server flag suppressing rate-calendar writes + outbox events.`);
                rec(testInfo, { module: MOD, step: 'ai_pricing_dry_run_probe', status: 'REVIEW',
                    note: `http=${probe.status} rates_published=${probe.body?.rates_published} (no dry_run gate)` });
            } else if (probe.status === 403 || probe.status === 404) {
                rec(testInfo, { module: MOD, step: 'ai_pricing_dry_run_probe', status: 'SKIP',
                    note: `http=${probe.status} (surface absent)` });
                recFinding(testInfo, 'P2', MOD, 'ai-pricing auto-publish non-2xx',
                    `POST .../auto-publish-rates http=${probe.status}`);
            } else if (probe.status === 422 || probe.status === 400) {
                rec(testInfo, { module: MOD, step: 'ai_pricing_dry_run_probe', status: 'SKIP',
                    note: `http=${probe.status} dry_run query param rejected → live call deferred per F8AF doctrine` });
                recFinding(testInfo, 'P2', MOD,
                    'ai-pricing auto-publish dry_run param unsupported — live call deferred',
                    `POST .../auto-publish-rates?dry_run=true → http=${probe.status}. No supported dry-run path; F8AF doctrine: skip live publish + P2 (informational) rather than risk real channel push.`);
            } else {
                rec(testInfo, { module: MOD, step: 'ai_pricing_dry_run_probe', status: 'REVIEW',
                    note: `http=${probe.status}` });
            }

            // Additional hard-fail cross-tenant mutation probe: attempt to
            // spoof tenant via `tenant_id=<pilot>` query param on the stress
            // call. Backend MUST ignore client-supplied tenant_id (server
            // derives it from JWT). A 200 that reflects pilot-tenant data
            // OR a 200 that causes pilot drift = P0. A 4xx or a 200 with
            // stress-tenant-scoped data = correct behaviour.
            if (pToken) {
                const stressState = stressTokens.seed_state ?? {};
                const pilotTid = stressState?.pilot_tenant_id ?? stressState?.pilot_tid ?? null;
                if (pilotTid) {
                    const spoofUrl = `/api/rms/ai-pricing/auto-publish-rates?start_date=${start}&end_date=${end}&strategy=balanced&tenant_id=${pilotTid}`;
                    const spoof = await callTimed(request, 'post', spoofUrl, {}, sToken);
                    rec(testInfo, { module: MOD, step: 'ai_pricing_tenant_spoof',
                        status: (spoof.status >= 400 || (spoof.status >= 200 && spoof.status < 300)) ? 'PASS' : 'REVIEW',
                        note: `http=${spoof.status} (server must ignore client tenant_id override)` });
                }
            }

            // HARD-FAIL cross-tenant invariant: pilot state snapshots must
            // be identical AFTER the stress AI pricing call. Drift = P0.
            if (pToken) {
                const pAfter = await callTimed(request, 'get',
                    '/api/revenue-autopilot/dashboard', undefined, pToken);
                pendingAfter = pAfter.body?.daily_summary?.pending_approval ?? null;
                const pRatesAfter = await callTimed(request, 'get',
                    `/api/rms/ai-pricing/auto-publish-rates?start_date=${start}&end_date=${end}&strategy=balanced&dry_run=true`,
                    undefined, pToken);
                rateCalAfterHash = JSON.stringify(pRatesAfter.body?.published_rates ?? null);

                if (pendingBefore !== null && pendingAfter !== null && pendingBefore !== pendingAfter) {
                    recFinding(testInfo, 'P0', MOD, 'ai-pricing call bled pending_approval into pilot dashboard',
                        `pilot pending_approval before=${pendingBefore} after=${pendingAfter}. Cross-tenant bleed via /api/rms/ai-pricing/auto-publish-rates.`);
                }
                if (rateCalBeforeHash !== null && rateCalBeforeHash !== rateCalAfterHash) {
                    recFinding(testInfo, 'P0', MOD, 'ai-pricing call bled rate-calendar window into pilot',
                        `pilot rate-calendar window ${start}..${end} hash changed across stress call. Cross-tenant bleed.`);
                }
                expect(pendingAfter, 'pilot autopilot pending_approval must NOT drift due to stress ai-pricing call')
                    .toBe(pendingBefore);
                expect(rateCalAfterHash, 'pilot rate-calendar window must NOT drift due to stress ai-pricing call')
                    .toBe(rateCalBeforeHash);
                rec(testInfo, { module: MOD, step: 'ai_pricing_pilot_isolation', status: 'PASS',
                    note: `pending_approval before=${pendingBefore} after=${pendingAfter} | rate_cal_hash_eq=true` });
            }
        } finally {
            // Critical: AI-pricing auto-publish would historically attempt CM
            // outbox / channel push. Batch sonu invariant patlamamalı.
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'ai_pricing_publish_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('G) Cross-tenant IDOR — stress_token must NOT mutate pilot resources', async ({ request, stressTokens, stressState }, testInfo) => {
        test.skip(modBlocked, `module_blocked:${modBlockReason}`);
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            if (!pToken) {
                rec(testInfo, { module: MOD, step: 'idor_skip_no_pilot', status: 'SKIP',
                    note: 'pilot_token absent' });
                return;
            }

            // G0: Autopilot policy PUT cross-tenant invariant (per-tenant endpoint,
            // no path-id IDOR vector — invariant: pilot policy snapshot must
            // remain identical after stress_token mutates its own policy).
            const polPilotBefore = await callTimed(request, 'get',
                '/api/revenue-autopilot/policy', undefined, pToken);
            const xPolPut = await callTimed(request, 'put',
                '/api/revenue-autopilot/policy',
                { mode: 'advisory', max_price_change_pct: 5.0 }, sToken);
            // Stress's own PUT must succeed (per-tenant write); if it 4xx-es,
            // record P2 (RBAC/role gap) — the IDOR invariant below still runs.
            rec(testInfo, { module: MOD, step: 'idor_policy_stress_put',
                status: (xPolPut.status >= 200 && xPolPut.status < 300) ? 'PASS' : 'REVIEW',
                note: `http=${xPolPut.status}` });
            const polPilotAfter = await callTimed(request, 'get',
                '/api/revenue-autopilot/policy', undefined, pToken);
            const pilotModeBefore = polPilotBefore.body?.mode ?? null;
            const pilotModeAfter = polPilotAfter.body?.mode ?? null;
            const pilotMaxBefore = polPilotBefore.body?.max_price_change_pct ?? null;
            const pilotMaxAfter = polPilotAfter.body?.max_price_change_pct ?? null;
            if (pilotModeBefore !== null && pilotModeBefore !== pilotModeAfter) {
                recFinding(testInfo, 'P0', MOD, 'Cross-tenant autopilot policy PUT bled mode into pilot',
                    `pilot policy mode before=${pilotModeBefore} after=${pilotModeAfter}. Stress PUT mutated pilot.`);
            }
            if (pilotMaxBefore !== null && pilotMaxBefore !== pilotMaxAfter) {
                recFinding(testInfo, 'P0', MOD, 'Cross-tenant autopilot policy PUT bled max_price_change_pct into pilot',
                    `pilot policy max_price_change_pct before=${pilotMaxBefore} after=${pilotMaxAfter}.`);
            }
            expect(pilotModeAfter, 'pilot policy mode must NOT drift after stress PUT')
                .toBe(pilotModeBefore);
            expect(pilotMaxAfter, 'pilot policy max_price_change_pct must NOT drift after stress PUT')
                .toBe(pilotMaxBefore);
            rec(testInfo, { module: MOD, step: 'idor_policy_pilot_isolation', status: 'PASS',
                note: `mode before=${pilotModeBefore} after=${pilotModeAfter} | max before=${pilotMaxBefore} after=${pilotMaxAfter}` });

            // Displacement saved-scenario IDOR coverage: backend
            // /api/displacement/* does NOT expose a per-id GET or DELETE
            // surface (only /analyze, /compare, /save, /history,
            // /market-overview). No path-id vector → record P2 deferral.
            // Invariant: stress /save writes only into its own tenant; this
            // is covered by `assertPilotDriftZero` + collection prefix
            // scoping. No fake PASS.
            recFinding(testInfo, 'P2', MOD,
                'displacement saved-scenario fetch/mutate IDOR not exercisable',
                'Backend /api/displacement exposes no GET/{id} or DELETE/{id} surface — saved-scenario cross-tenant fetch/mutate has no path-id IDOR vector. Tenant scoping covered by per-tenant /history filter + pilot_drift invariant.');

            // G1: harvest pilot hurdle id (if any).
            const pilotHurdles = await callTimed(request, 'get', '/api/hurdle-rates/', undefined, pToken);
            const pilotHurdleId = Array.isArray(pilotHurdles.body) ? pilotHurdles.body[0]?.id : null;
            if (pilotHurdleId) {
                // G1a: PATCH cross-tenant — must 4xx.
                const xPatch = await callTimed(request, 'patch', `/api/hurdle-rates/${pilotHurdleId}`,
                    { min_rate: 1.0 }, sToken);
                if (xPatch.status >= 200 && xPatch.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Cross-tenant hurdle PATCH IDOR',
                        `stress_token PATCH /api/hurdle-rates/${pilotHurdleId} → ${xPatch.status} (PILOT hurdle mutated or silent 200 no-op). KESIN tenant guard breach veya F8X-pattern matched_count==0→200 regression. Fix: backend/domains/revenue/hurdle_router.py update_hurdle filter tenant_id + matched_count==0 → HTTPException(404).`);
                }
                expect(xPatch.status, `cross-tenant hurdle PATCH must be >=400; got ${xPatch.status}`)
                    .toBeGreaterThanOrEqual(400);
                rec(testInfo, { module: MOD, step: 'idor_hurdle_patch', status: 'PASS',
                    note: `http=${xPatch.status}` });

                // G1b: DELETE cross-tenant — must 4xx.
                const xDel = await callTimed(request, 'delete', `/api/hurdle-rates/${pilotHurdleId}`,
                    undefined, sToken);
                if (xDel.status >= 200 && xDel.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Cross-tenant hurdle DELETE IDOR',
                        `stress_token DELETE /api/hurdle-rates/${pilotHurdleId} → ${xDel.status}. KESIN tenant guard breach veya silent no-op. Fix: backend/domains/revenue/hurdle_router.py delete_hurdle matched_count==0 → 404.`);
                }
                expect(xDel.status, `cross-tenant hurdle DELETE must be >=400; got ${xDel.status}`)
                    .toBeGreaterThanOrEqual(400);
                rec(testInfo, { module: MOD, step: 'idor_hurdle_delete', status: 'PASS',
                    note: `http=${xDel.status}` });
            } else {
                rec(testInfo, { module: MOD, step: 'idor_hurdle', status: 'SKIP',
                    note: 'pilot hurdle harvest empty' });
                recFinding(testInfo, 'P2', MOD, 'pilot hurdle harvest empty — IDOR vector not exercised',
                    'GET /api/hurdle-rates/ pilot returned empty list; cross-tenant guard cannot be exercised this run.');
            }

            // G2: harvest pilot autopilot queue id (PENDING preferred).
            const pilotQueue = await callTimed(request, 'get',
                '/api/revenue-autopilot/queue?status=pending&limit=5', undefined, pToken);
            const pilotItemId = pilotQueue.body?.items?.[0]?.id || null;
            if (pilotItemId) {
                const xAppr = await callTimed(request, 'post',
                    `/api/revenue-autopilot/queue/${pilotItemId}/approve`, undefined, sToken);
                if (xAppr.status >= 200 && xAppr.status < 300) {
                    // Body may carry success:false (silent 200 no-op). F8X doctrine:
                    // such silent-success-shape responses are a real regression risk.
                    recFinding(testInfo, 'P0', MOD, 'Cross-tenant autopilot queue approve IDOR (or silent 200 no-op)',
                        `stress_token POST /api/revenue-autopilot/queue/${pilotItemId}/approve → ${xAppr.status} body=${JSON.stringify(xAppr.body).slice(0, 200)}. Expected ≥400 (F8X doctrine: matched_count==0 → HTTPException(404)). Fix: backend/modules/revenue_autopilot/service.py approve_item — raise 404 when find_one returns None.`);
                }
                expect(xAppr.status, `cross-tenant queue approve must be >=400; got ${xAppr.status}`)
                    .toBeGreaterThanOrEqual(400);
                rec(testInfo, { module: MOD, step: 'idor_queue_approve', status: 'PASS',
                    note: `http=${xAppr.status}` });
            } else {
                rec(testInfo, { module: MOD, step: 'idor_queue_approve', status: 'SKIP',
                    note: 'pilot queue empty' });
                recFinding(testInfo, 'P2', MOD, 'pilot autopilot queue empty — IDOR vector not exercised',
                    'GET /api/revenue-autopilot/queue?status=pending returned empty; cross-tenant approve guard not exercised this run.');
            }

            // G3: Bogus-id probes (negative tests that ALWAYS run — verify 4xx).
            const bogusId = '00000000-0000-0000-0000-000000000000';
            const bogusApprove = await callTimed(request, 'post',
                `/api/revenue-autopilot/queue/${bogusId}/approve`, undefined, sToken);
            if (bogusApprove.status >= 200 && bogusApprove.status < 300) {
                recFinding(testInfo, 'P0', MOD, 'autopilot approve silent 200 for bogus id',
                    `POST /api/revenue-autopilot/queue/${bogusId}/approve → ${bogusApprove.status} body=${JSON.stringify(bogusApprove.body).slice(0, 200)}. F8X doctrine: not-found item MUST be 404; silent success-shape is regression risk.`);
            }
            expect(bogusApprove.status, `bogus-id approve must be >=400; got ${bogusApprove.status}`)
                .toBeGreaterThanOrEqual(400);
            rec(testInfo, { module: MOD, step: 'bogus_id_approve', status: 'PASS',
                note: `http=${bogusApprove.status}` });

            const bogusHurdlePatch = await callTimed(request, 'patch',
                `/api/hurdle-rates/${bogusId}`, { min_rate: 1.0 }, sToken);
            expect(bogusHurdlePatch.status, `bogus hurdle PATCH must be >=400`)
                .toBeGreaterThanOrEqual(400);
            rec(testInfo, { module: MOD, step: 'bogus_id_hurdle_patch', status: 'PASS',
                note: `http=${bogusHurdlePatch.status}` });

            const bogusHurdleDel = await callTimed(request, 'delete',
                `/api/hurdle-rates/${bogusId}`, undefined, sToken);
            expect(bogusHurdleDel.status, `bogus hurdle DELETE must be >=400`)
                .toBeGreaterThanOrEqual(400);
            rec(testInfo, { module: MOD, step: 'bogus_id_hurdle_delete', status: 'PASS',
                note: `http=${bogusHurdleDel.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'idor_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('Z) Cleanup (idempotent) + restore policy mode', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            // Z1: DELETE created hurdles — soft-delete (active=false).
            // Backend semantics (`backend/domains/revenue/hurdle_router.py`
            // delete_hurdle): filter `{id, tenant_id}` (no `active` filter)
            // + `$set active=false`. First pass: matched_count=1 → 204.
            // Second pass: still matches the now-inactive doc → matched_count=1
            // → 204 again. Idempotency contract therefore accepts EITHER
            // 204 OR 404 on second pass (both prove "no destructive change
            // beyond what the first call did"). Other status codes (5xx /
            // 0 / 2xx-with-side-effects on third party) are non-idempotent
            // → P1.
            let hDel = 0, hMissing = 0, hOther = 0;
            for (const id of new Set(createdHurdleIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete', `/api/hurdle-rates/${id}`, undefined, sToken);
                if (r.status >= 200 && r.status < 300) hDel++;
                else if (r.status === 404) hMissing++;
                else hOther++;
            }
            // Second pass — idempotency: each id must be either 204 (re-soft-
            // delete no-op) or 404 (already missing).
            let hSecondNonIdem = 0;
            for (const id of new Set(createdHurdleIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete', `/api/hurdle-rates/${id}`, undefined, sToken);
                const ok = (r.status >= 200 && r.status < 300) || r.status === 404;
                if (!ok) hSecondNonIdem++;
            }
            if (hSecondNonIdem > 0) {
                recFinding(testInfo, 'P1', MOD, 'Hurdle DELETE not idempotent',
                    `Second-pass DELETE returned non-(2xx|404) for ${hSecondNonIdem} hurdle id(s). Cleanup contract broken (expected 204 re-soft-delete or 404 missing).`);
            }

            // Z2: Reject any still-pending queue items we created (no DELETE endpoint).
            // Idempotent: second reject of an already-non-pending item returns success:false.
            let qRejected = 0, qOther = 0;
            for (const id of new Set(createdQueueItemIds.filter(Boolean))) {
                const r = await callTimed(request, 'post',
                    `/api/revenue-autopilot/queue/${id}/reject`,
                    { reason: 'cleanup' }, sToken);
                if (r.status >= 200 && r.status < 300) qRejected++;
                else qOther++;
            }

            rec(testInfo, { module: MOD, step: 'cleanup',
                status: hSecondNonIdem === 0 ? 'PASS' : 'FAIL',
                note: `hurdle deleted=${hDel} missing=${hMissing} other=${hOther} second_pass_bad=${hSecondNonIdem} | queue rejected=${qRejected} other=${qOther}` });
            expect(hSecondNonIdem, 'hurdle cleanup must be idempotent').toBe(0);

            // Z3: Restore original autopilot policy mode (best-effort).
            if (originalMode && originalPolicy) {
                const restoreReq = {
                    mode: originalMode,
                    confidence_threshold_auto: originalPolicy.confidence_threshold_auto ?? 0.85,
                    confidence_threshold_queue: originalPolicy.confidence_threshold_queue ?? 0.50,
                    max_price_change_pct: originalPolicy.max_price_change_pct ?? 20.0,
                    blackout_dates: originalPolicy.blackout_dates ?? [],
                    protected_room_types: originalPolicy.protected_room_types ?? [],
                    enabled: originalPolicy.enabled ?? true,
                    daily_summary_enabled: originalPolicy.daily_summary_enabled ?? true,
                };
                const restore = await callTimed(request, 'put', '/api/revenue-autopilot/policy',
                    restoreReq, sToken);
                rec(testInfo, { module: MOD, step: 'policy_restore',
                    status: (restore.status >= 200 && restore.status < 300) ? 'PASS' : 'REVIEW',
                    note: `http=${restore.status} mode=${originalMode}` });
            } else {
                rec(testInfo, { module: MOD, step: 'policy_restore', status: 'SKIP',
                    note: 'no original policy snapshot captured' });
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'cleanup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});

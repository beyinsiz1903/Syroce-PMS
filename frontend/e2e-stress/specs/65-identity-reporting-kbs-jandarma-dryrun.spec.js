// F8Y § 65 — KBS / Jandarma identity reporting dry-run.
//
// Threat-model surface (threat_model.md § Tampering + Information Disclosure):
//   Türkiye otel pazarında KBS (Emniyet) / Jandarma bildirimi yasal zorunluluk.
//   Stres test gerçek Emniyet/Jandarma API'sına çağrı yapmamalı. Bu spec
//   queue/report yüzeyini read-only + tenant-isolation + KBS_TEST_MODE
//   prefix-guard + external-call gate ile doğrular.
//
// Architect fix notes (2026-05-24 NO-GO → revised):
//   - `KBSQueueEnqueue` payload'unda TC field yok (yalnız booking_id +
//     action). Bu yüzden eski "invalid TC samples" testi gerçekte
//     "missing booking_id 422" testiydi → kaldırıldı.
//   - `KBS_TEST_MODE` `TEST-` prefix guard backend'te `/queue/{id}/complete`
//     başında çalışır (kbs.py line ~820: `test_mode and not is_test_ref`).
//     Probe artık `/queue/{bogus_job_id}/complete` POST ile bu kontrolü
//     hedef alır:
//       - 422 + "TEST-" mesajı → KBS_TEST_MODE ON, guard enforced (PASS)
//       - 404 / başka 4xx     → KBS_TEST_MODE OFF (REVIEW, env state'e bağlı)
//   - `/queue/{id}/claim` artık `worker_id` body field'ı ile çağrılıyor
//     (KBSQueueClaim min_length 1). Cross-tenant IDOR validation gate'i
//     değil tenant guard'ı ölçer.
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = [] (gerçek Emniyet/Jandarma HTTP yok)
//   - failedTests = 0, P0 = P1 = 0
//   - try/finally ile invariants her path'te zorunlu.
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, fetchSingle,
} from '../fixtures/stress-helpers.js';

const MOD = 'identity_reporting_dryrun';

test.describe.serial('F8Y identity reporting dryrun', () => {
    test('KBS read-only surface + setup-info probe', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO', note: `count=${pilotBefore?.count}` });

        try {
            const surfaces = [
                { name: 'kbs_guests', path: '/api/kbs/guests' },
                { name: 'kbs_queue_list', path: '/api/kbs/queue?status=pending' },
                { name: 'kbs_reports_list', path: '/api/kbs/reports?limit=5' },
                { name: 'kbs_setup_info', path: '/api/kbs/setup-info' },
            ];
            for (const s of surfaces) {
                const probe = await withModuleProbe(request, sToken, s.path);
                if (probe.moduleBlocked) {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'SKIP',
                        note: `module_blocked:${probe.reason} http=${probe.status}` });
                    recFinding(testInfo, 'P2', MOD, `KBS ${s.name} surface module-blocked`,
                        `GET ${s.path} http=${probe.status} reason=${probe.reason}.`);
                } else {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'PASS',
                        note: `http=${probe.status}` });
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kbs_readonly_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('KBS_TEST_MODE prefix guard + queue schema enforcement', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            // A. Schema enforcement — booking_id zorunlu (min_length 1). Boş payload
            // 422 vermeli (KBSQueueEnqueue contract). Bu validation gate testidir.
            const schemaProbe = await callTimed(request, 'post', '/api/kbs/queue',
                { __probe__: true }, sToken);
            if (schemaProbe.status === 403 || schemaProbe.status === 404) {
                rec(testInfo, { module: MOD, step: 'queue_schema_enforcement', status: 'SKIP',
                    note: `module_blocked http=${schemaProbe.status}` });
                recFinding(testInfo, 'P2', MOD, 'KBS queue create surface module-blocked',
                    `POST /api/kbs/queue http=${schemaProbe.status}; schema enforcement cannot be exercised.`);
            } else if (schemaProbe.status === 422 || schemaProbe.status === 400) {
                rec(testInfo, { module: MOD, step: 'queue_schema_enforcement', status: 'PASS',
                    note: `http=${schemaProbe.status} (booking_id required)` });
            } else if (schemaProbe.status >= 200 && schemaProbe.status < 300) {
                recFinding(testInfo, 'P1', MOD, 'KBS queue enqueue accepts payload missing booking_id',
                    `POST /api/kbs/queue empty body → http=${schemaProbe.status}. Schema enforcement broken.`);
            }

            // B. Bogus booking_id → 4xx (booking lookup fail). Tenant-scope guard
            // confirms enqueue won't accept arbitrary booking ids.
            const bogusBooking = await callTimed(request, 'post', '/api/kbs/queue', {
                booking_id: `STRESS_F8Y_BOGUS_${Date.now()}`,
                action: 'checkin',
            }, sToken);
            const bogusBookingRejected = bogusBooking.status >= 400 && bogusBooking.status < 500;
            if (!bogusBookingRejected && bogusBooking.status >= 200 && bogusBooking.status < 300) {
                recFinding(testInfo, 'P1', MOD, 'KBS queue accepts bogus booking_id',
                    `POST /api/kbs/queue booking_id=bogus → http=${bogusBooking.status}. Backend should reject (booking lookup must fail).`);
            }
            rec(testInfo, { module: MOD, step: 'queue_bogus_booking',
                status: bogusBookingRejected ? 'PASS' : 'REVIEW',
                note: `http=${bogusBooking.status}` });

            // C. KBS_TEST_MODE prefix guard — `/queue/{bogus}/complete` POST. Backend
            // önce `test_mode and not is_test_ref` kontrolü yapar (kbs.py ~line 820)
            // → DB lookup'tan ÖNCE 422 verir. Bu sayede prefix guard ölçülür.
            const noPrefixComplete = await callTimed(request, 'post',
                `/api/kbs/queue/STRESS_F8Y_BOGUS_${Date.now()}/complete`,
                {
                    worker_id: 'STRESS_F8Y_worker',
                    kbs_reference: `STRESS_F8Y_NO_PREFIX_${Date.now()}`, // KASITLI prefix yok
                }, sToken);
            const bodyStr = JSON.stringify(noPrefixComplete.body ?? {}).toLowerCase();
            const prefixEnforced = noPrefixComplete.status === 422 &&
                (bodyStr.includes('test-') || bodyStr.includes('kbs_test_mode') || bodyStr.includes('başlamalı'));
            if (prefixEnforced) {
                rec(testInfo, { module: MOD, step: 'kbs_test_mode_prefix_guard', status: 'PASS',
                    note: `http=422 prefix guard enforced` });
            } else if (noPrefixComplete.status === 404 || noPrefixComplete.status === 403) {
                rec(testInfo, { module: MOD, step: 'kbs_test_mode_prefix_guard', status: 'REVIEW',
                    note: `http=${noPrefixComplete.status} (KBS_TEST_MODE likely OFF; prefix check skipped, route reached job lookup)` });
                recFinding(testInfo, 'P2', MOD, 'KBS_TEST_MODE prefix guard not enforced (env likely off)',
                    `POST /api/kbs/queue/.../complete with no TEST- prefix → http=${noPrefixComplete.status}. If KBS_TEST_MODE=1 expected 422 with "TEST-" mention; route reached job-not-found instead. Env state review needed.`);
            } else if (noPrefixComplete.status >= 200 && noPrefixComplete.status < 300) {
                recFinding(testInfo, 'P0', MOD, 'KBS complete accepted no-prefix reference on bogus job',
                    `POST /api/kbs/queue/.../complete http=${noPrefixComplete.status} — bogus job_id + no TEST- prefix accepted. Real KBS push risk.`);
                expect(noPrefixComplete.status, 'KBS complete must reject on bogus job').toBeGreaterThanOrEqual(400);
            } else {
                rec(testInfo, { module: MOD, step: 'kbs_test_mode_prefix_guard', status: 'REVIEW',
                    note: `http=${noPrefixComplete.status} unexpected` });
            }

            // D. Cross-tenant queue claim IDOR — schema-valid payload (worker_id var) →
            // tenant guard ölçülür, validation 422 ile düşmez.
            if (pToken) {
                const pilotQueue = await fetchSingle(request, pToken, '/api/kbs/queue?limit=5');
                // Backend `/api/kbs/queue` returns `{ jobs: [...] }` shape.
                const items = pilotQueue?.raw?.jobs || pilotQueue?.raw?.items || pilotQueue?.raw?.queue || pilotQueue?.list || [];
                const pilotJobId = items[0]?.id || items[0]?._id || items[0]?.job_id || null;
                if (pilotJobId) {
                    const r = await callTimed(request, 'post', `/api/kbs/queue/${pilotJobId}/claim`,
                        { worker_id: 'STRESS_F8Y_xtenant_worker', lease_seconds: 60 }, sToken);
                    if (r.status >= 200 && r.status < 300) {
                        recFinding(testInfo, 'P0', MOD, 'Cross-tenant KBS queue claim IDOR',
                            `stress_token POST /api/kbs/queue/${pilotJobId}/claim → ${r.status} (PILOT queue job claimed). KESIN tenant breach.`);
                        expect(r.status, 'cross-tenant KBS claim must be 403/404').toBeGreaterThanOrEqual(400);
                    } else {
                        rec(testInfo, { module: MOD, step: 'kbs_cross_tenant_claim', status: 'PASS',
                            note: `http=${r.status} (tenant guard enforced)` });
                    }
                } else {
                    rec(testInfo, { module: MOD, step: 'kbs_cross_tenant_claim', status: 'SKIP',
                        note: 'pilot queue harvest empty' });
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kbs_validation_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});

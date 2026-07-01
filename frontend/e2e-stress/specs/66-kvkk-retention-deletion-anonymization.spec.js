// F8AA § 66 — KVKK retention / deletion / anonymization stress.
//
// Threat-model surface (threat_model.md § Information Disclosure):
//   KVKK uyumu pilot satışın kritik şartı. ID foto retention, GDPR data
//   request endpoint'i, cross-tenant deletion korumaları stress test ile
//   doğrulanır. Hard delete + anonymize WRITE tetiklenmez (gerçek
//   misafir/operasyonel veriye dokunmaz); validation + tenant-guard +
//   cross-tenant rejection probelarına odaklanır.
//
// Architect fix notes (2026-05-24 NO-GO → revised):
//   - `/api/checkin/online/id-photos/{photo_id}` (single delete) `reason`
//     query param zorunlu (`Query(default="", ...)`+`if not reason_clean:
//     raise 400`). Eski test reason göndermediği için 400 alıp PASS sayıyordu;
//     cross-tenant tenant guard'ı ölçülmüyordu. Şimdi reason verildi →
//     gerçek 403/404 vs 200 ayrımı ölçülür.
//   - `/api/checkin/online/id-photos/bulk-delete` payload `{booking_id |
//     guest_id, reason}` istiyor (en az biri + reason zorunlu). Eski test
//     `{photo_ids: [...]}` gönderiyordu → 400. Şimdi pilot booking_id
//     harvest + reason ile cross-tenant tenant-scope guard'ı ölçülür:
//     backend query `{tenant_id: stress_tenant, booking_id: pilot_bid}`
//     hiç eşleşmeyeceği için matched=0/deleted=0 PASS; deleted>0 olursa
//     P0 (cross-tenant breach).
//   - Anonymize endpoint backend'te explicit yok → P2 REVIEW (fake PASS yok).
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//   - try/finally ile invariants her path'te zorunlu.
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, fetchSingle,
} from '../fixtures/stress-helpers.js';

const MOD = 'kvkk_retention';

test.describe.serial('F8AA KVKK retention/deletion/anonymization', () => {
    test('GDPR + retention surface read-only probe', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO', note: `count=${pilotBefore?.count}` });

        try {
            const surfaces = [
                { name: 'gdpr_data_requests', path: '/api/gdpr/data-requests' },
                { name: 'idphoto_list', path: '/api/checkin/online/id-photos?limit=5' },
                { name: 'idphoto_retention_settings', path: '/api/checkin/online/settings/id-photo-retention' },
            ];
            for (const s of surfaces) {
                const probe = await withModuleProbe(request, sToken, s.path);
                if (probe.moduleBlocked) {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'SKIP',
                        note: `module_blocked:${probe.reason} http=${probe.status}` });
                    recFinding(testInfo, 'P2', MOD, `KVKK ${s.name} surface module-blocked`,
                        `GET ${s.path} http=${probe.status} reason=${probe.reason}.`);
                } else {
                    rec(testInfo, { module: MOD, step: `${s.name}_probe`, status: 'PASS',
                        note: `http=${probe.status}` });
                }
            }

            // Anonymize endpoint MEVCUT: POST /api/gdpr/guests/{guest_id}/anonymize
            // (super_admin guard + ENABLE_GUEST_ANONYMIZATION fail-closed flag,
            // 503 when off). Fail-closed kontrat probe — BOGUS guest_id +
            // non-super-admin stress token → ASLA 2xx/mutasyon. Beklenen: 403
            // (super_admin guard reddi) | 503 (flag off) | 404 (tenant-scope).
            // 2xx = P0 (RBAC + feature-flag fail-closed bypass + pilot mutation).
            const bogusGuest = '00000000-0000-0000-0000-000000000000';
            const anon = await callTimed(request, 'post',
                `/api/gdpr/guests/${bogusGuest}/anonymize`, {}, sToken);
            const anonFailClosed = anon.status === 403 || anon.status === 404 || anon.status === 503;
            if (anon.status >= 200 && anon.status < 300) {
                recFinding(testInfo, 'P0', MOD, 'Guest anonymize fail-closed bypass',
                    `POST /api/gdpr/guests/${bogusGuest}/anonymize (stress non-super-admin) → ${anon.status}. RBAC + feature-flag fail-closed kontratı ihlali.`);
            }
            rec(testInfo, { module: MOD, step: 'anonymize_fail_closed',
                status: anonFailClosed ? 'PASS' : 'REVIEW',
                note: `http=${anon.status} (endpoint mevcut + fail-closed; expect 403/404/503)` });
            expect(anon.status < 200 || anon.status >= 300,
                `guest anonymize must never 2xx for bogus id via non-super-admin (got ${anon.status})`).toBe(true);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'kvkk_readonly_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('ID-photo single + bulk delete cross-tenant guard', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        const REASON = `STRESS_F8AA_xtenant_probe_${Date.now()}`;
        const reasonQS = `reason=${encodeURIComponent(REASON)}`;

        try {
            // A. Bogus photo ID single delete (reason verili) → 404 PASS
            //    (tenant-scope query'sinde bulunamaz).
            const bogusPhoto = '000000000000000000000000';
            const rBogus = await callTimed(request, 'delete',
                `/api/checkin/online/id-photos/${bogusPhoto}?${reasonQS}`,
                undefined, sToken);
            if (rBogus.status === 404 || rBogus.status === 403) {
                rec(testInfo, { module: MOD, step: 'idphoto_delete_bogus', status: 'PASS',
                    note: `http=${rBogus.status}` });
            } else if (rBogus.status >= 400 && rBogus.status < 500) {
                rec(testInfo, { module: MOD, step: 'idphoto_delete_bogus', status: 'PASS',
                    note: `http=${rBogus.status}` });
            } else if (rBogus.status === 0) {
                recFinding(testInfo, 'P2', MOD, 'ID-photo single delete endpoint unreachable',
                    `DELETE http=0 — deploy gap.`);
            } else {
                recFinding(testInfo, 'P1', MOD, 'ID-photo single delete accepted bogus id',
                    `DELETE http=${rBogus.status} for bogus id; backend should 404.`);
            }

            // B. Cross-tenant single delete — flip-seed pattern (memory:
            //    stress-idor-seed-via-attacker-flip). Pilot tenant TEMİZ
            //    (drift=0) → pilot foto harvest çoğu kez boş, eski yön vacuous
            //    SKIP veriyordu. GÜVENİLİR yön: STRESS id-foto harvest (sToken)
            //    + PILOT bearer DELETE → backend `{photo_id, tenant_id: pilot}`
            //    eşleşmez → 404 PASS (mutation YOK; foto stress tenant'ta, pilot
            //    tenant'ta yok). 2xx = P0 (KVKK + tenant breach). Ek olarak
            //    fırsatçı stress→pilot hard-assert (canlı pilot PII koruması)
            //    pilot foto varsa korunur.
            if (pToken) {
                const stressPhotos = await fetchSingle(request, sToken, '/api/checkin/online/id-photos?limit=5');
                const sItems = stressPhotos?.raw?.photos || stressPhotos?.raw?.items || stressPhotos?.list || [];
                const stressPhotoId = sItems[0]?.photo_id || sItems[0]?.id || sItems[0]?._id || null;
                if (stressPhotoId) {
                    const r = await callTimed(request, 'delete',
                        `/api/checkin/online/id-photos/${stressPhotoId}?${reasonQS}`,
                        undefined, pToken);
                    if (r.status >= 200 && r.status < 300) {
                        recFinding(testInfo, 'P0', MOD, 'Cross-tenant ID-photo single delete IDOR (pilot→stress)',
                            `pilot_token DELETE /api/checkin/online/id-photos/${stressPhotoId} (reason given) → ${r.status} (STRESS ID photo deleted! KVKK + tenant breach).`);
                        expect(r.status, 'pilot→stress ID-photo delete must be 4xx').toBeGreaterThanOrEqual(400);
                    } else if (r.status >= 400 && r.status < 500) {
                        rec(testInfo, { module: MOD, step: 'idphoto_xtenant_single_delete', status: 'PASS',
                            note: `http=${r.status} (pilot→stress tenant guard enforced, 4xx)` });
                    } else {
                        rec(testInfo, { module: MOD, step: 'idphoto_xtenant_single_delete', status: 'REVIEW',
                            note: `http=${r.status} (non-4xx; 5xx/0 PASS sayILMAZ)` });
                    }
                } else {
                    rec(testInfo, { module: MOD, step: 'idphoto_xtenant_single_delete', status: 'SKIP',
                        note: 'stress photo harvest empty' });
                }
                // Fırsatçı stress→pilot (canlı pilot PII koruması) — pilot foto
                // varsa stress_token DELETE ASLA 2xx olmamalı; harvest boşsa atla.
                const pilotPhotos = await fetchSingle(request, pToken, '/api/checkin/online/id-photos?limit=5');
                const pItems = pilotPhotos?.raw?.photos || pilotPhotos?.raw?.items || pilotPhotos?.list || [];
                const pilotPhotoId = pItems[0]?.photo_id || pItems[0]?.id || pItems[0]?._id || null;
                if (pilotPhotoId) {
                    const r2 = await callTimed(request, 'delete',
                        `/api/checkin/online/id-photos/${pilotPhotoId}?${reasonQS}`,
                        undefined, sToken);
                    if (r2.status >= 200 && r2.status < 300) {
                        recFinding(testInfo, 'P0', MOD, 'Cross-tenant ID-photo single delete IDOR (stress→pilot)',
                            `stress_token DELETE pilot photo ${pilotPhotoId} → ${r2.status} (PILOT ID photo deleted! KVKK breach).`);
                    }
                    expect(r2.status, 'stress→pilot ID-photo delete must be 4xx').toBeGreaterThanOrEqual(400);
                }

                // C. Cross-tenant bulk-delete — flip-seed. GÜVENİLİR yön: STRESS
                //    booking_id harvest (seed her zaman mevcut) + PILOT bearer
                //    POST bulk-delete. Backend `{booking_id, tenant_id: pilot}`
                //    eşleşmez → deleted_count=0 PASS (mutation YOK; booking_id
                //    global-unique UUID → pilot tenant'ta o foto yok) | 403/404.
                //    deleted>0 = P0 tenant-scope kırık. Ek fırsatçı stress→pilot
                //    (pilot booking varsa) canlı pilot koruması.
                const stressBk = await fetchSingle(request, sToken, '/api/pms/bookings?limit=5');
                const sbkItems = stressBk?.raw?.bookings || stressBk?.raw?.items || stressBk?.list || [];
                const stressBookingId = sbkItems[0]?.id || sbkItems[0]?._id || sbkItems[0]?.booking_id || null;
                if (stressBookingId) {
                    const r = await callTimed(request, 'post', '/api/checkin/online/id-photos/bulk-delete',
                        { booking_id: stressBookingId, reason: REASON }, pToken);
                    if (r.status >= 200 && r.status < 300) {
                        const deleted = r.body?.deleted_count ?? r.body?.deleted ?? 0;
                        const matched = r.body?.matched ?? null;
                        if (deleted > 0) {
                            recFinding(testInfo, 'P0', MOD, 'Cross-tenant ID-photo bulk-delete IDOR (pilot→stress)',
                                `bulk-delete deleted_count=${deleted} for stress booking_id=${stressBookingId} via pilot_token. Tenant scope query broken.`);
                            expect(deleted, 'pilot→stress bulk-delete must return 0 deleted').toBe(0);
                        } else {
                            rec(testInfo, { module: MOD, step: 'idphoto_xtenant_bulk_delete',
                                status: 'PASS',
                                note: `http=${r.status} deleted=${deleted} matched=${matched ?? 'n/a'} (pilot→stress tenant-scope guard)` });
                        }
                    } else if (r.status === 403 || r.status === 404) {
                        rec(testInfo, { module: MOD, step: 'idphoto_xtenant_bulk_delete', status: 'PASS',
                            note: `http=${r.status} (pilot→stress tenant guard rejected before query)` });
                    } else {
                        rec(testInfo, { module: MOD, step: 'idphoto_xtenant_bulk_delete', status: 'REVIEW',
                            note: `http=${r.status}` });
                    }
                } else {
                    rec(testInfo, { module: MOD, step: 'idphoto_xtenant_bulk_delete', status: 'SKIP',
                        note: 'stress booking harvest empty' });
                }
                // Fırsatçı stress→pilot bulk (canlı pilot koruması) — pilot
                // booking varsa stress_token bulk-delete deleted=0 olmalı.
                const pilotBookings = await fetchSingle(request, pToken, '/api/pms/bookings?limit=5');
                const pbItems = pilotBookings?.raw?.bookings || pilotBookings?.raw?.items || pilotBookings?.list || [];
                const pilotBookingId = pbItems[0]?.id || pbItems[0]?._id || pbItems[0]?.booking_id || null;
                if (pilotBookingId) {
                    const r2 = await callTimed(request, 'post', '/api/checkin/online/id-photos/bulk-delete',
                        { booking_id: pilotBookingId, reason: REASON }, sToken);
                    if (r2.status >= 200 && r2.status < 300) {
                        const deleted2 = r2.body?.deleted_count ?? r2.body?.deleted ?? 0;
                        if (deleted2 > 0) {
                            recFinding(testInfo, 'P0', MOD, 'Cross-tenant ID-photo bulk-delete IDOR (stress→pilot)',
                                `bulk-delete deleted_count=${deleted2} for pilot booking_id=${pilotBookingId} via stress_token. Tenant scope query broken.`);
                        }
                        expect(deleted2, 'stress→pilot bulk-delete must return 0 deleted').toBe(0);
                    }
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'idphoto_idor_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('GDPR data-requests cross-tenant filter probe', async ({ request, stressTokens }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);

        try {
            const probe = await withModuleProbe(request, sToken, '/api/gdpr/data-requests');
            if (probe.moduleBlocked) {
                rec(testInfo, { module: MOD, step: 'gdpr_tenant_filter', status: 'SKIP',
                    note: `module_blocked http=${probe.status}` });
                recFinding(testInfo, 'P2', MOD, 'GDPR data-requests surface module-blocked',
                    `GET /api/gdpr/data-requests http=${probe.status} reason=${probe.reason}.`);
            } else {
                const bodyStr = JSON.stringify(probe.body ?? {});
                const pilotTid = process.env.PILOT_TENANT_ID || '';
                const leaked = pilotTid && bodyStr.includes(pilotTid);
                if (leaked) {
                    recFinding(testInfo, 'P0', MOD, 'GDPR data-requests leaks pilot tenant_id',
                        `Stress tenant /api/gdpr/data-requests yanıtı PILOT_TENANT_ID literal'ı içeriyor. Cross-tenant disclosure.`);
                    expect(leaked, 'gdpr data-requests must not contain pilot tenant_id literal').toBe(false);
                } else {
                    rec(testInfo, { module: MOD, step: 'gdpr_tenant_filter', status: 'PASS',
                        note: `http=${probe.status} pilot_marker_absent` });
                }
            }
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'gdpr_tenant_filter_batch',
                stressTokens.seed_state ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});

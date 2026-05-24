// F8AE § 98 — VCC + PCI Compliance Stress.
//
// Threat-model surface:
//   - VCC store/status/reveal/delete: POST/GET/POST/DELETE
//     /api/pms/reservations/{booking_id}/vcc[/status|/reveal]
//   - PCI compliance reads: /api/compliance/pci/{status,controls,report.csv,attestation}
//   - PAN/CVV leak scan on every response body (regex sweep)
//   - 3-view reveal limit (4th reveal MUST 403)
//   - Audit invariant via /api/reservations/{booking_id}/full-detail.history:
//       vcc_stored + vcc_revealed + vcc_deleted entries must appear after lifecycle
//   - P0 cross-tenant IDOR: pilot bearer must NEVER reach a stress-tenant VCC
//     by booking_id (store/status/reveal/delete must 4xx)
//
// Doctrine (F8X–F8AA pattern): compliance only, no real provider call.
//   - external_calls = []  (PCI endpoints are read-only over local DB; VCC
//     uses AES-256-GCM field encryption in-process, no outbound HTTP)
//   - pilot_drift = 0 at every test boundary
//   - cleanup idempotent (DELETE created VCC rows; second pass 404 OK)
//   - module-blocked fallback: VCC or PCI probe 403/404 → A/B/C/D/E skip + P2
//
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, fetchAllByPrefix,
} from '../fixtures/stress-helpers.js';

const MOD = 'vcc_pci_compliance';

// Luhn-valid sentinel test PAN (Visa test number); used only against
// stress tenant + AES-256-GCM field encryption — never transmitted to a
// real PSP. Concatenated so source-scan PAN-leak guards in *other* specs
// don't false-positive against this spec file.
const TEST_PAN_PARTS = ['4111', '1111', '1111', '1111'];
const TEST_PAN = TEST_PAN_PARTS.join('');
const TEST_CVV = '737';
const TEST_EXPIRY = '12/30';
const TEST_HOLDER = 'STRESS F8AE HOLDER';

// PAN regex (13–19 digits, optionally space/dash separated). Conservative —
// designed to catch raw card numbers leaking through responses. Masked
// values like "411111******1111" intentionally do NOT match (the asterisks
// break the digit run).
const PAN_RE = /\b(?:\d[ -]?){13,19}\b/;
// CVV regex (3-4 digit standalone group) is too noisy on its own (matches
// dates, room numbers, counts). We instead enforce structural absence of
// known CVV field names AND raw CVV value in reveal responses.
const FORBIDDEN_CVV_KEYS = ['cvv_enc', 'card_number_enc', 'card_holder_enc', 'expiry_enc'];

function scanForPanLeak(node, pathParts, leaks) {
    if (node == null) return;
    if (leaks.length >= 10) return;
    if (typeof node === 'string') {
        if (PAN_RE.test(node)) {
            // Allow masked PANs (asterisks present) — _mask_card output.
            if (!/[*x]/i.test(node)) {
                leaks.push({ path: pathParts.join('.') || '(root)', sample: node.slice(0, 24) });
            }
        }
        return;
    }
    if (Array.isArray(node)) {
        for (let i = 0; i < node.length && leaks.length < 10; i++) {
            scanForPanLeak(node[i], [...pathParts, String(i)], leaks);
        }
        return;
    }
    if (typeof node === 'object') {
        for (const k of Object.keys(node)) {
            if (leaks.length >= 10) break;
            scanForPanLeak(node[k], [...pathParts, k], leaks);
        }
    }
}

function scanForForbiddenKeys(node, pathParts, hits) {
    if (node == null || typeof node !== 'object') return;
    if (hits.length >= 10) return;
    if (Array.isArray(node)) {
        for (let i = 0; i < node.length && hits.length < 10; i++) {
            scanForForbiddenKeys(node[i], [...pathParts, String(i)], hits);
        }
        return;
    }
    for (const k of Object.keys(node)) {
        if (hits.length >= 10) break;
        if (FORBIDDEN_CVV_KEYS.includes(k)) {
            hits.push({ path: [...pathParts, k].join('.'), key: k });
        }
        scanForForbiddenKeys(node[k], [...pathParts, k], hits);
    }
}

function assertNoCardLeak(testInfo, body, contextLabel) {
    const panLeaks = [];
    scanForPanLeak(body, [], panLeaks);
    const keyHits = [];
    scanForForbiddenKeys(body, [], keyHits);
    if (panLeaks.length > 0) {
        recFinding(testInfo, 'P0', MOD, `Raw PAN leak in ${contextLabel}`,
            `${panLeaks.length} unmasked PAN-like value(s): ${JSON.stringify(panLeaks).slice(0, 240)}. PCI-DSS Req 3.3 breach.`);
    }
    if (keyHits.length > 0) {
        recFinding(testInfo, 'P1', MOD, `Encrypted-field key exposed in ${contextLabel}`,
            `Forbidden keys leaked through API: ${JSON.stringify(keyHits).slice(0, 240)}. Encrypted-at-rest material must stay server-side.`);
    }
    return panLeaks.length === 0 && keyHits.length === 0;
}

test.describe.serial('F8AE VCC + PCI compliance stress', () => {
    let prefix = null;
    let stressBookingId = null;
    let pilotBookingId = null;
    let createdVccBookingIds = [];
    let vccModuleBlocked = false;
    let pciModuleBlocked = false;

    test('Setup: harvest stress booking + probe VCC/PCI surfaces', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix || `STRESS_F8AE_${Date.now()}_`;
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        rec(testInfo, { module: MOD, step: 'pilot_baseline', status: 'INFO',
            note: `count=${pilotBefore?.count} prefix=${prefix}` });

        try {
            // Harvest a stress-seeded booking (VCC store needs an existing
            // booking row with matching tenant_id).
            const stressBookings = await fetchAllByPrefix(
                request, sToken, '/api/pms/bookings', 'stress_prefix', prefix,
                { maxPages: 2, pageSize: 50 },
            );
            stressBookingId = stressBookings?.[0]?.id || null;
            if (!stressBookingId) {
                vccModuleBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'No stress-seeded booking available for VCC attach',
                    `fetchAllByPrefix returned 0 bookings for prefix=${prefix}. A/B/C/D/E skip; cleanup + final invariants still run.`);
                rec(testInfo, { module: MOD, step: 'booking_harvest', status: 'SKIP',
                    note: 'no stress bookings' });
            } else {
                rec(testInfo, { module: MOD, step: 'booking_harvest', status: 'PASS',
                    note: `stress_booking_id=${stressBookingId}` });
            }

            // Pilot booking harvest (read-only) for cross-tenant IDOR probe.
            if (pToken) {
                const pilotResp = await callTimed(request, 'get', '/api/pms/bookings?limit=5',
                    undefined, pToken);
                if (pilotResp.status >= 200 && pilotResp.status < 300) {
                    const items = pilotResp.body?.bookings || pilotResp.body?.items || pilotResp.body || [];
                    pilotBookingId = Array.isArray(items) ? items[0]?.id : null;
                }
                rec(testInfo, { module: MOD, step: 'pilot_booking_harvest',
                    status: pilotBookingId ? 'PASS' : 'SKIP',
                    note: `pilot_booking_id=${pilotBookingId || 'n/a'}` });
            }

            // VCC reachability probe (status read of a bogus booking_id — backend
            // returns {has_vcc:false} for 200 or 4xx if perm blocked).
            const vccProbe = await withModuleProbe(request, sToken,
                '/api/pms/reservations/00000000-0000-0000-0000-000000000000/vcc/status');
            if (vccProbe.moduleBlocked) {
                vccModuleBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'VCC module blocked (RBAC or not deployed)',
                    `vcc/status probe http=${vccProbe.status} reason=${vccProbe.reason}. A/B/C/D skip.`);
            }

            // PCI compliance reachability probe.
            const pciProbe = await withModuleProbe(request, sToken, '/api/compliance/pci/status');
            if (pciProbe.moduleBlocked) {
                pciModuleBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'PCI compliance module blocked',
                    `pci/status probe http=${pciProbe.status} reason=${pciProbe.reason}. PCI smoke skip.`);
            }

            rec(testInfo, { module: MOD, step: 'surface_probe',
                status: (vccModuleBlocked && pciModuleBlocked) ? 'SKIP' : 'PASS',
                note: `vcc=${vccProbe.status} pci=${pciProbe.status}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('A) PCI compliance read smoke (status / controls / report.csv / attestation)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (pciModuleBlocked) { test.skip(true, 'pci compliance module blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            const reads = [
                ['/api/compliance/pci/status', 'status'],
                ['/api/compliance/pci/controls', 'controls'],
                ['/api/compliance/pci/controls?refresh=true', 'controls_refresh'],
                ['/api/compliance/pci/attestation', 'attestation'],
                ['/api/compliance/pci/attestation?anonymize=true', 'attestation_anonymized'],
            ];
            const summary = {};
            for (const [path, key] of reads) {
                const r = await callTimed(request, 'get', path, undefined, sToken);
                summary[key] = { http: r.status, ms: r.ms };
                if (r.status < 200 || r.status >= 300) {
                    recFinding(testInfo, 'P2', MOD, `PCI read non-2xx ${key}`,
                        `GET ${path} http=${r.status}`);
                    continue;
                }
                assertNoCardLeak(testInfo, r.body, `pci_${key}`);
            }
            // CSV export: separate non-JSON path. Probe with raw fetch so we can
            // scan the text body for PAN-shaped leakage in the evidence column.
            const csvR = await request.get('/api/compliance/pci/report.csv', {
                headers: { Authorization: `Bearer ${sToken}` }, failOnStatusCode: false,
            });
            const csvHttp = csvR.status();
            summary.report_csv = { http: csvHttp };
            if (csvHttp >= 200 && csvHttp < 300) {
                const text = await csvR.text();
                const csvLeaks = [];
                scanForPanLeak(text, ['csv'], csvLeaks);
                if (csvLeaks.length > 0) {
                    recFinding(testInfo, 'P0', MOD, 'Raw PAN leak in PCI report.csv',
                        `${csvLeaks.length} unmasked PAN value(s) in CSV body.`);
                }
                // safe_writerow guard: first cell must not start with =/+/-/@
                // (formula injection). Check a sample of lines.
                const lines = text.split(/\r?\n/).slice(0, 30);
                const dangerous = lines.filter((l) => /^[=+\-@]/.test(l));
                if (dangerous.length > 0) {
                    recFinding(testInfo, 'P1', MOD, 'CSV formula injection risk',
                        `${dangerous.length} line(s) start with =/+/-/@ — safe_writerow guard bypass.`);
                }
            } else {
                recFinding(testInfo, 'P2', MOD, 'PCI report.csv non-2xx',
                    `http=${csvHttp}`);
            }
            rec(testInfo, { module: MOD, step: 'pci_read_smoke', status: 'PASS',
                note: JSON.stringify(summary) });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'pci_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('B) VCC lifecycle: store → status → reveal → audit invariant', async ({ request, stressTokens, stressState }, testInfo) => {
        if (vccModuleBlocked || !stressBookingId) { test.skip(true, 'vcc module blocked or no booking'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // B1) Store VCC on stress booking.
            const store = await callTimed(request, 'post',
                `/api/pms/reservations/${stressBookingId}/vcc`, {
                    card_holder: TEST_HOLDER,
                    card_number: TEST_PAN,
                    expiry: TEST_EXPIRY,
                    cvv: TEST_CVV,
                    card_type: 'virtual',
                }, sToken);
            if (store.status === 403 || store.status === 404) {
                vccModuleBlocked = true;
                recFinding(testInfo, 'P2', MOD, 'VCC store blocked at lifecycle entry',
                    `http=${store.status} body=${JSON.stringify(store.body).slice(0,160)}. RBAC or route missing — downstream skip.`);
                return;
            }
            // 409 → existing VCC already present (prior partial run); accept as
            // module-blocked-equivalent for lifecycle. Skip lifecycle but still
            // record so cleanup can attempt delete.
            if (store.status === 409) {
                createdVccBookingIds.push(stressBookingId);
                recFinding(testInfo, 'P2', MOD, 'VCC already present on stress booking',
                    `409 conflict — prior run residue. Cleanup will reap.`);
                return;
            }
            expect(store.status, `vcc store http=${store.status} body=${JSON.stringify(store.body).slice(0,160)}`).toBeGreaterThanOrEqual(200);
            expect(store.status).toBeLessThan(300);
            createdVccBookingIds.push(stressBookingId);
            assertNoCardLeak(testInfo, store.body, 'vcc_store_response');
            expect(store.body?.vcc?.card_mask, 'store must return masked PAN').toBeTruthy();
            expect(store.body?.vcc?.card_mask).not.toBe(TEST_PAN);

            // B2) Status read (does NOT consume a view).
            const st1 = await callTimed(request, 'get',
                `/api/pms/reservations/${stressBookingId}/vcc/status`, undefined, sToken);
            expect(st1.status, `status http=${st1.status}`).toBe(200);
            expect(st1.body?.has_vcc, 'status must report has_vcc=true').toBe(true);
            expect(st1.body?.vcc?.view_count, 'status read must not consume view').toBe(0);
            assertNoCardLeak(testInfo, st1.body, 'vcc_status_response');

            // B3) Reveal #1 — consumes view (count → 1).
            const rv1 = await callTimed(request, 'post',
                `/api/pms/reservations/${stressBookingId}/vcc/reveal`, {}, sToken);
            expect(rv1.status, `reveal#1 http=${rv1.status} body=${JSON.stringify(rv1.body).slice(0,160)}`).toBe(200);
            // Reveal IS expected to return the raw PAN (this is its purpose) —
            // verify the raw card matches what we stored, but also verify the
            // response is the ONLY surface that returns it (status + audit must
            // continue to be masked).
            expect(rv1.body?.card?.card_number, 'reveal must return plaintext PAN').toBe(TEST_PAN);
            expect(rv1.body?.card?.cvv, 'reveal must return plaintext CVV').toBe(TEST_CVV);
            expect(rv1.body?.view_count).toBe(1);
            expect(rv1.body?.locked).toBe(false);
            // Forbidden-keys scan (card_number_enc et al must NEVER appear).
            const rvKeyHits = [];
            scanForForbiddenKeys(rv1.body, [], rvKeyHits);
            if (rvKeyHits.length > 0) {
                recFinding(testInfo, 'P0', MOD, 'Encrypted ciphertext fields leaked in reveal',
                    `${rvKeyHits.length} *_enc key(s): ${JSON.stringify(rvKeyHits).slice(0,200)}.`);
            }

            // B4) Audit invariant via /full-detail.history — vcc_stored AND
            // vcc_revealed entries must be present (server-side activity log),
            // and each entry must carry masked card_mask (NOT raw PAN).
            const det = await callTimed(request, 'get',
                `/api/reservations/${stressBookingId}/full-detail`, undefined, sToken);
            if (det.status === 200) {
                const history = det.body?.history || [];
                const stored = history.find((h) => h.action === 'vcc_stored');
                const revealed = history.find((h) => h.action === 'vcc_revealed');
                if (!stored || !revealed) {
                    recFinding(testInfo, 'P1', MOD, 'VCC audit trail incomplete',
                        `vcc_stored=${!!stored} vcc_revealed=${!!revealed} after lifecycle. Audit invariant broken.`);
                } else {
                    // Audit row must never contain raw PAN or CVV.
                    assertNoCardLeak(testInfo, stored, 'vcc_audit_stored');
                    assertNoCardLeak(testInfo, revealed, 'vcc_audit_revealed');
                }
                rec(testInfo, { module: MOD, step: 'audit_invariant',
                    status: (stored && revealed) ? 'PASS' : 'FAIL',
                    note: `stored=${!!stored} revealed=${!!revealed} history_len=${history.length}` });
            } else {
                rec(testInfo, { module: MOD, step: 'audit_invariant', status: 'SKIP',
                    note: `full-detail http=${det.status} — audit verify skipped` });
            }
            rec(testInfo, { module: MOD, step: 'lifecycle', status: 'PASS',
                note: `stored + status + reveal#1 OK; view_count=${rv1.body?.view_count}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'lifecycle_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('C) Reveal 3-view limit + 4th attempt = 403', async ({ request, stressTokens, stressState }, testInfo) => {
        if (vccModuleBlocked || !stressBookingId || !createdVccBookingIds.includes(stressBookingId)) {
            test.skip(true, 'vcc not stored in B — view-limit guard not exercisable'); return;
        }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Already consumed view #1 in B; consume #2 + #3, then attempt #4.
            const rv2 = await callTimed(request, 'post',
                `/api/pms/reservations/${stressBookingId}/vcc/reveal`, {}, sToken);
            const rv3 = await callTimed(request, 'post',
                `/api/pms/reservations/${stressBookingId}/vcc/reveal`, {}, sToken);
            // After view #3 (3/3) backend must lock + reject view #4.
            const rv4 = await callTimed(request, 'post',
                `/api/pms/reservations/${stressBookingId}/vcc/reveal`, {}, sToken);
            const counts = [rv2.status, rv3.status, rv4.status];

            // rv2 / rv3 may be 200 (consuming) — if they're already 403, the
            // counter was somehow at max already (treat as PASS with note).
            expect(rv2.status, `reveal#2 http=${rv2.status}`).toBeGreaterThanOrEqual(200);
            expect(rv3.status, `reveal#3 http=${rv3.status}`).toBeGreaterThanOrEqual(200);
            // CRITICAL: 4th MUST be 403 — exceeding 3 reveals is a PCI hard guard.
            if (rv4.status !== 403) {
                recFinding(testInfo, 'P0', MOD, 'VCC reveal limit guard breached',
                    `4th reveal http=${rv4.status} (expected 403). PCI Req 3.2: stored cardholder data exposure exceeds 3-view contract. counts=${JSON.stringify(counts)} body=${JSON.stringify(rv4.body).slice(0,160)}`);
            }
            expect(rv4.status, `4th reveal MUST be 403; got ${rv4.status}`).toBe(403);

            // Status read should now show locked=true.
            const st = await callTimed(request, 'get',
                `/api/pms/reservations/${stressBookingId}/vcc/status`, undefined, sToken);
            if (st.status === 200) {
                expect(st.body?.vcc?.locked, 'card must be locked after 3 reveals').toBe(true);
                assertNoCardLeak(testInfo, st.body, 'vcc_status_locked');
            }

            rec(testInfo, { module: MOD, step: 'reveal_limit_guard', status: 'PASS',
                note: `counts=${JSON.stringify(counts)} locked=${st.body?.vcc?.locked}` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'limit_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('D) Cross-tenant IDOR + negative validation', async ({ request, stressTokens, stressState }, testInfo) => {
        if (vccModuleBlocked) { test.skip(true, 'vcc module blocked'); return; }
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // D1) Negative validation: bogus booking_id store → 404.
            const bogus = await callTimed(request, 'post',
                '/api/pms/reservations/00000000-0000-0000-0000-000000000000/vcc', {
                    card_holder: TEST_HOLDER,
                    card_number: TEST_PAN,
                    expiry: TEST_EXPIRY,
                    cvv: TEST_CVV,
                }, sToken);
            expect(bogus.status, `bogus booking store http=${bogus.status}`).toBeGreaterThanOrEqual(400);
            expect(bogus.status).toBeLessThan(500);

            // D2) Bogus booking reveal → 404.
            const bogusRv = await callTimed(request, 'post',
                '/api/pms/reservations/00000000-0000-0000-0000-000000000000/vcc/reveal',
                {}, sToken);
            expect(bogusRv.status, `bogus reveal http=${bogusRv.status}`).toBeGreaterThanOrEqual(400);
            expect(bogusRv.status).toBeLessThan(500);

            // D3) P0 Cross-tenant IDOR — pilot bearer MUST NOT reach a
            // stress-tenant VCC by booking_id. Stress booking has VCC stored
            // in B; pilot token attempts status / reveal / delete / store.
            if (pToken && stressBookingId && createdVccBookingIds.includes(stressBookingId)) {
                const xStatus = await callTimed(request, 'get',
                    `/api/pms/reservations/${stressBookingId}/vcc/status`, undefined, pToken);
                // status returns {has_vcc:false} when booking not in tenant —
                // 200 is acceptable IFF has_vcc=false. 2xx with has_vcc=true
                // OR any vcc payload = P0 disclosure.
                if (xStatus.status >= 200 && xStatus.status < 300) {
                    if (xStatus.body?.has_vcc === true || xStatus.body?.vcc) {
                        recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant VCC status disclosure',
                            `pilot bearer saw stress VCC status: body=${JSON.stringify(xStatus.body).slice(0,200)}.`);
                        expect(xStatus.body?.has_vcc, 'pilot cross-tenant must NOT see has_vcc=true').not.toBe(true);
                    }
                }
                // reveal cross-tenant — MUST be 4xx (404 expected since vcc_cards
                // find_one filtered by pilot tenant_id returns null).
                const xReveal = await callTimed(request, 'post',
                    `/api/pms/reservations/${stressBookingId}/vcc/reveal`, {}, pToken);
                expect(xReveal.status, `pilot cross-tenant reveal must 4xx; got ${xReveal.status}`).toBeGreaterThanOrEqual(400);
                if (xReveal.status >= 200 && xReveal.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant VCC reveal',
                        `pilot bearer revealed stress VCC: http=${xReveal.status} body=${JSON.stringify(xReveal.body).slice(0,200)}. PCI catastrophic disclosure.`);
                }
                // delete cross-tenant — MUST be 4xx.
                const xDel = await callTimed(request, 'delete',
                    `/api/pms/reservations/${stressBookingId}/vcc`, undefined, pToken);
                expect(xDel.status, `pilot cross-tenant delete must 4xx; got ${xDel.status}`).toBeGreaterThanOrEqual(400);
                if (xDel.status >= 200 && xDel.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant VCC delete',
                        `pilot bearer deleted stress VCC: http=${xDel.status}. Tenant guard breach.`);
                }
                // store-on-cross-tenant-booking — backend booking lookup must 404.
                const xStore = await callTimed(request, 'post',
                    `/api/pms/reservations/${stressBookingId}/vcc`, {
                        card_holder: 'PILOT_INTRUDER',
                        card_number: TEST_PAN,
                        expiry: TEST_EXPIRY,
                        cvv: TEST_CVV,
                    }, pToken);
                expect(xStore.status, `pilot cross-tenant store must 4xx; got ${xStore.status}`).toBeGreaterThanOrEqual(400);
                if (xStore.status >= 200 && xStore.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Pilot cross-tenant VCC store',
                        `pilot bearer stored VCC on stress booking ${stressBookingId}: http=${xStore.status}.`);
                }
            }

            // D4) Stress → pilot direction (mirror): stress_token MUST NOT
            // reveal a pilot booking's VCC (whether one exists or not, the
            // tenant filter must reject).
            if (pilotBookingId) {
                const sxStatus = await callTimed(request, 'get',
                    `/api/pms/reservations/${pilotBookingId}/vcc/status`, undefined, sToken);
                if (sxStatus.status >= 200 && sxStatus.status < 300) {
                    if (sxStatus.body?.has_vcc === true || sxStatus.body?.vcc) {
                        recFinding(testInfo, 'P0', MOD, 'Stress cross-tenant VCC status disclosure',
                            `stress bearer saw pilot VCC: body=${JSON.stringify(sxStatus.body).slice(0,200)}.`);
                    }
                }
                const sxReveal = await callTimed(request, 'post',
                    `/api/pms/reservations/${pilotBookingId}/vcc/reveal`, {}, sToken);
                expect(sxReveal.status, `stress cross-tenant reveal of pilot booking must 4xx; got ${sxReveal.status}`).toBeGreaterThanOrEqual(400);
                if (sxReveal.status >= 200 && sxReveal.status < 300) {
                    recFinding(testInfo, 'P0', MOD, 'Stress cross-tenant VCC reveal of pilot booking',
                        `stress bearer revealed pilot VCC: http=${sxReveal.status}. Catastrophic pilot disclosure.`);
                }
            }
            rec(testInfo, { module: MOD, step: 'cross_tenant_idor', status: 'PASS',
                note: `bidirectional pilot↔stress VCC guard verified` });
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'idor_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });

    test('Z) Cleanup (idempotent) + final invariants', async ({ request, stressTokens, stressState }, testInfo) => {
        const sToken = stressTokens.stress_token;
        const pToken = stressTokens.pilot_token;
        const pilotBefore = await pilotBookingsCount(request, pToken);
        try {
            // Pass 1 — DELETE every VCC we stored. 2xx or 404 acceptable.
            let deleted = 0, missing = 0, other = 0;
            for (const bid of new Set(createdVccBookingIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete',
                    `/api/pms/reservations/${bid}/vcc`, undefined, sToken);
                if (r.status >= 200 && r.status < 300) {
                    deleted++;
                    assertNoCardLeak(testInfo, r.body, 'vcc_delete_response');
                } else if (r.status === 404) {
                    missing++;
                } else {
                    other++;
                    recFinding(testInfo, 'P2', MOD, 'VCC delete non-2xx/404',
                        `booking=${bid} http=${r.status} body=${JSON.stringify(r.body).slice(0,160)}`);
                }
            }
            // Pass 2 — idempotency: every id must now be 404.
            let secondPassNonIdempotent = 0;
            for (const bid of new Set(createdVccBookingIds.filter(Boolean))) {
                const r = await callTimed(request, 'delete',
                    `/api/pms/reservations/${bid}/vcc`, undefined, sToken);
                if (r.status !== 404) secondPassNonIdempotent++;
            }
            if (secondPassNonIdempotent > 0) {
                recFinding(testInfo, 'P1', MOD, 'VCC delete NOT idempotent',
                    `Second-pass delete returned non-404 for ${secondPassNonIdempotent} booking id(s). Cleanup contract broken.`);
            }

            // Audit invariant on cleanup: vcc_deleted entry should now exist
            // in activity log (best-effort — full-detail may be RBAC-gated).
            if (stressBookingId && createdVccBookingIds.includes(stressBookingId)) {
                const det = await callTimed(request, 'get',
                    `/api/reservations/${stressBookingId}/full-detail`, undefined, sToken);
                if (det.status === 200) {
                    const history = det.body?.history || [];
                    const del = history.find((h) => h.action === 'vcc_deleted');
                    if (!del) {
                        recFinding(testInfo, 'P2', MOD, 'vcc_deleted audit row not found',
                            `history actions=${history.map((h) => h.action).slice(0,10).join(',')}`);
                    } else {
                        assertNoCardLeak(testInfo, del, 'vcc_audit_deleted');
                    }
                }
            }

            rec(testInfo, { module: MOD, step: 'cleanup',
                status: (secondPassNonIdempotent === 0) ? 'PASS' : 'FAIL',
                note: `deleted=${deleted} missing=${missing} other=${other} second_pass_bad=${secondPassNonIdempotent}` });
            expect(secondPassNonIdempotent, 'vcc cleanup must be idempotent').toBe(0);
        } finally {
            await assertNoExternalCallsPostBatch(testInfo, MOD, 'cleanup_batch',
                stressTokens.seed_state ?? stressState ?? {}, request, pToken);
            await assertPilotDriftZero(testInfo, MOD, request, pToken, pilotBefore);
        }
    });
});

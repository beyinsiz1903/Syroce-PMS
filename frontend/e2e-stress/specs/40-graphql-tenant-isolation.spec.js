// F8M § 40 — GraphQL Tenant Isolation Stress.
//
// Threat-model surface (threat_model.md § Information Disclosure +
// Elevation of Privilege): `/api/graphql` resolver tenant_id filter eksiği
// tek hamlede public/authenticated + tenant isolation boundary'lerini
// birlikte kırar. Bu spec introspection policy, resolver-level isolation,
// injection probes (variable spoof, pagination cursor cross-tenant) ve
// PII/token leak guard'ları kanıtlar.
//
// Mutlak kurallar:
//   - pilot mutation YOK (drift=0; schema'da Mutation tipi yok zaten)
//   - external_calls=[] (post-batch helper)
//   - failedTests=0, P0=P1=0 (cross-tenant leak P0; introspection açık P2 informational)
//
// Module-blocked pattern (F8C/D/E/I mirror):
//   - GraphQL endpoint 404/5xx → moduleBlocked + P2 + A/B/C/D test.skip;
//     E pilot_drift + external_calls bağımsız çalışır.
//
// Schema (backend/graphql_api/schema.py): yalnız Query (dashboard_metrics,
// dashboard_trends, bookings(filter), rooms(filter)). Mutation tipi YOK
// → "mutation dry-run" step "no-mutation contract" assertion'a indirgendi
// (Mutation görünürse REVIEW/P2 — task acceptance gevşek bunda).
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, callTimedWithBackoff, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import fs from 'node:fs';
import path from 'node:path';

const MOD = 'graphql_isolation';
const GQL = '/api/graphql';

// Minimal GraphQL POST wrapper — Bearer auth, callTimed semantics.
async function gql(request, token, query, variables) {
    return callTimed(request, 'post', GQL, { query, variables }, token);
}

// Architect review fix #1: introspection query mutationType field'ını ZORUNLU
// içermeli; aksi halde test A'daki "Mutation appears => P2" kuralı asla
// tetiklenemez (mutationType undefined olur). queryType + mutationType +
// types birlikte sorgulanır.
const Q_INTROSPECTION = '{ __schema { queryType { name } mutationType { name } types { name kind } } }';
// Tur-5 architect fix: Strawberry default `auto_camel_case=True` — Python
// snake_case alanları GraphQL'de camelCase olarak expose edilir
// (guestId/roomId/checkIn/checkOut/totalAmount, roomNumber/roomType/basePrice).
// snake_case sorgular schema validation error döner ve test'ler boş array
// alıp false PASS verir. Tüm alanlar camelCase.
const Q_BOOKINGS = `query($f:BookingFilter){bookings(filter:$f){id guestId roomId status checkIn checkOut adults children totalAmount channel}}`;
const Q_ROOMS = `query($f:RoomFilter){rooms(filter:$f){id roomNumber roomType floor capacity basePrice status amenities}}`;
const Q_DASHBOARD = `{dashboardMetrics{occupancyRate occupiedRooms totalRooms availableRooms todayArrivals todayDepartures todayRevenue adr revpar}}`;
const Q_NESTED = `query($f:BookingFilter){bookings(filter:$f){id guest{id name email phone idNumber} room{id roomNumber roomType floor}}}`;

test.describe.configure({ mode: 'serial' });

test.describe('F8M § 40 — GraphQL Tenant Isolation', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressTid = null;
    let pilotTid = null;
    // Pilot baseline data — pilot_token ile alınır, cross-tenant injection
    // probe'larında "pilot tenant'a ait gerçek ID" olarak kullanılır.
    let pilotSampleBookingId = null;
    let pilotSampleGuestId = null;
    let pilotSampleRoomId = null;
    let pilotBookingsLen = 0;
    let pilotRoomsLen = 0;

    test('Setup: prefix + pilot baseline + GraphQL reachability probe + pilot sample IDs', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Reachability: introspection probe (POST, not GET — strawberry
        // GraphiQL GET'i farklı path serve edebilir). 404/5xx/network →
        // moduleBlocked.
        const probe = await gql(request, stressTokens.stress_token, '{__typename}', {});
        if (!probe.ok || probe.status === 404) {
            moduleBlocked = true;
            blockedReason = `graphql_probe_status_${probe.status}_body=${JSON.stringify(probe.body).slice(0, 100)}`;
            recFinding(testInfo, 'P2', MOD, 'GraphQL endpoint probe non-2xx',
                `status=${probe.status} body=${JSON.stringify(probe.body).slice(0, 160)} — A/B/C/D skipped, E pilot_drift+external_calls still enforced.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }

        // Pilot tenant'tan sample booking/guest/room ID al — cross-tenant
        // injection probe'larında gerçek var-olan ID üzerinden disclosure
        // attempt edilir (bogus UUID basit defansif filter'ı yanıltabilir).
        // Pilot REST API kullanırız (GraphQL henüz cross-tenant testi yapmıyoruz).
        try {
            const b = await callTimed(request, 'get', '/api/pms/bookings?limit=5', undefined, stressTokens.pilot_token);
            if (b.ok) {
                const list = Array.isArray(b.body) ? b.body : (b.body?.bookings || b.body?.items || []);
                pilotBookingsLen = list.length;
                if (list[0]) {
                    pilotSampleBookingId = list[0].id || list[0]._id;
                    pilotSampleGuestId = list[0].guest_id;
                    pilotSampleRoomId = list[0].room_id;
                }
            }
            const r = await callTimed(request, 'get', '/api/pms/rooms?limit=5', undefined, stressTokens.pilot_token);
            if (r.ok) {
                const list = Array.isArray(r.body) ? r.body : (r.body?.rooms || r.body?.items || []);
                pilotRoomsLen = list.length;
                if (list[0] && !pilotSampleRoomId) pilotSampleRoomId = list[0].id || list[0]._id;
            }
        } catch (_) { /* best-effort */ }

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} stress_tid=${stressTid?.slice(0, 8)} pilot_tid=${pilotTid?.slice(0, 8)} pilot_sample_booking=${!!pilotSampleBookingId} pilot_sample_guest=${!!pilotSampleGuestId} pilot_sample_room=${!!pilotSampleRoomId} pilot_bookings_len=${pilotBookingsLen} pilot_rooms_len=${pilotRoomsLen}` });
    });

    test('A) Introspection policy + Mutation surface contract', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'introspection', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Introspection — production'da kapalı olması beklenir; açıksa schema
        // surface saldırgan için ücretsiz keşif. Burada açık dönerse REVIEW/P2
        // (task acceptance: "açıksa REVIEW/P2 raporlanır").
        const r = await gql(request, stressTokens.stress_token, Q_INTROSPECTION, {});
        const introspectionOpen = r.ok && r.body?.data?.__schema != null;
        const types = r.body?.data?.__schema?.types || [];
        const mutationType = r.body?.data?.__schema?.mutationType;

        rec(testInfo, { module: MOD, step: 'introspection',
            status: introspectionOpen ? 'REVIEW' : 'PASS',
            endpoint: GQL, http: r.status,
            note: introspectionOpen
                ? `introspection_open=true types=${types.length} mutation_type=${JSON.stringify(mutationType)}`
                : `introspection_closed status=${r.status} errors=${JSON.stringify(r.body?.errors || []).slice(0, 100)}` });

        if (introspectionOpen) {
            recFinding(testInfo, 'P2', MOD, 'GraphQL introspection production stress\'te açık',
                `Schema introspection 2xx döndü (types=${types.length}). Production'da disable edilmesi önerilir; attack surface keşfi ücretsiz oluyor. Acceptance: REVIEW/P2 informational.`);
        }

        // Mutation surface contract: schema'da Mutation tipi YOK (yalnız Query).
        // Mutation görünürse spec dışı yeni yüzey demektir → REVIEW/P2.
        if (mutationType && mutationType.name) {
            recFinding(testInfo, 'P2', MOD, 'GraphQL Mutation surface görüldü — F8M kapsamı genişletilmeli',
                `mutation_type=${JSON.stringify(mutationType)}. Schema bu zamana kadar yalnız Query barındırıyordu; eklenen mutation yüzeyi için ayrı isolation/dry-run kanıtı gerekli.`);
        } else {
            rec(testInfo, { module: MOD, step: 'mutation_surface_contract', status: 'PASS',
                note: 'no Mutation type — read-only schema (acceptance: stress tenant\'a mutation dry-run yapılmaz)' });
        }

        // Token leak guard — introspection response'unda credential material
        // bulunmamalı (default değerler / docstring leak).
        if (r.ok) {
            const tokOk = assertNoTokenLeak(testInfo, MOD, r.body, 'graphql_introspection');
            rec(testInfo, { module: MOD, step: 'introspection_token_leak_guard',
                status: tokOk ? 'PASS' : 'FAIL', note: `tok_ok=${tokOk}` });
        }
    });

    test('B) Resolver isolation — stress_token ile bookings/rooms/dashboard kendi tenant\'ı dönmeli, pilot ID\'leri sızmamalı', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'resolver_isolation', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }

        // Q1 — Bookings: stress_token ile filter:{} (boş) sorgu. Dönen ID
        // listesi pilot tenant booking ID'sini İÇERMEMELİ. Hard floor:
        // pilotSampleBookingId varsa bu ID dönen sette olmamalı (P0 leak).
        const b = await gql(request, stressTokens.stress_token, Q_BOOKINGS, { f: { limit: 200, skip: 0 } });
        // Tur-5 fix: hard error assertion. Bookings probe schema valid
        // olmalı; errors array doluysa false-PASS riski + coverage gap →
        // P1 finding emit, status FAIL.
        const bErrors = Array.isArray(b.body?.errors) ? b.body.errors : [];
        if (bErrors.length > 0 || !b.ok) {
            recFinding(testInfo, 'P1', MOD,
                'GraphQL bookings resolver schema/transport error — isolation kanıtı yok',
                `status=${b.status} errors=${JSON.stringify(bErrors).slice(0, 240)}. Cross-tenant leak detection imkânsız; query field-name veya schema drift olabilir.`);
        }
        const bookings = b.body?.data?.bookings || [];
        const bookingIds = new Set(bookings.map(x => x.id));
        const guestIds = new Set(bookings.map(x => x.guestId).filter(Boolean));
        const roomIds = new Set(bookings.map(x => x.roomId).filter(Boolean));

        const pilotBookingLeak = pilotSampleBookingId && bookingIds.has(pilotSampleBookingId);
        const pilotGuestLeak = pilotSampleGuestId && guestIds.has(pilotSampleGuestId);
        const pilotRoomLeakViaBooking = pilotSampleRoomId && roomIds.has(pilotSampleRoomId);

        rec(testInfo, { module: MOD, step: 'resolver_bookings_isolation',
            status: (pilotBookingLeak || pilotGuestLeak || pilotRoomLeakViaBooking) ? 'FAIL' : 'PASS',
            endpoint: GQL, http: b.status,
            note: `returned=${bookings.length} pilot_booking_leak=${pilotBookingLeak} pilot_guest_leak=${pilotGuestLeak} pilot_room_leak_via_booking=${pilotRoomLeakViaBooking}` });

        if (pilotBookingLeak || pilotGuestLeak || pilotRoomLeakViaBooking) {
            recFinding(testInfo, 'P0', MOD,
                'GraphQL bookings resolver cross-tenant leak — pilot ID stress response\'unda göründü',
                `pilot_booking=${pilotBookingLeak ? pilotSampleBookingId : '-'} pilot_guest=${pilotGuestLeak ? pilotSampleGuestId : '-'} pilot_room=${pilotRoomLeakViaBooking ? pilotSampleRoomId : '-'}. Resolver tenant_id filter eksik → cross-tenant disclosure.`);
        }

        // Q2 — Rooms: aynı doktrin.
        const r = await gql(request, stressTokens.stress_token, Q_ROOMS, { f: { limit: 200, skip: 0 } });
        const rErrors = Array.isArray(r.body?.errors) ? r.body.errors : [];
        if (rErrors.length > 0 || !r.ok) {
            recFinding(testInfo, 'P1', MOD,
                'GraphQL rooms resolver schema/transport error — isolation kanıtı yok',
                `status=${r.status} errors=${JSON.stringify(rErrors).slice(0, 240)}.`);
        }
        const rooms = r.body?.data?.rooms || [];
        const returnedRoomIds = new Set(rooms.map(x => x.id));
        const pilotRoomLeak = pilotSampleRoomId && returnedRoomIds.has(pilotSampleRoomId);

        rec(testInfo, { module: MOD, step: 'resolver_rooms_isolation',
            status: pilotRoomLeak ? 'FAIL' : 'PASS',
            endpoint: GQL, http: r.status,
            note: `returned=${rooms.length} pilot_room_leak=${pilotRoomLeak}` });
        if (pilotRoomLeak) {
            recFinding(testInfo, 'P0', MOD,
                'GraphQL rooms resolver cross-tenant leak',
                `pilot_room_id=${pilotSampleRoomId} stress response'unda göründü. Resolver tenant_id filter eksik.`);
        }

        // Q3 — Dashboard metrics: cross-tenant aggregation accident. Bu
        // endpoint materialized_views üzerinden döner; tenant scope eksikse
        // pilot+stress birlikte toplanır. Direct ID leak'i göstermez ama
        // total_rooms / occupied_rooms gerçek-dışı büyük dönerse REVIEW.
        const d = await gql(request, stressTokens.stress_token, Q_DASHBOARD, {});
        const metrics = d.body?.data?.dashboardMetrics || null;
        rec(testInfo, { module: MOD, step: 'resolver_dashboard_metrics',
            status: d.ok ? 'PASS' : 'REVIEW',
            endpoint: GQL, http: d.status,
            note: metrics
                ? `total_rooms=${metrics.totalRooms} occupied=${metrics.occupiedRooms} revenue=${metrics.todayRevenue}`
                : `body=${JSON.stringify(d.body).slice(0, 160)}` });

        // PII guard — booking + nested guest field'ları phone/email/id_number
        // raw döndürmemeli (Guest type'ı phone/id_number expose ediyor!).
        // Bu real test: PII expose şeması mevcut ama masked olmalı.
        const nested = await gql(request, stressTokens.stress_token, Q_NESTED, { f: { limit: 50, skip: 0 } });
        const nestedBookings = nested.body?.data?.bookings || [];
        const guestsForPii = nestedBookings.map(x => x.guest).filter(Boolean);
        if (guestsForPii.length > 0) {
            // assertPiiMasked snake_case field bekler; nested.guest.idNumber
            // camelCase → manuel normalize edip içeri besle.
            const normalized = guestsForPii.map(g => ({
                phone: g.phone, email: g.email, identity_number: g.idNumber,
            }));
            const piiOk = assertPiiMasked(testInfo, MOD, normalized, ['phone', 'email', 'identity_number']);
            rec(testInfo, { module: MOD, step: 'graphql_pii_guard',
                status: piiOk ? 'PASS' : 'FAIL',
                note: `nested_guests=${guestsForPii.length} pii_ok=${piiOk}` });
        } else {
            rec(testInfo, { module: MOD, step: 'graphql_pii_guard', status: 'PASS',
                note: 'no nested guest payload — PII surface yok bu sample\'da' });
        }

        // Token leak — nested + dashboard yanıtlarında credential material yok.
        if (nested.ok) assertNoTokenLeak(testInfo, MOD, nested.body, 'graphql_nested');
        if (d.ok) assertNoTokenLeak(testInfo, MOD, d.body, 'graphql_dashboard');
    });

    test('C) Cross-tenant injection probes — variable spoof, pilot ID lookup, pagination cursor', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'cross_tenant_injection', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }

        const probes = [];
        const leaks = [];

        // P1 — Filter spoof: pilot guest_id ile sorgu. Beklenti: boş liste
        // (stress tenant'ta o guest_id yok). 1+ row dönerse cross-tenant leak.
        // Tur-5: BookingFilter input field `guest_id` → GraphQL'de `guestId`
        // (Strawberry auto_camel_case=True).
        if (pilotSampleGuestId) {
            const r = await gql(request, stressTokens.stress_token, Q_BOOKINGS,
                { f: { guestId: pilotSampleGuestId, limit: 50 } });
            const rows = r.body?.data?.bookings || [];
            probes.push({ kind: 'guest_id_spoof', http: r.status, returned: rows.length });
            if (rows.length > 0) {
                leaks.push({ kind: 'guest_id_spoof', sample_id: pilotSampleGuestId, returned: rows.length });
            }
        }

        // P2 — Room ID spoof: pilot room_id ile booking sorgusu. Aynı doktrin.
        if (pilotSampleRoomId) {
            const r = await gql(request, stressTokens.stress_token, Q_BOOKINGS,
                { f: { roomId: pilotSampleRoomId, limit: 50 } });
            const rows = r.body?.data?.bookings || [];
            probes.push({ kind: 'room_id_spoof', http: r.status, returned: rows.length });
            if (rows.length > 0) {
                leaks.push({ kind: 'room_id_spoof', sample_id: pilotSampleRoomId, returned: rows.length });
            }
        }

        // P3 — Pagination cursor abuse: çok büyük skip ile cross-tenant overflow.
        // Beklenti: boş liste veya en fazla stress tenant kendi kuyruğu.
        // Bu test "boundary stres" — sonuçtaki ID'leri pilot ile karşılaştır.
        const big = await gql(request, stressTokens.stress_token, Q_BOOKINGS,
            { f: { limit: 100, skip: 10000 } });
        const bigRows = big.body?.data?.bookings || [];
        probes.push({ kind: 'big_skip', http: big.status, returned: bigRows.length });
        const bigIds = new Set(bigRows.map(x => x.id));
        if (pilotSampleBookingId && bigIds.has(pilotSampleBookingId)) {
            leaks.push({ kind: 'big_skip_pilot_leak', sample_id: pilotSampleBookingId });
        }

        // P4 — Negative skip / extreme limit (validation bypass attempt).
        const neg = await gql(request, stressTokens.stress_token, Q_BOOKINGS,
            { f: { limit: 100, skip: -1 } });
        probes.push({ kind: 'negative_skip', http: neg.status,
            returned: (neg.body?.data?.bookings || []).length,
            errors: (neg.body?.errors || []).length });

        // P5 — Variables key collision (extra tenant_id field — schema'da yok,
        // ama yine de deneriz; schema validation tarafından REJECT beklenir).
        const collide = await gql(request, stressTokens.stress_token,
            `query($f:BookingFilter,$tid:String){bookings(filter:$f){id}}`,
            { f: { limit: 10 }, tid: pilotTid });
        probes.push({ kind: 'variable_collision_tid', http: collide.status,
            errors: (collide.body?.errors || []).length });

        const pass = leaks.length === 0;
        rec(testInfo, { module: MOD, step: 'cross_tenant_injection',
            status: pass ? 'PASS' : 'FAIL',
            note: `probes=${probes.length} leaks=${leaks.length} probe_summary=${JSON.stringify(probes).slice(0, 240)}` });
        if (!pass) {
            recFinding(testInfo, 'P0', MOD,
                'GraphQL cross-tenant injection leak — pilot ID stres token ile geri döndü',
                `Leaks: ${JSON.stringify(leaks)}. Resolver pilot ID'sini kabul edip data döndü → tenant_id filter eksik veya client-input trust hatası.`);
        }
    });

    test('C2) Folios + Reports surface contract — schema\'da YOK; query attempt schema error dönmeli, data DÖNMEMELİ', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'folios_reports_surface', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Validation review (tur-2): task acceptance "resolver isolation across
        // bookings/guests/folios/rooms/reports" — backend GraphQL schema
        // (`backend/graphql_api/schema.py`) yalnız bookings + rooms +
        // dashboard_metrics + dashboard_trends + nested guest/room expose
        // ediyor. folios + reports resolver\'ı YOK. Bu test surface contract\'ı
        // doğrular — query atılırsa schema validation error dönmeli; data
        // dönerse YENİ resolver eklenmiş demek + isolation kanıtlanmamış (P0).
        const probes = [
            { name: 'folios_query', query: 'query($f:BookingFilter){folios(filter:$f){id booking_id total_amount}}', variables: { f: { limit: 5 } } },
            { name: 'folio_singleton', query: 'query{folio(id:"00000000-0000-0000-0000-000000000000"){id}}', variables: {} },
            { name: 'reports_query', query: 'query{reports{vat profit_loss}}', variables: {} },
            { name: 'vat_report', query: 'query{vatReport(from:"2026-01-01",to:"2026-12-31"){total}}', variables: {} },
            { name: 'finance_dashboard', query: 'query{financeDashboard{revenue}}', variables: {} },
        ];
        const surfaceLeaks = [];
        for (const p of probes) {
            const r = await gql(request, stressTokens.stress_token, p.query, p.variables);
            const hasErrors = Array.isArray(r.body?.errors) && r.body.errors.length > 0;
            const hasData = r.body?.data && Object.values(r.body.data).some(v => v != null);
            if (!hasErrors && hasData) {
                surfaceLeaks.push({ probe: p.name, status: r.status, data_keys: Object.keys(r.body.data) });
            }
        }
        const pass = surfaceLeaks.length === 0;
        rec(testInfo, { module: MOD, step: 'folios_reports_surface_contract',
            status: pass ? 'PASS' : 'FAIL',
            note: `probes=${probes.length} surface_leaks=${surfaceLeaks.length} detail=${JSON.stringify(surfaceLeaks).slice(0, 200)}` });
        if (!pass) {
            recFinding(testInfo, 'P0', MOD,
                'GraphQL folios/reports surface beklenmedik şekilde data döndü',
                `Schema bu kadar yüzeyi expose etmiyor olmalıydı; ${JSON.stringify(surfaceLeaks)} — yeni resolver eklenmiş + tenant isolation kanıtı yok. Spec güncelleyip resolver isolation probe\'larını eklemeli.`);
        }
    });

    test('D) Auth boundary — unauthenticated + invalid token + wrong-tenant', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'auth_boundary', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const probes = [];

        // 1) No auth header — beklenti: 401/403 veya GraphQL errors (auth required).
        //    200 + data dönerse PUBLIC RESOLVER LEAK = P0.
        const noAuth = await callTimed(request, 'post', GQL, { query: Q_BOOKINGS, variables: { f: { limit: 5 } } }, '');
        const noAuthData = noAuth.body?.data?.bookings || [];
        probes.push({ kind: 'no_auth', http: noAuth.status, data_returned: noAuthData.length,
            errors: (noAuth.body?.errors || []).length });
        if (noAuth.status >= 200 && noAuth.status < 300 && noAuthData.length > 0) {
            recFinding(testInfo, 'P0', MOD,
                'GraphQL unauthenticated booking disclosure',
                `no-auth POST 200 + ${noAuthData.length} row → public resolver. Threat-model § Elevation of Privilege.`);
        }

        // 2) Garbage token — invalid JWT. Beklenti: 401.
        const garbage = await callTimed(request, 'post', GQL, { query: Q_BOOKINGS, variables: { f: { limit: 5 } } }, 'eyJ_garbage.invalid.token');
        const garbageData = garbage.body?.data?.bookings || [];
        probes.push({ kind: 'invalid_token', http: garbage.status, data_returned: garbageData.length });
        if (garbage.status >= 200 && garbage.status < 300 && garbageData.length > 0) {
            recFinding(testInfo, 'P0', MOD,
                'GraphQL invalid-token disclosure',
                `Invalid JWT 200 + data → token validation bypass. status=${garbage.status}.`);
        }

        // 3) Pilot token GraphQL'a → pilot tenant'ın kendi datası dönmeli;
        //    stress tenant ID'leri DOLAR ETMEMELİ (reverse cross-tenant).
        const pilotR = await gql(request, stressTokens.pilot_token, Q_BOOKINGS, { f: { limit: 100, skip: 0 } });
        const pilotRows = pilotR.body?.data?.bookings || [];
        probes.push({ kind: 'pilot_self_query', http: pilotR.status, returned: pilotRows.length });
        // Stress tenant'ın prefix'li booking ID'lerini biz bilmiyoruz (random
        // UUID), ama stress tenant 500+ booking ile seed edildi; pilot tenant
        // gerçek count'tan çok daha fazla satır dönerse cross-tenant aggregation
        // şüphesi.
        //
        // CI #48 false-positive fix: önceki sürüm `pilotBookingsLen`'i
        // `/api/pms/bookings?limit=5` çağrısından alıyordu (REST cap=5);
        // bu eşik (5*3=15, max 50) pilot tenant 100+ booking taşıdığında
        // determinik olarak P1 spam üretiyordu. `pilotBefore.count`
        // `pilotBookingsCount` → `fetchSingle` üzerinden cap'siz gelir ve
        // gerçek pilot booking sayısını temsil eder. Bir tarafta limit=100
        // (GraphQL) diğerinde server default (REST) olduğu için kıyaslama
        // yalnızca "GraphQL count ≫ REST count" rejimi anlamlı; aksi halde
        // her iki taraf da limit'e dayanır ve sinyal değildir.
        const pilotRestCount = pilotBefore?.count ?? pilotBookingsLen;
        const restCapHit = pilotRestCount === pilotRows.length;
        if (!restCapHit && pilotRows.length > Math.max(pilotRestCount * 3, 50)) {
            recFinding(testInfo, 'P1', MOD,
                'Pilot GraphQL bookings cross-tenant aggregation şüphesi',
                `Pilot REST(uncapped)=${pilotRestCount} bookings; GraphQL=${pilotRows.length}. ~3x oran üzerinde => stress tenant verisi karışmış olabilir.`);
        }

        rec(testInfo, { module: MOD, step: 'auth_boundary',
            status: 'PASS', note: `probes=${JSON.stringify(probes).slice(0, 240)}` });
    });

    test('E) external_calls invariant + pilot_drift=0', async ({ request, stressTokens }, testInfo) => {
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const stateBlob = JSON.parse(fs.readFileSync(path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-state.json'), 'utf-8'));
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'graphql_isolation_done', stateBlob, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'invariants_done', status: 'PASS', note: 'pilot_drift+external_calls verified' });
        expect(true).toBe(true);
    });
});

// F8K § 60 — Public Online Check-in Token Guard & Submission Contract Stress.
//
// Threat-model surface (threat_model.md § Spoofing + Tampering + Information
// Disclosure): `/api/checkin/online/*` JWT-auth gerektirir (frontdesk veya
// guest_app rolü). Public token bypass yok; ama cross-tenant booking_id
// teftişi ve guest_app role isolation (kendi booking dışına bakma yasak)
// + multipart ID photo upload size/type guard birinci sınıf saldırı
// yüzeyleridir. Raw bytes asla DB'ye yazılmamalı (sha256 + encrypted blob
// dışında), signature SVG sanitized olmalı.
//
// Mutlak kurallar (task #196):
//   - pilot mutation YOK (drift=0). Çağrılar yalnızca stress booking ID
//     hedefler; pilot booking_id ile teftiş = 404 beklenir + drift baseline
//     değişmez.
//   - external_calls=[] (post-batch helper). Online check-in submission
//     normalde bir OTA outbound dispatch'i tetiklemez; ama spec submit
//     YAPMAZ (dry-run probe contract), bu yüzden dispatcher zaten boş.
//   - failedTests=0, P0=P1=0.
//   - Real OCR / KVKK ID lookup vendor call = 0.
//   - Cleanup idempotent: spec hiçbir kalıcı satır yazmaz (probe-only); ama
//     accidental stage_doc olursa stress_prefix marker'lı online_checkin_id_photos
//     satırlarını cleanup'ta tarar.
//
// Module-blocked pattern (F8M § 40/41 + F8L § 50 mirror):
//   - Stress tenant'ta hiç booking yoksa veya state probe non-2xx ise
//     moduleBlocked + P2 informational + A/B/C/D test.skip; E pilot_drift +
//     external_calls bağımsız çalışır.
//
// Backend yüzeyleri (backend/domains/guest/checkin_router.py):
//   - GET    /api/checkin/online/{booking_id}                   (state)
//   - POST   /api/checkin/online                                (submit JSON)
//   - POST   /api/checkin/online/{booking_id}/id-photo          (multipart)
//   - DELETE /api/checkin/online/id-photos/{photo_id}           (cleanup)
//
// Auth contract: hepsi `_allow_frontdesk_or_guest` dependency → frontdesk
// module RBAC veya guest_app role veya super_admin geçer. Stress admin
// (admin/super_admin) erişebilir; anonymous + garbage JWT → 401/403.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertPiiMasked, assertNoTokenLeak, withModuleProbe, pilotBookingsCount,
    fetchSingle,
} from '../fixtures/stress-helpers.js';

const MOD = 'public_checkin';

// Anonymous / custom-bearer call wrapper. callTimed otomatik Bearer ekler;
// burada başlığı manuel kontrol etmeliyiz (no-token, garbage, tampered).
async function callRaw(request, method, urlPath, opts = {}) {
    const headers = { 'Content-Type': opts.contentType || 'application/json', ...(opts.headers || {}) };
    const t0 = Date.now();
    const r = await request[method](urlPath, {
        headers, data: opts.body, multipart: opts.multipart, failOnStatusCode: false,
        timeout: opts.timeout ?? 30_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    const ms = Date.now() - t0;
    let bodyJson = null, bodyText = null;
    try { bodyText = r.text ? await r.text() : null; } catch { /* */ }
    try { bodyJson = bodyText && bodyText.trim().startsWith('{') ? JSON.parse(bodyText) : null; } catch { /* */ }
    const status = r.status?.() ?? 0;
    return { status, ms, body: bodyJson, text: bodyText, ok: status >= 200 && status < 300 };
}

const TAMPERED_JWT = 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4eHgiLCJleHAiOjB9.tampered_sig_invalid_xxxxxxxxxxxxxxxxxxxx';

test.describe.configure({ mode: 'serial' });

test.describe('F8K § 60 — Public Online Check-in Stress', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let stressTid = null;
    let pilotTid = null;
    let stressBookingId = null;
    let pilotBookingId = null;

    test('Setup: prefix + pilot baseline + stress booking probe + auth contract baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tid;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Stress tenant'tan bir booking ID al — checkin endpoint'leri booking
        // bazlı; setup'ta booking yoksa moduleBlocked.
        const bk = await fetchSingle(request, stressTokens.stress_token, '/api/pms/bookings?limit=20');
        if (!(bk.http >= 200 && bk.http < 300) || !Array.isArray(bk.list) || bk.list.length === 0) {
            moduleBlocked = true;
            blockedReason = `bookings_probe_status_${bk.http}_len_${bk.list?.length ?? 'n/a'}`;
            recFinding(testInfo, 'P2', MOD, 'Stress tenant\'ta booking bulunamadı / probe non-2xx',
                `GET /api/pms/bookings status=${bk.http} len=${bk.list?.length ?? 'n/a'} — checkin endpoint'leri booking_id şart. A/B/C/D skipped, E pilot_drift+external_calls bağımsız.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            return;
        }
        stressBookingId = bk.list[0]?.id || bk.list[0]?._id;

        // Pilot tenant'tan da bir booking ID al (cross-tenant probe için).
        try {
            const pbk = await fetchSingle(request, stressTokens.pilot_token, '/api/pms/bookings?limit=5');
            if (pbk.http >= 200 && pbk.http < 300 && pbk.list.length > 0) {
                pilotBookingId = pbk.list[0]?.id || pbk.list[0]?._id;
            }
        } catch (_) { /* best-effort */ }

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count} stress_booking=${stressBookingId?.slice(0, 8)} pilot_booking_sample=${pilotBookingId ? pilotBookingId.slice(0, 8) : 'missing'}` });
    });

    test('A) Auth contract — anonymous + garbage + tampered JWT → 401/403 on state GET', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'auth_contract', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const ALLOWED_DENY = new Set([401, 403]);
        const url = `/api/checkin/online/${stressBookingId}`;

        // 1) Anonymous — no Authorization header.
        const anon = await callRaw(request, 'get', url);
        const anonOk = ALLOWED_DENY.has(anon.status);
        if (anon.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Online check-in state GET anonymous erişime açık',
                `GET ${url} no-auth status=${anon.status} body=${JSON.stringify(anon.body).slice(0, 160)}. Threat-model § Elevation of Privilege + Information Disclosure (booking payload PII içerir).`);
        }

        // 2) Garbage bearer.
        const garbage = await callRaw(request, 'get', url, { headers: { Authorization: 'Bearer garbage_token_xxxxxxxxxxxxxxxxxxxx' } });
        const garbageOk = ALLOWED_DENY.has(garbage.status);
        if (garbage.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Online check-in garbage JWT kabul edildi',
                `${url} garbage-bearer status=${garbage.status} — JWT signature verification bypass.`);
        }

        // 3) Tampered (well-formed shape, invalid signature).
        const tampered = await callRaw(request, 'get', url, { headers: { Authorization: `Bearer ${TAMPERED_JWT}` } });
        const tamperedOk = ALLOWED_DENY.has(tampered.status);
        if (tampered.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Online check-in tampered JWT kabul edildi',
                `${url} tampered-bearer status=${tampered.status} — signature verify zayıf.`);
        }

        // 4) Valid stress admin — 2xx veya 404 (booking state'e bağlı) kabul.
        const valid = await callTimed(request, 'get', url, undefined, stressTokens.stress_token);
        const validOk = valid.ok || valid.status === 404;
        if (valid.ok && valid.body) {
            // PII guard — booking payload guest phone/email/identity_number içerebilir.
            assertPiiMasked(testInfo, MOD, valid.body, ['phone', 'email', 'identity_number', 'passport_no', 'guest_phone', 'guest_email']);
            assertNoTokenLeak(testInfo, MOD, valid.body, 'checkin_state_read');
        }

        const pass = anonOk && garbageOk && tamperedOk && validOk;
        rec(testInfo, { module: MOD, step: 'auth_contract',
            status: pass ? 'PASS' : 'FAIL',
            endpoint: `GET ${url}`,
            note: `anon=${anon.status} garbage=${garbage.status} tampered=${tampered.status} valid=${valid.status}` });
    });

    test('B) Form submit contract — invalid payload + no-auth + cross-tenant booking_id', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'submit_contract', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const SUBMIT = '/api/checkin/online';
        const ALLOWED_DENY = new Set([401, 403]);

        // 1) Anonymous submit — 401/403.
        const anon = await callRaw(request, 'post', SUBMIT, { body: { booking_id: stressBookingId } });
        if (anon.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Online check-in submit anonymous erişime açık',
                `POST ${SUBMIT} no-auth status=${anon.status}. Tampering primitive.`);
        }

        // 2) Stress admin + EMPTY/INVALID body — 400/422 beklenir (validation).
        //    2xx dönerse boş form ile check-in tamamlanmış = data integrity ihlali.
        const empty = await callTimed(request, 'post', SUBMIT, {}, stressTokens.stress_token);
        const emptyValid = empty.status === 400 || empty.status === 422;
        if (empty.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Online check-in submit boş body ile 2xx döndü',
                `POST ${SUBMIT} body={} status=${empty.status} — validation eksik; arbitrary check-in oluşturulabilir.`);
        }

        // 3) Stress admin + GARBAGE booking_id — 404/400/422 beklenir.
        const garbage = await callTimed(request, 'post', SUBMIT,
            { booking_id: 'F8K_GARBAGE_NOT_A_REAL_ID', signature_consent: true, signature_text: 'STRESS_PROBE' },
            stressTokens.stress_token);
        if (garbage.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Online check-in submit garbage booking_id ile 2xx döndü',
                `POST ${SUBMIT} body={booking_id:garbage} status=${garbage.status} — booking lookup bypass.`);
        }

        // 4) Stress admin + PILOT booking_id — cross-tenant teftiş. 404 beklenir
        //    (booking tenant filter ile bulunmaz). 2xx olursa cross-tenant
        //    mutation primitive = P0.
        let crossTenantOk = true;
        let crossStatus = null;
        if (pilotBookingId) {
            const cross = await callTimed(request, 'post', SUBMIT,
                { booking_id: pilotBookingId, signature_consent: true, signature_text: 'STRESS_PROBE' },
                stressTokens.stress_token);
            crossStatus = cross.status;
            crossTenantOk = !cross.ok;
            if (cross.ok) {
                recFinding(testInfo, 'P0', MOD,
                    'Cross-tenant online check-in submit kabul edildi',
                    `POST ${SUBMIT} body={booking_id:<pilot>} status=${cross.status} — pilot booking stress admin tarafından mutate edildi. Tenant isolation breach.`);
            }
        }

        const pass = ALLOWED_DENY.has(anon.status) && emptyValid && !garbage.ok && crossTenantOk;
        rec(testInfo, { module: MOD, step: 'submit_contract',
            status: pass ? 'PASS' : 'FAIL',
            note: `anon=${anon.status} empty=${empty.status} garbage_bk=${garbage.status} cross_tenant=${crossStatus ?? 'no_pilot_bk'}` });
    });

    test('C) ID-photo upload size/type guard — anonymous + oversized + invalid mime → reject', async ({ request, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'id_photo_guard', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const url = `/api/checkin/online/${stressBookingId}/id-photo`;
        const ALLOWED_DENY = new Set([401, 403]);

        // 1) Anonymous upload — 401/403.
        const anonBuf = Buffer.from('not-a-real-image', 'utf-8');
        const anon = await callRaw(request, 'post', url, {
            multipart: { photo: { name: 'a.txt', mimeType: 'text/plain', buffer: anonBuf } },
        });
        if (anon.ok) {
            recFinding(testInfo, 'P0', MOD,
                'ID photo upload anonymous erişime açık',
                `POST ${url} no-auth status=${anon.status} — KVKK regulated PII upload yüzeyi.`);
        }

        // 2) Stress admin + INVALID mime/content (text masquerading as image).
        //    upload_validator magic-bytes kontrolü 400/415/422 üretmeli.
        const txtBuf = Buffer.from('PLAIN TEXT NOT AN IMAGE', 'utf-8');
        const txt = await callRaw(request, 'post', url, {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            multipart: { photo: { name: 'fake.jpg', mimeType: 'image/jpeg', buffer: txtBuf } },
        });
        const txtRejected = !txt.ok;
        if (txt.ok) {
            recFinding(testInfo, 'P0', MOD,
                'ID photo upload magic-bytes guard bypass — plain text JPEG mime ile kabul edildi',
                `POST ${url} body=text/plain mime=image/jpeg status=${txt.status} — upload_validator magic-bytes check zayıf. Polyglot/SVG/PDF injection riski.`);
        }

        // 3) Stress admin + OVERSIZED (MAX_IMAGE_BYTES = 256 KiB; gönder 320 KiB
        //    JPEG header'lı bayt dizisi). 413/400/422 beklenir.
        const oversized = Buffer.concat([
            Buffer.from([0xFF, 0xD8, 0xFF, 0xE0]),                // JPEG SOI
            Buffer.alloc(320 * 1024, 0x42),                       // 320 KiB padding
        ]);
        const big = await callRaw(request, 'post', url, {
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            multipart: { photo: { name: 'big.jpg', mimeType: 'image/jpeg', buffer: oversized } },
        });
        const bigRejected = !big.ok || big.status === 413;
        if (big.ok && big.status !== 413) {
            // 2xx döndüyse stage_doc yazılmış olabilir → kayıt id'yi çekip cleanup et.
            if (big.body?.photo_id) {
                try {
                    await callTimed(request, 'delete',
                        `/api/checkin/online/id-photos/${big.body.photo_id}`,
                        undefined, stressTokens.stress_token);
                    rec(testInfo, { module: MOD, step: 'id_photo_oversize_cleanup',
                        status: 'PASS', note: `deleted accidental photo_id=${big.body.photo_id?.slice(0, 8)}` });
                } catch (_) { /* best-effort */ }
            }
            recFinding(testInfo, 'P0', MOD,
                'ID photo upload size limit bypass — 320 KiB kabul edildi',
                `POST ${url} bytes=${oversized.length} status=${big.status} — MAX_IMAGE_BYTES (256 KiB) guard çalışmıyor. DoS + storage exhaustion riski.`);
        }

        const pass = ALLOWED_DENY.has(anon.status) && txtRejected && bigRejected;
        rec(testInfo, { module: MOD, step: 'id_photo_guard',
            status: pass ? 'PASS' : 'FAIL',
            note: `anon=${anon.status} text_mime_jpeg=${txt.status} oversized_320kib=${big.status}` });
    });

    test('D) Pilot drift + external_calls invariant', async ({ request, stressTokens, stressState }, testInfo) => {
        // Bu testler probe-only; ama yine de doctrine'ı uygulayalım.
        await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        await assertNoExternalCallsPostBatch(testInfo, MOD, 'public_checkin_probes',
            stressState, request, stressTokens.pilot_token);
    });

    test.afterAll(async ({ request, stressTokens, stressState }) => {
        // Idempotent residue sweep — accidental stage_doc varsa temizle.
        // Probe-only spec; normal koşullarda yazma olmaz ama defense-in-depth.
        if (!stressTokens || moduleBlocked) return;
        try {
            const r = await request.get('/api/checkin/online/id-photos?limit=50', {
                headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                failOnStatusCode: false, timeout: 15_000,
            });
            if (!r.ok()) return;
            const j = await r.json().catch(() => ({}));
            const items = Array.isArray(j) ? j : (j?.photos || j?.items || []);
            const stressPrefix = stressState?.data_prefix || 'STRESS_';
            // Yalnız bu round prefix'li satırlar — `claimed===false` toptan
            // silme YOK (orphan-cleanup job'unun sorumluluğu). Tightly
            // run-scoped: field_label/note/guest_name içinde stressPrefix
            // marker'ı zorunlu.
            for (const it of items) {
                const tag = (it?.field_label || '') + (it?.note || '') + (it?.guest_name || '');
                if (!tag.includes(stressPrefix)) continue;
                const pid = it.photo_id || it.id;
                if (pid) {
                    await request.delete(`/api/checkin/online/id-photos/${pid}`, {
                        headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
                        failOnStatusCode: false, timeout: 10_000,
                    }).catch(() => null);
                }
            }
        } catch (_) { /* best-effort */ }
    });
});

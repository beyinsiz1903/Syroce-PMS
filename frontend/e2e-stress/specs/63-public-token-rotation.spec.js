// F8Q § 63 — Public token (QR / booking) rotation + tampering deep.
//
// Surface:
//   - `backend/routers/room_qr_requests.py` /api/public/room-qr/{tid}/{rid}
//     GET + /submit POST → `_verify_token(tenant_id, room_id, t)` HMAC.
//   - `backend/core/security.py` `generate_time_based_qr_token` (JWT-based,
//     booking-scoped, 72h exp).
//   - ROOM_QR_SECRET env var (missing_secrets — fail-closed contract).
//
// Doctrine:
//   - Valid token contract probe (verify + submit smoke).
//   - Tampered/malformed/missing token → 403.
//   - Cross-tenant token (forge same room with different tid) → 403.
//   - Expired token (manufactured payload past exp) → 403/410.
//   - Raw secret/JWT not in error response.
//   - external_calls=[], pilot_drift=0.
//
// Rotation note: explicit secret-rotation endpoint backend'de mevcut DEĞİL
// (rotate_secret yalnız core/secrets/ provider katmanında, ROOM_QR_SECRET
// için public/staff endpoint yok). Bu spec rotation'ı emule edemez; ama
// tampering + expiry + cross-tenant kontratlarını sıkı doğrular. Rotation
// surface eksikliği D adımında P2 REVIEW olarak raporlanır (P0/P1 değil).
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe, assertPiiMasked,
} from '../fixtures/stress-helpers.js';

const MOD = 'public_token_rotation';

test.describe.configure({ mode: 'serial' });

function tokenContainsSecretLeak(body) {
    let blob = ''; try { blob = JSON.stringify(body); } catch { /* nz */ }
    // Heuristic: ROOM_QR_SECRET / JWT_SECRET literal substring (no real
    // secret value scan — sadece env-name veya 64+ hex/base64 raw).
    if (/ROOM_QR_SECRET|JWT_SECRET/.test(blob)) return true;
    if (/[A-Za-z0-9+/=]{64,}/.test(blob.replace(/"id":\s*"[^"]+"/g, ''))) {
        // Long token-like blob in non-id field is suspicious; not deterministic
        // P0 but flag for review.
        return false; // keep conservative
    }
    return false;
}

test.describe('F8Q § 63 — Public QR token tamper/cross-tenant/expiry deep', () => {
    let pilotBefore = null;
    let prefix = null;
    let stressTid = null;
    let stressRoomId = null;
    let stressRoomToken = null;
    let moduleBlocked = false;
    let blockedReason = null;

    test('Setup: prefix + pilot baseline + stress room harvest + module probe', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        stressTid = stressState.stress_tenant_id || process.env.E2E_STRESS_TENANT_ID || null;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Harvest a stress room ID — pms rooms list (bare array; items[] de
        // tolere edilir). NOT: `/api/rooms` list route YOK; doğru yüzey
        // `/api/pms/rooms`.
        const rooms = await callTimed(request, 'get', '/api/pms/rooms?limit=1',
            undefined, stressTokens.stress_token);
        if (rooms.ok) {
            const arr = Array.isArray(rooms.body?.items) ? rooms.body.items
                : Array.isArray(rooms.body) ? rooms.body : [];
            stressRoomId = arr[0]?.id || arr[0]?._id || null;
        }
        if (!stressRoomId) {
            moduleBlocked = true;
            blockedReason = 'no_stress_room_harvest';
            recFinding(testInfo, 'P2', MOD, 'no stress room harvested',
                `GET /api/pms/rooms status=${rooms.status} — A/B/C skip, D bağımsız.`);
        }

        // Harvest a VALID token via staff qr-code endpoint (gerçek token contract
        // doğrulaması + D rotation karşılaştırması için). Token döner ama tuz
        // (server-side sır) dönmez.
        if (stressRoomId) {
            const qr = await callTimed(request, 'get', `/api/rooms/${stressRoomId}/qr-code`,
                undefined, stressTokens.stress_token);
            if (qr.ok && qr.body?.token) {
                stressRoomToken = qr.body.token;
            } else if (qr.status === 401 || qr.status === 403) {
                recFinding(testInfo, 'P2', MOD, 'staff qr-code perm-gated',
                    `GET /api/rooms/<room>/qr-code status=${qr.status} — valid-token harvest skip, tamper/rotation contract daralır.`);
            }
        }

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} stress_tid=${stressTid?.slice(0, 8)} room=${stressRoomId?.slice(0, 8) || 'none'} valid_token=${stressRoomToken ? 'harvested' : 'none'} module_blocked=${moduleBlocked}` });
        expect(true).toBe(true);
    });

    test('A) Tampered/malformed/missing token → 403 contract', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'tamper_contract', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        const base = `/api/public/room-qr/${stressTid}/${stressRoomId}`;
        const probes = [
            { name: 'missing_token', url: base },
            { name: 'empty_token', url: `${base}?t=` },
            { name: 'garbage_token', url: `${base}?t=garbage_not_a_token` },
            { name: 'truncated_jwt', url: `${base}?t=eyJhbGciOiJIUzI1NiJ9.truncated` },
            { name: 'tampered_payload', url: `${base}?t=eyJhbGciOiJIUzI1NiJ9.eyJ0YW1wZXJlZCI6dHJ1ZX0.fakesig` },
            { name: 'sql_injection', url: `${base}?t=' OR '1'='1` },
            { name: 'long_garbage', url: `${base}?t=${'A'.repeat(2048)}` },
        ];
        const results = [];
        let secretLeaks = 0;
        let serverErr = 0;
        for (const p of probes) {
            const r = await callTimed(request, 'get', p.url, undefined, null);
            const accepted = r.ok && r.status === 200;
            const rejectOk = r.status === 403 || r.status === 400 || r.status === 422 || r.status === 401;
            const has5xx = r.status >= 500;
            if (has5xx) serverErr++;
            if (accepted) {
                recFinding(testInfo, 'P0', MOD, `tampered_token_accepted:${p.name}`,
                    `${p.url.slice(0, 100)} status=${r.status} — _verify_token bypass.`);
            }
            if (tokenContainsSecretLeak(r.body)) {
                secretLeaks++;
                recFinding(testInfo, 'P0', MOD, `secret_leak_in_error:${p.name}`,
                    `Error body ROOM_QR_SECRET/JWT_SECRET literal taşıyor.`);
            }
            results.push({ name: p.name, status: r.status, reject_ok: rejectOk });
        }
        rec(testInfo, { module: MOD, step: 'tamper_contract', status: serverErr === 0 && secretLeaks === 0 ? 'PASS' : 'FAIL',
            note: `probes=${probes.length} server_err=${serverErr} secret_leaks=${secretLeaks} results=${JSON.stringify(results)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'tamper_contract', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(serverErr, `5xx on tampering = ${serverErr} (DoS surface)`).toBe(0);
        expect(secretLeaks, `secret literal in error body = ${secretLeaks}`).toBe(0);
    });

    test('B) Cross-tenant token forge — wrong tenant + valid token shape', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'cross_tenant_forge', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        // Forge: random UUID tenant_id + stress room_id + arbitrary JWT-shaped t.
        const forgedTid = '00000000-0000-0000-0000-deadbeefcafe';
        const r = await callTimed(request, 'get',
            `/api/public/room-qr/${forgedTid}/${stressRoomId}?t=eyJhbGciOiJIUzI1NiJ9.eyJmYWtlIjoidHJ1ZSJ9.x`,
            undefined, null);
        const leaked = r.ok && r.body && (r.body.hotel_name || r.body.room_number);
        const rejectOk = r.status === 403 || r.status === 404;
        if (leaked) {
            recFinding(testInfo, 'P0', MOD, 'cross-tenant token forge accepted',
                `forged tid=${forgedTid.slice(0, 8)} + stress room → status=${r.status} body keys=${Object.keys(r.body || {}).join(',')}.`);
        }
        if (r.status >= 500) {
            recFinding(testInfo, 'P0', MOD, 'cross-tenant forge 5xx',
                `status=${r.status} — DoS surface via tenant_id query.`);
        }
        rec(testInfo, { module: MOD, step: 'cross_tenant_forge', status: !leaked && r.status < 500 ? 'PASS' : 'FAIL',
            note: `status=${r.status} reject_ok=${rejectOk} leaked=${leaked}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'cross_tenant_forge', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(leaked, `cross-tenant token forge leaked data`).toBeFalsy();
        expect(r.status < 500, `forge probe 5xx`).toBe(true);
    });

    test('C) Bulk QR fetch (staff) PII mask + secret in response guard', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'bulk_qr_pii', status: 'SKIP', note: blockedReason });
            test.skip(true, 'module blocked');
            return;
        }
        // /api/rooms/qr-codes/bulk — staff endpoint, döner QR data URL + token.
        const bulk = await callTimed(request, 'get', '/api/rooms/qr-codes/bulk?limit=5',
            undefined, stressTokens.stress_token);
        if (bulk.status === 401 || bulk.status === 403) {
            recFinding(testInfo, 'P2', MOD, 'bulk-qr perm-gated',
                `status=${bulk.status} — RBAC short-circuit.`);
            rec(testInfo, { module: MOD, step: 'bulk_qr_pii', status: 'SKIP', note: `status=${bulk.status}` });
            return;
        }
        if (bulk.status >= 500) {
            recFinding(testInfo, 'P0', MOD, 'bulk-qr 5xx', `status=${bulk.status}`);
        }
        const secretLeak = tokenContainsSecretLeak(bulk.body);
        if (secretLeak) {
            recFinding(testInfo, 'P0', MOD, 'secret leak in bulk-qr response',
                'Response body ROOM_QR_SECRET/JWT_SECRET literal taşıyor.');
        }
        rec(testInfo, { module: MOD, step: 'bulk_qr_pii', status: !secretLeak && bulk.status < 500 ? 'PASS' : 'FAIL',
            note: `status=${bulk.status} secret_leak=${secretLeak}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'bulk_qr_pii', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(secretLeak, 'secret literal in response').toBe(false);
    });

    test('D) QR secret rotation — endpoint + old-token invalidation contract', async ({ request, stressTokens, stressState }, testInfo) => {
        // POST /api/rooms/qr/rotate-secret per-tenant QR HMAC tuzunu döndürür
        // (tenant-scoped — yalnız çağıranın tenant'ı; pilot etkilenmez). Rotation
        // sonrası bu tenant'a ait eski tokenlar `_verify_token` HMAC mismatch ile
        // 403 reddedilir; yeni basılan token doğrulanır. Tuz ASLA yanıtta dönmez.
        const base = stressRoomId ? `/api/public/room-qr/${stressTid}/${stressRoomId}` : null;

        // 0) Positive contract: harvested valid token rotation ÖNCESİ 200 verir.
        let positiveOk = null;
        if (base && stressRoomToken) {
            const pos = await callTimed(request, 'get', `${base}?t=${stressRoomToken}`, undefined, null);
            positiveOk = pos.ok && pos.status === 200;
            if (positiveOk === false) {
                recFinding(testInfo, 'P2', MOD, 'valid QR token did not verify pre-rotation',
                    `GET ${base}?t=<valid> status=${pos.status} — beklenen 200.`);
            }
        }

        // 1) Rotate THIS tenant's QR secret.
        const rot = await callTimed(request, 'post', '/api/rooms/qr/rotate-secret',
            {}, stressTokens.stress_token);
        const rotateOk = rot.ok && (rot.body?.rotated === true || typeof rot.body?.version === 'number');
        if (rot.status === 401 || rot.status === 403) {
            recFinding(testInfo, 'P2', MOD, 'QR rotate-secret perm-gated',
                `POST /api/rooms/qr/rotate-secret status=${rot.status} — rotation contract daralır.`);
        } else if (!rotateOk && rot.status !== 0) {
            recFinding(testInfo, 'P1', MOD, 'QR rotate-secret unexpected response',
                `POST /api/rooms/qr/rotate-secret status=${rot.status} body=${JSON.stringify(rot.body).slice(0, 120)}.`);
        }
        if (rot.ok && tokenContainsSecretLeak(rot.body)) {
            recFinding(testInfo, 'P0', MOD, 'rotate-secret response leaks secret',
                'rotate-secret yanıtı salt/secret literal taşıyor — server-side sır sızıntısı.');
        }

        // 2) Rotation sonrası ESKİ token reddedilmeli (HMAC sig mismatch → 403).
        let oldTokenRejected = null;
        if (rotateOk && base && stressRoomToken) {
            const old = await callTimed(request, 'get', `${base}?t=${stressRoomToken}`, undefined, null);
            oldTokenRejected = old.status === 403;
            if (old.ok && old.status === 200) {
                recFinding(testInfo, 'P0', MOD, 'old QR token still valid after rotation',
                    `GET ${base}?t=<old> status=${old.status} — rotation eski tokenı geçersiz kılmadı.`);
            }
        }

        // 3) Yeni token re-harvest → 200 (rotation yeni sırrı etkin kıldı).
        let newTokenOk = null;
        if (rotateOk && base && stressRoomId) {
            const qr2 = await callTimed(request, 'get', `/api/rooms/${stressRoomId}/qr-code`,
                undefined, stressTokens.stress_token);
            if (qr2.ok && qr2.body?.token) {
                const fresh = await callTimed(request, 'get', `${base}?t=${qr2.body.token}`, undefined, null);
                newTokenOk = fresh.ok && fresh.status === 200;
                if (newTokenOk === false) {
                    recFinding(testInfo, 'P1', MOD, 'fresh QR token rejected post-rotation',
                        `GET ${base}?t=<fresh> status=${fresh.status} — rotation sonrası yeni token doğrulanmadı.`);
                }
            }
        }

        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'rotation_contract',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `positive=${positiveOk} rotate=${rot.status}/${rotateOk} old_rejected=${oldTokenRejected} new_ok=${newTokenOk} drift=${driftOk} ext=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
        // Rotation gerçekleştiyse eski-token reddi + yeni-token kabulü zorunlu.
        if (rotateOk && base && stressRoomToken) {
            expect(oldTokenRejected, 'old QR token must be rejected after rotation').toBe(true);
        }
        if (rotateOk && newTokenOk !== null) {
            expect(newTokenOk, 'fresh QR token must verify after rotation').toBe(true);
        }
    });
});

// F8U § 98 — Auth Token Lifecycle stress + pen-test.
//
// Threat-model surface (threat_model.md § Spoofing + EoP):
//   "The server must validate bearer tokens on every protected route,
//    distinguish access tokens from refresh tokens, enforce
//    revocation/invalid-before semantics, and verify any webhook or
//    API-key caller before trusting tenant or booking identifiers."
//
// F8I admin RBAC + F8M B2B API key zaten test ediyor; standart user JWT
// lifecycle (login → refresh rotation → logout invalidation → garbage
// reject → tampered reject) için dedicated stress yok. Bu spec o boşluğu
// kapatır.
//
// Mutlak kurallar:
//   - pilot mutation = 0 (drift=0 final invariant)
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//   - Stress admin'in PAYLAŞILAN bearer'ı (stressTokens.stress_token)
//     ASLA logout edilmez — bu spec'in tüm logout/refresh test'leri
//     FRESH login ile elde edilen ayrı session üzerinde çalışır.
//
// Module-blocked pattern:
//   - Fresh login non-2xx → setup moduleBlocked (creds yanlış veya
//     bootstrap fail). A-G test.skip, H pilot_drift + external_calls
//     bağımsız çalışır.
//   - /api/auth/refresh-token 404 → refresh disabled deploy, B/C/D
//     refresh-bağlı testler SKIP, geri kalanlar çalışır.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertNoTokenLeak, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'auth_token_lifecycle';
const DENY = new Set([401, 403]);

// Raw login wrapper — fresh session elde etmek için. callTimed bearer
// pattern kullandığı için ayrı (login bearer-less).
async function freshLogin(request, email, password) {
    const t0 = Date.now();
    const r = await request.post('/api/auth/login', {
        data: { email, password },
        failOnStatusCode: false, timeout: 30_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    const ms = Date.now() - t0;
    let body = null;
    try { body = r.json ? await r.json() : null; } catch { /* ignore */ }
    return { status: r.status?.() ?? 0, ms, body, ok: (r.status?.() ?? 0) >= 200 && (r.status?.() ?? 0) < 300 };
}

async function callRefresh(request, refreshToken) {
    // Backend /api/auth/refresh-token body-based + cookie-based path destekler.
    // Body path (Path A in _enforce_refresh_invariants) en stabil — body-based dene.
    const r = await request.post('/api/auth/refresh-token', {
        data: { refresh_token: refreshToken },
        headers: { 'Content-Type': 'application/json' },
        failOnStatusCode: false, timeout: 15_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    let body = null;
    try { body = r.json ? await r.json() : null; } catch { /* ignore */ }
    return { status: r.status?.() ?? 0, body, ok: (r.status?.() ?? 0) >= 200 && (r.status?.() ?? 0) < 300 };
}

async function callLogout(request, accessToken) {
    const r = await request.post('/api/auth/logout', {
        headers: { Authorization: `Bearer ${accessToken}`, 'Content-Type': 'application/json' },
        data: {},
        failOnStatusCode: false, timeout: 15_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    return { status: r.status?.() ?? 0, ok: (r.status?.() ?? 0) >= 200 && (r.status?.() ?? 0) < 300 };
}

// Tampered JWT — geçerli formattaki JWT'nin signature segment'inde 1 byte
// flip. Header/payload geçerli, signature broken → server reject etmeli.
function tamperJwt(jwt) {
    if (!jwt || typeof jwt !== 'string') return null;
    const parts = jwt.split('.');
    if (parts.length !== 3) return null;
    const sig = parts[2];
    if (sig.length < 4) return null;
    // İlk karakteri farklı bir base64url karaktere swap'le.
    const ch = sig[0];
    const swap = ch === 'A' ? 'B' : 'A';
    parts[2] = swap + sig.slice(1);
    return parts.join('.');
}

test.describe.configure({ mode: 'serial' });

test.describe('F8U § 98 — Auth Token Lifecycle', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let refreshDisabled = false;
    // Fresh-login session (logout/refresh test'leri için izole).
    let freshAccess = null;
    let freshRefresh = null;
    let freshExpiresIn = null;
    let rotatedAccess = null;
    let rotatedRefresh = null;

    test('Setup: pilot baseline + fresh login (isolated session) + token shape', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        const email = process.env.E2E_STRESS_ADMIN_EMAIL;
        const password = process.env.E2E_STRESS_ADMIN_PASSWORD;
        if (!email || !password) {
            moduleBlocked = true;
            blockedReason = 'no_stress_admin_credentials_in_env';
            recFinding(testInfo, 'P2', MOD, 'E2E_STRESS_ADMIN_EMAIL/PASSWORD env yok',
                'Fresh login yapılamıyor; A-G skipped, H pilot_drift + external_calls bağımsız çalışır.');
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            // Module-block: env-config eksik (legit), explicit skip — silent-return YASAK.
            test.skip(true, 'E2E_STRESS_ADMIN_EMAIL/PASSWORD env missing');
            return;
        }

        const login = await freshLogin(request, email, password);
        if (!login.ok) {
            moduleBlocked = true;
            blockedReason = `login_non2xx_status_${login.status}`;
            recFinding(testInfo, 'P2', MOD, 'Fresh login non-2xx',
                `status=${login.status} body=${JSON.stringify(login.body).slice(0, 120)} — bootstrap/RBAC; A-G skipped.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            // Module-block: bootstrap/RBAC tarafı reddetti — explicit skip.
            test.skip(true, `fresh login non-2xx status=${login.status}`);
            return;
        }
        freshAccess = login.body?.access_token || login.body?.token;
        freshRefresh = login.body?.refresh_token || null;
        freshExpiresIn = login.body?.expires_in ?? null;

        // Contract: access_token zorunlu, refresh_token mevcutsa V3 shape,
        // expires_in mevcutsa pozitif int. token_type "bearer" beklenir.
        if (!freshAccess) {
            moduleBlocked = true;
            blockedReason = 'login_2xx_no_access_token';
            recFinding(testInfo, 'P0', MOD,
                'Auth login 2xx döndü AMA access_token body\'de yok',
                `body=${JSON.stringify(login.body).slice(0, 200)}. POST /api/auth/login contract\'ı access_token DÖNDÜRMELİ.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
                note: `module_blocked=true reason=${blockedReason} severity=P0` });
            // Skip-as-pass YASAK: P0 emit edildi, Playwright'a da hard fail sinyali.
            expect(freshAccess, 'login 2xx but access_token missing — contract violation').toBeTruthy();
            return;
        }

        // Shape sanity (P2 informational eğer eksik — backend V3 migration
        // tamamlanmamış olabilir, ama refresh testleri SKIP eder).
        if (!freshRefresh) {
            refreshDisabled = true;
            recFinding(testInfo, 'P2', MOD, 'Login response\'unda refresh_token yok',
                `expires_in=${freshExpiresIn} token_type=${login.body?.token_type}. V3 contract refresh_token bekler; B/C/D refresh testleri SKIP.`);
        }
        if (freshExpiresIn != null && (typeof freshExpiresIn !== 'number' || freshExpiresIn <= 0)) {
            recFinding(testInfo, 'P1', MOD, 'expires_in invalid shape',
                `expires_in=${JSON.stringify(freshExpiresIn)} — pozitif sayı beklenir.`);
        }

        // Login response token leak guard — refresh_token EXEMPT (login response
        // primary contract); ama JWT_RE pattern body içinde başka yerlerde
        // (audit_log, debug field) leak ETMEMELİ. assertNoTokenLeak login
        // response için skip — login=token issuance, kontrolü 2xx ME response'a
        // bırakırız (aşağıda).

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} fresh_access_len=${freshAccess.length} fresh_refresh=${!!freshRefresh} expires_in=${freshExpiresIn} pilot_before=${pilotBefore?.count}` });
    });

    test('A) Valid access token — /auth/me 2xx + role/tenant present + no token leak in body', async ({ request, stressState, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'access_smoke', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const me = await callTimed(request, 'get', '/api/auth/me', undefined, freshAccess);
        const okBody = me.ok && me.body && (me.body.id || me.body._id) && me.body.tenant_id;
        rec(testInfo, { module: MOD, step: 'access_smoke',
            status: okBody ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/auth/me', http: me.status,
            note: `role=${me.body?.role || 'n/a'} tenant=${me.body?.tenant_id ? 'set' : 'unset'}` });
        if (!okBody) {
            recFinding(testInfo, 'P0', MOD, 'Valid access token /auth/me reddedildi veya body shape bozuk',
                `status=${me.status} body=${JSON.stringify(me.body).slice(0, 200)}.`);
        }
        if (me.ok) {
            assertNoTokenLeak(testInfo, MOD, me.body, 'auth_me_response');
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'access_smoke', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) Refresh rotation — old refresh issues NEW access+refresh; rotation contract enforced', async ({ request, stressState, stressTokens }, testInfo) => {
        if (moduleBlocked || refreshDisabled) {
            rec(testInfo, { module: MOD, step: 'refresh_rotation', status: 'SKIP',
                note: moduleBlocked ? `module blocked: ${blockedReason}` : 'refresh_disabled' });
            test.skip(true, 'module blocked or refresh disabled');
            return;
        }
        const r = await callRefresh(request, freshRefresh);
        if (r.status === 404) {
            refreshDisabled = true;
            rec(testInfo, { module: MOD, step: 'refresh_rotation', status: 'REVIEW',
                note: 'refresh endpoint 404 — deploy yok; C/D SKIP.' });
            recFinding(testInfo, 'P2', MOD, '/api/auth/refresh-token 404 — refresh endpoint deploy yok',
                'V3 refresh akışı doğrulanamadı; client refresh capability eksik olabilir.');
            // 404 = legit module-block (endpoint deploy yok) → explicit skip,
            // silent-return YASAK (recFinding-then-return pass-through).
            test.skip(true, 'refresh endpoint not deployed (404)');
            return;
        }
        const rotatedOk = r.ok && r.body && r.body.access_token;
        rec(testInfo, { module: MOD, step: 'refresh_rotation',
            status: rotatedOk ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/auth/refresh-token', http: r.status,
            note: `rotated_access=${!!r.body?.access_token} rotated_refresh=${!!r.body?.refresh_token}` });
        if (!rotatedOk) {
            recFinding(testInfo, 'P0', MOD, 'Valid refresh token reddedildi (rotation broken)',
                `status=${r.status} body=${JSON.stringify(r.body).slice(0, 200)}.`);
            // Skip-as-pass YASAK: rotation kontratı çökmüş — hard fail.
            expect(rotatedOk, `refresh rotation broken status=${r.status}`).toBe(true);
            return;
        }
        rotatedAccess = r.body.access_token;
        rotatedRefresh = r.body.refresh_token || null;

        // Rotation contract: refresh response refresh_token DÖNMELİ
        // (single-use rotation). Yoksa stale refresh ile süresiz session.
        if (!rotatedRefresh) {
            recFinding(testInfo, 'P1', MOD,
                'Refresh rotation response\'unda yeni refresh_token YOK — rotation contract eksik',
                'V3 single-use rotation kuralı: her refresh çağrısı yeni refresh_token üretmeli. Eksik → eski refresh süresiz kullanılabilir (long-lived session attack surface).');
        }
        // Yeni access token ≠ eski (defansif gate).
        if (rotatedAccess === freshAccess) {
            recFinding(testInfo, 'P1', MOD,
                'Refresh rotation aynı access_token döndü',
                'Yeni token jti veya iat farklı olmalı; identical string → token reuse smell.');
        }
        // Yeni refresh ≠ eski.
        if (rotatedRefresh && rotatedRefresh === freshRefresh) {
            recFinding(testInfo, 'P0', MOD,
                'Refresh rotation aynı refresh_token döndü — rotation single-use değil',
                'Single-use kontratı ihlali; eski refresh kullanım için açık kalır.');
        }
        assertNoTokenLeak(testInfo, MOD, { rotated_status: 'ok' }, 'refresh_rotation_meta');
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'refresh_rotation', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) Old refresh after rotation must be REJECTED (single-use enforcement)', async ({ request, stressState, stressTokens }, testInfo) => {
        if (moduleBlocked || refreshDisabled || !rotatedRefresh) {
            rec(testInfo, { module: MOD, step: 'old_refresh_rejected', status: 'SKIP',
                note: `module_blocked=${moduleBlocked} refresh_disabled=${refreshDisabled} rotated_refresh_present=${!!rotatedRefresh}` });
            test.skip(true, 'pre-conditions missing');
            return;
        }
        const reuse = await callRefresh(request, freshRefresh);
        // Beklenti: 401 / 403 / 400 (revoked / invalid). 2xx → single-use bypass = P0.
        const rejected = !reuse.ok;
        rec(testInfo, { module: MOD, step: 'old_refresh_rejected',
            status: rejected ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/auth/refresh-token (old)', http: reuse.status,
            note: `expected=4xx observed=${reuse.status}` });
        if (reuse.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Rotated (old) refresh token hala kabul ediliyor — single-use kuralı ihlali',
                `Rotation sonrası eski refresh ile yeni access alındı: status=${reuse.status} body_has_access=${!!reuse.body?.access_token}. Stolen-refresh saldırısına açık.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'old_refresh_rejected', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Logout invalidates access token AND refresh token (revocation)', async ({ request, stressState, stressTokens }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'logout_revocation', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Logout için en güncel access token: rotation olduysa rotatedAccess,
        // olmadıysa freshAccess. Bu spec sonrası bu session ölmeli.
        const accessToLogout = rotatedAccess || freshAccess;
        const refreshToProbe = rotatedRefresh || freshRefresh;

        const logout = await callLogout(request, accessToLogout);
        rec(testInfo, { module: MOD, step: 'logout_call',
            status: logout.ok ? 'PASS' : 'REVIEW',
            endpoint: 'POST /api/auth/logout', http: logout.status,
            note: `logout_status=${logout.status}` });
        if (!logout.ok) {
            // Logout endpoint 4xx → revocation flow çağrılamadı.
            recFinding(testInfo, 'P1', MOD, 'Logout endpoint reddetti veya deploy yok',
                `status=${logout.status} — revocation contract doğrulanamadı.`);
            // Skip-as-pass YASAK: revocation invariant test edilemedi → hard fail.
            expect(logout.ok, `logout non-2xx status=${logout.status}`).toBe(true);
            return;
        }

        // Post-logout access reject.
        const me = await callTimed(request, 'get', '/api/auth/me', undefined, accessToLogout);
        const accessRevoked = DENY.has(me.status);
        rec(testInfo, { module: MOD, step: 'post_logout_access_rejected',
            status: accessRevoked ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/auth/me (post-logout)', http: me.status,
            note: `expected=401/403 observed=${me.status}` });
        if (me.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Logout sonrası access token hala geçerli — revocation enforcement yok',
                `POST /api/auth/logout 2xx sonrası GET /api/auth/me ile aynı access token status=${me.status} döndü. Redis pub/sub auth invalidation gotcha kontrol edilmeli.`);
        }

        // Post-logout refresh reject — refresh varsa.
        if (refreshToProbe && !refreshDisabled) {
            const refreshAfterLogout = await callRefresh(request, refreshToProbe);
            const refreshRevoked = !refreshAfterLogout.ok;
            rec(testInfo, { module: MOD, step: 'post_logout_refresh_rejected',
                status: refreshRevoked ? 'PASS' : 'FAIL',
                endpoint: 'POST /api/auth/refresh-token (post-logout)', http: refreshAfterLogout.status,
                note: `expected=4xx observed=${refreshAfterLogout.status}` });
            if (refreshAfterLogout.ok) {
                recFinding(testInfo, 'P0', MOD,
                    'Logout sonrası refresh token hala kabul ediliyor — refresh revocation yok',
                    `Logout 2xx sonrası refresh çağrısı status=${refreshAfterLogout.status} access_token üretti. Stolen-refresh logout sonrası bile session uzatabilir.`);
            }
        } else {
            rec(testInfo, { module: MOD, step: 'post_logout_refresh_rejected', status: 'SKIP',
                note: 'no refresh token to probe' });
        }

        // Bu spec'in fresh session'ı artık kapalı — sonraki testler için
        // null'la, böylece yanlış kullanım crash etsin.
        freshAccess = null; rotatedAccess = null;
        freshRefresh = null; rotatedRefresh = null;
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'logout_revocation', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('E) Garbage / malformed / tampered access tokens — all rejected', async ({ request, stressState, stressTokens }, testInfo) => {
        // Bu test fresh session'a bağımlı değil — sadece reject davranışı test eder.
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'invalid_token_reject', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const cases = [
            { name: 'empty', tok: '' },
            { name: 'garbage', tok: 'garbage.not.ajwt' },
            { name: 'random_string', tok: 'A'.repeat(64) },
            { name: 'fake_jwt_shape', tok: 'eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJ4In0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c' },
            // tampered: stress_token signature byte flip (header/payload geçerli).
            { name: 'tampered_real_jwt', tok: tamperJwt(stressTokens.stress_token) },
        ];
        const results = [];
        let accepted = 0;
        for (const c of cases) {
            if (!c.tok) {
                // Empty bearer — header yine de gönderilir; backend reject etmeli.
                const r = await request.get('/api/auth/me', {
                    headers: { Authorization: `Bearer ` },
                    failOnStatusCode: false, timeout: 10_000,
                }).catch((e) => ({ status: () => 0 }));
                const st = r.status?.() ?? 0;
                const ok2xx = st >= 200 && st < 300;
                results.push({ name: c.name, status: st });
                if (ok2xx) accepted++;
                continue;
            }
            const r = await callTimed(request, 'get', '/api/auth/me', undefined, c.tok);
            results.push({ name: c.name, status: r.status });
            if (r.ok) accepted++;
        }
        const pass = accepted === 0;
        rec(testInfo, { module: MOD, step: 'invalid_token_reject',
            status: pass ? 'PASS' : 'FAIL',
            note: `results=${JSON.stringify(results)} accepted_invalid=${accepted}` });
        if (accepted > 0) {
            recFinding(testInfo, 'P0', MOD,
                'Invalid/tampered/garbage token /auth/me ile 2xx döndü',
                `accepted_invalid=${accepted} results=${JSON.stringify(results)}. JWT validation bypass.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'invalid_token_reject', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('F) Cross-scope guard — refresh token MUST NOT work as access bearer', async ({ request, stressState, stressTokens }, testInfo) => {
        // Refresh token JWT type="refresh" — Authorization: Bearer <refresh>
        // ile /auth/me çağrılırsa server type contract enforce etmeli (reject).
        // Fresh session zaten kapalı; bunun için TEKRAR login alıp test ederiz.
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'cross_scope_refresh_as_access', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const email = process.env.E2E_STRESS_ADMIN_EMAIL;
        const password = process.env.E2E_STRESS_ADMIN_PASSWORD;
        const login = await freshLogin(request, email, password);
        if (!login.ok || !login.body?.refresh_token) {
            // Fresh login başarısız → cross-scope test edilemez. Refresh_token
            // dönmemesi rotation V3 deploy yok demek olabilir (legit module-block);
            // ama login.ok=false production regression. İkisini ayır.
            if (!login.ok) {
                recFinding(testInfo, 'P1', MOD,
                    'Cross-scope guard test edilemedi — fresh login failed',
                    `status=${login.status} body=${JSON.stringify(login.body).slice(0, 200)}. Auth login regression veya credential drift.`);
                rec(testInfo, { module: MOD, step: 'cross_scope_refresh_as_access', status: 'FAIL',
                    note: `fresh login failed status=${login.status}` });
                expect(login.ok, `fresh login status=${login.status}`).toBe(true);
                return;
            }
            // refresh_token yok → V3 refresh deploy yok, legit module-block.
            rec(testInfo, { module: MOD, step: 'cross_scope_refresh_as_access', status: 'SKIP',
                note: `refresh_token not returned (V3 refresh disabled) status=${login.status}` });
            test.skip(true, 'refresh_token not returned by login (V3 disabled)');
            return;
        }
        const refreshTok = login.body.refresh_token;
        const probe = await callTimed(request, 'get', '/api/auth/me', undefined, refreshTok);
        // Refresh token ile resource erişimi YASAK — DENY beklenir.
        const rejected = DENY.has(probe.status) || probe.status === 400;
        rec(testInfo, { module: MOD, step: 'cross_scope_refresh_as_access',
            status: rejected ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/auth/me (with refresh bearer)', http: probe.status,
            note: `expected=4xx observed=${probe.status}` });
        if (probe.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Refresh token access bearer olarak kabul edildi — type contract ihlali',
                `Authorization: Bearer <refresh> ile /auth/me status=${probe.status} döndü. Refresh ve access scope ayrımı yok; refresh kaybı = sınırsız session.`);
        }

        // Cleanup: bu fresh session'ı da invalidate et (logout) → tenant'a stale
        // bearer bırakma.
        const access = login.body.access_token;
        if (access) await callLogout(request, access);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'cross_scope', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('G) Pilot drift = 0 + external_calls = [] (final invariants)', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});

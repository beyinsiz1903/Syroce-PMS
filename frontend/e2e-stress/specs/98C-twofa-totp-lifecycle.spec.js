// F8AG § 98C — 2FA TOTP Lifecycle Stress + Pen-Test.
//
// Threat-model surface (threat_model.md § Spoofing + EoP):
//   "The server must validate bearer tokens on every protected route,
//    distinguish access tokens from refresh tokens, enforce
//    revocation/invalid-before semantics, and verify any webhook or
//    API-key caller before trusting tenant or booking identifiers."
//
// 2FA TOTP guards every staff/admin login surface. A silent regression in
// throttling, same-window replay-guard, backup-code single-use, or tenant
// scoping would directly collapse the spoofing / elevation-of-privilege
// boundaries described in threat_model.md. F8U covers session/refresh
// lifecycle; F8AG covers the 2FA verify boundary itself.
//
// Mutlak kurallar:
//   - pilot mutation = 0 (drift=0 final invariant)
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//   - Stress admin'in PAYLAŞILAN bearer'ı (stressTokens.stress_token) bu
//     spec'in /setup, /setup/confirm, /disable, /regenerate-backup-codes
//     yüzeyleri için KULLANILIR (current_user current bearer); ama spec
//     CLEANUP'ı zorunlu (try/finally) — 2FA enabled bırakırsa diğer spec'lerin
//     paylaşılan bearer login refresh'i ASLA çalışmaz (login → requires_2fa
//     challenge → tüm downstream specs çöker).
//   - Fresh login (yeni session) sadece /auth/login → challenge → /auth/2fa/verify
//     happy-path + replay-guard subtest'leri için.
//
// Module-blocked pattern:
//   - GET /api/2fa/status non-2xx → setup moduleBlocked (RBAC veya endpoint
//     deploy yok). A-G test.skip, H pilot_drift + external_calls bağımsız.
//   - 2FA already enabled at probe time → setup moduleBlocked (önceki run
//     residue) + P2 REVIEW; cleanup attempted in afterAll.
//   - E2E_STRESS_ADMIN_EMAIL/PASSWORD env yok → module blocked + P2.
//
// Brute-force isolation:
//   - TWOFA_VERIFY_IP (15/60s) is endpoint-scoped (`/auth/2fa/verify` only).
//     Burst içinde DENEME = 17 (threshold+2) → expected ≥1× 429 yakalanır.
//     Diğer spec'ler /auth/2fa/verify çağırmadığı için bleed YOK; pencere
//     60s'de doğal expire eder. Ek sleep gerekmez.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    assertNoTokenLeak, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';
import { createHmac } from 'node:crypto';

const MOD = 'twofa_lifecycle';
const DENY = new Set([401, 403]);

// ── Base32 decode + TOTP (RFC 6238, HMAC-SHA1, 30s step, 6 digits) ──
// pyotp/otplib bağımlılığı yok; node:crypto yeterli.
function base32Decode(b32) {
    const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
    const clean = String(b32 || '').toUpperCase().replace(/=+$/, '').replace(/\s+/g, '');
    let bits = '';
    for (const ch of clean) {
        const v = alphabet.indexOf(ch);
        if (v < 0) throw new Error(`base32 invalid char: ${ch}`);
        bits += v.toString(2).padStart(5, '0');
    }
    const bytes = [];
    for (let i = 0; i + 8 <= bits.length; i += 8) {
        bytes.push(parseInt(bits.slice(i, i + 8), 2));
    }
    return Buffer.from(bytes);
}

function totpAt(secretB32, unixSeconds, step = 30, digits = 6) {
    const key = base32Decode(secretB32);
    const counter = Math.floor(unixSeconds / step);
    const buf = Buffer.alloc(8);
    // 64-bit big-endian counter (JS number safe for counter ranges we use).
    buf.writeBigUInt64BE(BigInt(counter), 0);
    const hmac = createHmac('sha1', key).update(buf).digest();
    const offset = hmac[hmac.length - 1] & 0x0f;
    const code = ((hmac[offset] & 0x7f) << 24)
        | ((hmac[offset + 1] & 0xff) << 16)
        | ((hmac[offset + 2] & 0xff) << 8)
        | (hmac[offset + 3] & 0xff);
    return String(code % 10 ** digits).padStart(digits, '0');
}

function currentTotp(secretB32) {
    return totpAt(secretB32, Math.floor(Date.now() / 1000));
}

async function freshLogin(request, email, password) {
    const r = await request.post('/api/auth/login', {
        data: { email, password },
        failOnStatusCode: false, timeout: 30_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    let body = null;
    try { body = r.json ? await r.json() : null; } catch { /* ignore */ }
    return { status: r.status?.() ?? 0, body, ok: (r.status?.() ?? 0) >= 200 && (r.status?.() ?? 0) < 300 };
}

async function call2faVerify(request, challengeToken, code, opts = {}) {
    const headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    // Timeout overridable — D) brute-force burst fires 17 verifies in
    // parallel against a single-worker uvicorn; HOL blocking on serialized
    // Mongo writes (consume_jti + throttle insert/count + audit_log per
    // request) can push tail requests past the default 15s, returning
    // status=0 (Playwright client cancel) instead of the expected 429.
    // Per-call override lets the brute-force test grant >60s so every
    // request completes within the throttle's 60s window.
    const r = await request.post('/api/auth/2fa/verify', {
        data: { challenge_token: challengeToken, code },
        headers,
        failOnStatusCode: false, timeout: opts.timeout || 15_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    let body = null;
    try { body = r.json ? await r.json() : null; } catch { /* ignore */ }
    return { status: r.status?.() ?? 0, body, ok: (r.status?.() ?? 0) >= 200 && (r.status?.() ?? 0) < 300 };
}

test.describe.configure({ mode: 'serial' });

test.describe('F8AG § 98C — 2FA TOTP Lifecycle', () => {
    let pilotBefore = null;
    let prefix = null;
    let moduleBlocked = false;
    let blockedReason = null;
    let tempUserToken = null;
    let testEmail = null;
    let testPassword = null;
    let secret = null;          // plaintext TOTP secret returned by /setup
    let backupCodes = null;     // plaintext backup codes returned by /setup/confirm
    let twofaEnabled = false;   // tracked so afterAll can cleanly disable
    let usedConfirmCode = null; // for same-window replay assertion across endpoints
    // F8AH P1 fix — track ALL TOTP codes the suite has already consumed via
    // /auth/2fa/verify or /2fa/regenerate-backup-codes so that downstream
    // tests (notably F: regenerate-backup-codes) can wait for a fresh slot
    // instead of colliding with the cross-endpoint TOTP single-use guard
    // (Bug CB v45 — `consume_totp_counters` claims all matching counters
    // atomically and never frees them within the matching window).
    const usedTotpCodes = new Set();

    // ── afterAll: ALWAYS disable 2FA so shared bearer login keeps working ──
    test.afterAll(async ({ }, testInfo) => {
        if (!twofaEnabled) return;
        const fs = await import('node:fs');
        const path = await import('node:path');
        const { request: plRequest } = await import('@playwright/test');
        const tokenFile = path.join(process.cwd(), 'e2e-stress', '.auth', 'stress-token.json');
        let tokens = null;
        try { tokens = JSON.parse(fs.readFileSync(tokenFile, 'utf-8')); } catch { /* ignore */ }
        const password = testPassword || process.env.E2E_STRESS_ADMIN_PASSWORD;
        const activeToken = tempUserToken || tokens?.stress_token;
        if (!activeToken || !password || !secret) {
            // Best-effort: log to stderr; cleanup failure is logged but doesn't FAIL afterAll.
            // eslint-disable-next-line no-console
            console.error('[F8AG] afterAll cleanup skipped — missing token/password/secret.');
            return;
        }
        const ctx = await plRequest.newContext({ baseURL: process.env.E2E_BASE_URL || 'http://localhost:8000' });
        try {
            // Try a wider TOTP candidate window in case of clock drift (±90s)
            // AND skip same-counter as `usedConfirmCode` (same-window replay
            // guard). Each candidate gets a fresh 30s timeout (Atlas can be
            // slow under stress run load).
            const now = Math.floor(Date.now() / 1000);
            const candidates = [now, now + 30, now + 60, now + 90, now - 30, now - 60, now - 90];
            for (let i = 0; i < candidates.length && twofaEnabled; i++) {
                const t = candidates[i];
                const code = totpAt(secret, t);
                if (code === usedConfirmCode || usedTotpCodes.has(code)) continue;
                const r = await ctx.post('/api/2fa/disable', {
                    data: { password, code },
                    headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
                    failOnStatusCode: false, timeout: 30_000,
                }).catch(() => null);
                if (r && r.ok()) { twofaEnabled = false; break; }
                // Throttle backoff if 429 hit (SENSITIVE_AUTH_USER 5/900s).
                if (r && r.status() === 429) await new Promise((res) => setTimeout(res, 3000));
            }
            // Fallback chain: try EVERY remaining backup code (newest first).
            // Single-use semantics mean an already-consumed code is just a
            // wasted attempt, not a failure — keep trying until one works.
            if (twofaEnabled && Array.isArray(backupCodes) && backupCodes.length > 0) {
                for (let i = backupCodes.length - 1; i >= 0 && twofaEnabled; i--) {
                    const r = await ctx.post('/api/2fa/disable', {
                        data: { password, code: backupCodes[i] },
                        headers: { Authorization: `Bearer ${activeToken}`, 'Content-Type': 'application/json' },
                        failOnStatusCode: false, timeout: 30_000,
                    }).catch(() => null);
                    if (r && r.ok()) { twofaEnabled = false; break; }
                    if (r && r.status() === 429) await new Promise((res) => setTimeout(res, 3000));
                }
            }
        } finally {
            await ctx.dispose();
        }
        if (twofaEnabled) {
            // eslint-disable-next-line no-console
            console.error('[F8AG] CRITICAL: 2FA cleanup FAILED — stress admin still has 2FA enabled; next stress run logins will be challenged. RECOVERY: run `python backend/scripts/reset_stress_admin_2fa.py --apply` from a host that can reach Atlas + has E2E_STRESS_ADMIN_EMAIL set.');
        }
    });

    test('Setup: pilot baseline + module probe + status snapshot', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        testEmail = `2fa-test-${Date.now()}@syroce.com`;
        testPassword = 'AuthTestPass123!';

        // Create a temporary user to avoid changing the shared admin's 2FA settings.
        const createStaff = await request.post('/api/hotel/team', {
            data: { email: testEmail, name: '2FA Test User', role: 'admin', password: testPassword },
            headers: { Authorization: `Bearer ${stressTokens.stress_token}` },
            failOnStatusCode: false, timeout: 60_000,
        });

        if (!createStaff.ok()) {
            moduleBlocked = true;
            blockedReason = `temp_user_creation_failed_${createStaff.status()}`;
            recFinding(testInfo, 'P2', MOD, 'Temp user creation failed',
                `status=${createStaff.status()} — A-G skipped.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            test.skip(true, 'Temporary user creation failed');
            return;
        }

        const login = await freshLogin(request, testEmail, testPassword);
        if (!login.ok) {
            moduleBlocked = true;
            blockedReason = `login_non2xx_status_${login.status}`;
            recFinding(testInfo, 'P2', MOD, 'Fresh login non-2xx',
                `status=${login.status} — A-G skipped.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            test.skip(true, 'Temporary user login failed');
            return;
        }
        tempUserToken = login.body.access_token;

        const email = testEmail;
        const password = testPassword;

        // Module probe.
        const probe = await callTimed(request, 'get', '/api/2fa/status', undefined, tempUserToken);
        if (probe.status === 403 || probe.status === 404 || probe.status === 0) {
            moduleBlocked = true;
            blockedReason = `status_probe_${probe.status}`;
            recFinding(testInfo, 'P2', MOD, '2FA status endpoint reachable değil',
                `status=${probe.status} body=${JSON.stringify(probe.body).slice(0, 120)} — 2FA modülü deploy yok veya RBAC kapalı; lifecycle A-G skipped.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
                note: `module_blocked=true reason=${blockedReason}` });
            test.skip(true, `2FA status probe ${probe.status}`);
            return;
        }
        if (!probe.ok) {
            moduleBlocked = true;
            blockedReason = `status_probe_unexpected_${probe.status}`;
            recFinding(testInfo, 'P1', MOD, '2FA status probe unexpected non-2xx',
                `status=${probe.status} body=${JSON.stringify(probe.body).slice(0, 200)}.`);
            rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
                note: `module_blocked=true reason=${blockedReason}` });
            expect(probe.ok, `2FA status probe non-2xx status=${probe.status}`).toBe(true);
            return;
        }
        // Status response shape — token leak guard (defensive: enabled flag etc).
        assertNoTokenLeak(testInfo, MOD, probe.body, 'twofa_status_response');

        if (probe.body?.enabled) {
            // Residue from a previous broken run — try to disable up-front via
            // backup code path is impossible (we don't have the secret/codes).
            // Mark module blocked + P1 + return (afterAll cleanup also no-op).
            moduleBlocked = true;
            blockedReason = 'twofa_already_enabled_residue';
            recFinding(testInfo, 'P1', MOD,
                '2FA stress admin\'de zaten enabled — önceki run residue',
                'Spec lifecycle test edemez (secret/backup codes elde değil). RECOVERY: `python backend/scripts/reset_stress_admin_2fa.py --apply` (Atlas erişimi olan host\'tan, E2E_STRESS_ADMIN_EMAIL env\'i set). Aksi halde downstream tüm spec\'lerin login\'i challenge döner.');
            rec(testInfo, { module: MOD, step: 'setup', status: 'FAIL',
                note: 'twofa_already_enabled — residue, run backend/scripts/reset_stress_admin_2fa.py --apply' });
            expect(probe.body.enabled, 'stress admin should not have 2FA enabled at spec start — residue').toBe(false);
            return;
        }

        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} status_enabled=${probe.body?.enabled} pending=${probe.body?.pending_setup} backup_remaining=${probe.body?.backup_codes_remaining} pilot_before=${pilotBefore?.count}` });
    });

    test('A) Setup → returns secret + otpauth URI + QR data URL (pending state)', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'setup_pending', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        const r = await callTimed(request, 'post', '/api/2fa/setup', {}, tempUserToken);
        const okShape = r.ok && r.body && typeof r.body.secret === 'string' && r.body.secret.length >= 16
            && typeof r.body.otpauth_uri === 'string' && r.body.otpauth_uri.startsWith('otpauth://')
            && typeof r.body.qr_code === 'string' && r.body.qr_code.startsWith('data:image/');
        rec(testInfo, { module: MOD, step: 'setup_pending',
            status: okShape ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/2fa/setup', http: r.status,
            note: `secret_len=${r.body?.secret?.length ?? 0} uri_prefix_ok=${r.body?.otpauth_uri?.startsWith('otpauth://')} qr_data_url=${r.body?.qr_code?.startsWith('data:image/')}` });
        if (!okShape) {
            recFinding(testInfo, 'P1', MOD, '/api/2fa/setup contract bozuk',
                `status=${r.status} body_keys=${Object.keys(r.body || {}).join(',')}.`);
            expect(okShape, `setup contract violated status=${r.status}`).toBe(true);
            return;
        }
        secret = r.body.secret;
        // status snapshot — pending_setup true beklenir, enabled false.
        const after = await callTimed(request, 'get', '/api/2fa/status', undefined, tempUserToken);
        const pendingOk = after.ok && after.body?.enabled === false && after.body?.pending_setup === true;
        if (!pendingOk) {
            recFinding(testInfo, 'P1', MOD, '/api/2fa/setup sonrası status pending_setup=true değil',
                `status=${after.status} body=${JSON.stringify(after.body).slice(0, 200)}.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_pending', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) Confirm with wrong code → 400; correct code → enabled + backup codes', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || !secret) {
            rec(testInfo, { module: MOD, step: 'setup_confirm', status: 'SKIP', note: 'precondition missing (secret)' });
            test.skip(true, 'no secret');
            return;
        }
        // Wrong code rejection.
        const bad = await callTimed(request, 'post', '/api/2fa/setup/confirm', { code: '000000' }, tempUserToken);
        const badRejected = bad.status === 400 || bad.status === 401;
        rec(testInfo, { module: MOD, step: 'confirm_wrong_code',
            status: badRejected ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/2fa/setup/confirm (000000)', http: bad.status,
            note: `expected=400/401 observed=${bad.status}` });
        if (!badRejected) {
            recFinding(testInfo, 'P0', MOD, 'Confirm wrong code 2xx — enrollment validation yok',
                `status=${bad.status} body=${JSON.stringify(bad.body).slice(0, 200)}. Zero-knowledge 2FA enrollment bypass.`);
        }

        // Correct code → enrollment success.
        const code = currentTotp(secret);
        usedConfirmCode = code;
        const ok = await callTimed(request, 'post', '/api/2fa/setup/confirm', { code }, tempUserToken);
        const enrolled = ok.ok && ok.body?.enabled === true && Array.isArray(ok.body?.backup_codes) && ok.body.backup_codes.length >= 8;
        rec(testInfo, { module: MOD, step: 'confirm_correct_code',
            status: enrolled ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/2fa/setup/confirm', http: ok.status,
            note: `enabled=${ok.body?.enabled} backup_count=${Array.isArray(ok.body?.backup_codes) ? ok.body.backup_codes.length : 'n/a'}` });
        if (!enrolled) {
            recFinding(testInfo, 'P1', MOD, 'Confirm correct code enroll etmedi',
                `status=${ok.status} body=${JSON.stringify(ok.body).slice(0, 200)}.`);
            expect(enrolled, `confirm did not enroll status=${ok.status}`).toBe(true);
            return;
        }
        backupCodes = ok.body.backup_codes;
        twofaEnabled = true;
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'setup_confirm', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) Verify happy-path → exchange challenge_token for access_token + same-window replay guard', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || !secret || !twofaEnabled) {
            rec(testInfo, { module: MOD, step: 'verify_happy', status: 'SKIP', note: 'precondition missing' });
            test.skip(true, 'not enrolled');
            return;
        }
        const email = process.env.E2E_STRESS_ADMIN_EMAIL;
        const password = process.env.E2E_STRESS_ADMIN_PASSWORD;
        const login = await freshLogin(request, email, password);
        const isChallenge = login.ok && login.body?.requires_2fa === true && typeof login.body?.challenge_token === 'string';
        rec(testInfo, { module: MOD, step: 'login_challenge',
            status: isChallenge ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/auth/login', http: login.status,
            note: `requires_2fa=${login.body?.requires_2fa} challenge_token_present=${!!login.body?.challenge_token} access_token_empty=${login.body?.access_token === ''}` });
        if (!isChallenge) {
            recFinding(testInfo, 'P0', MOD,
                'Login 2FA enabled iken challenge yerine access_token döndü',
                `status=${login.status} body=${JSON.stringify(login.body).slice(0, 200)}. 2FA enforcement bypass.`);
            expect(isChallenge, '2FA challenge expected after enroll').toBe(true);
            return;
        }
        const challenge = login.body.challenge_token;

        // Same-counter code as confirm could collide; pick a distinct verify code
        // by waiting for the next 30s slot if necessary.
        let verifyCode = currentTotp(secret);
        if (verifyCode === usedConfirmCode || usedTotpCodes.has(verifyCode)) {
            // Wait until the next 30s window so the matched counter differs.
            const now = Math.floor(Date.now() / 1000);
            const next = (Math.floor(now / 30) + 1) * 30;
            const sleepMs = Math.max(0, (next - now) * 1000) + 1500;
            await new Promise((res) => setTimeout(res, sleepMs));
            verifyCode = currentTotp(secret);
        }
        const v = await call2faVerify(request, challenge, verifyCode);
        // Track BEFORE checking ok so a 4xx after backend-side consume still
        // marks the code as burnt (consume_totp_counters claims atomically
        // even when the request later fails for an unrelated reason).
        usedTotpCodes.add(verifyCode);
        const exchanged = v.ok && v.body?.access_token && v.body.access_token.length > 0;
        rec(testInfo, { module: MOD, step: 'verify_happy',
            status: exchanged ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/auth/2fa/verify', http: v.status,
            note: `access_token_issued=${!!v.body?.access_token}` });
        if (!exchanged) {
            recFinding(testInfo, 'P0', MOD,
                'Verify happy-path access_token üretmedi',
                `status=${v.status} body=${JSON.stringify(v.body).slice(0, 200)}.`);
            expect(exchanged, `verify happy-path failed status=${v.status}`).toBe(true);
            return;
        }

        // Same challenge_token replay → must be rejected (single-use jti).
        const replay = await call2faVerify(request, challenge, verifyCode);
        const replayRejected = !replay.ok;
        rec(testInfo, { module: MOD, step: 'verify_challenge_replay',
            status: replayRejected ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/auth/2fa/verify (replay)', http: replay.status,
            note: `expected=4xx observed=${replay.status}` });
        if (replay.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Aynı challenge_token ikinci /2fa/verify çağrısında kabul edildi — single-use jti yok',
                `status=${replay.status} body=${JSON.stringify(replay.body).slice(0, 200)}. consumed_jtis unique index regression.`);
        }
        // /api/auth/2fa/verify is a token-issuance endpoint (login-completion
        // contract): access_token + refresh_token in the body are REQUIRED,
        // not a leak. Guard still fires on any OTHER token-shaped field
        // (audit echoes, sibling response keys), preserving the threat-model
        // invariant while allowing the documented happy-path contract.
        assertNoTokenLeak(testInfo, MOD, v.body, 'verify_response', {
            allowedTokenKeys: ['access_token', 'refresh_token'],
            // JWT regex bypass is path-scoped (defence in depth) — must list
            // every leaf where a JWT-shaped value is legitimately returned.
            allowedJwtPaths: ['access_token', 'refresh_token'],
        });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'verify_happy', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Brute-force boundary — invalid codes hit TWOFA_VERIFY_IP throttle (15/60s) → ≥1× 429', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || !secret || !twofaEnabled) {
            rec(testInfo, { module: MOD, step: 'verify_throttle', status: 'SKIP', note: 'precondition missing' });
            test.skip(true, 'not enrolled');
            return;
        }
        const email = process.env.E2E_STRESS_ADMIN_EMAIL;
        const password = process.env.E2E_STRESS_ADMIN_PASSWORD;
        // Task-137 + Bug AS doctrine — /api/auth/2fa/verify consumes the
        // challenge_token jti atomically via consumed_jtis unique index
        // BEFORE the throttle enforce() can run (auth.py L779-788 vs L765).
        // A naive burst that reuses ONE challenge_token would only ever
        // increment the throttle counter on attempt #1 — attempts #2..N
        // bounce with 401 "Doğrulama belirteci zaten kullanıldı" via
        // DuplicateKeyError, never reaching _record_failure_and_raise.
        // Real brute-force vector = login + verify pair per attempt, so
        // each iteration must mint a fresh challenge_token. LOGIN_IP
        // (cap=20/60s) drains on every successful login (auth.py L525-526,
        // L698-699), so 17 fresh logins stay well under the LOGIN budget.
        // 17 burst = TWOFA_VERIFY_IP threshold(15) + 2 → at least the 16th
        // verify should hit 429. Each attempt uses fake code "111111";
        // backend's verify_totp fails → enforce(TWOFA_VERIFY_IP) +1.
        //
        // CI 2026-05-28 NO-GO P0 RCA — earlier sequential implementation
        // (login + verify in serial, ~3-5s/iter under Atlas write latency)
        // stretched the 17-iter loop across >60s, so the sliding window
        // never strictly exceeded 15 hits within any 60s slice → no 429.
        // Local `enforce()` smoke (in-process, ~8.9s for 17 calls) PASS
        // confirms Mongo backend works; the failure was test rate <
        // throttle rate. Real-world brute-force ALWAYS bursts (curl/script
        // can send 17 requests in <1s), so the test now models that:
        // (1) mint 17 fresh challenge tokens sequentially (each is single-
        //     use; sequential is fine because LOGIN throttle is per-IP not
        //     per-2FA-attempt and challenge minting itself is cheap), then
        // (2) fire all 17 /api/auth/2fa/verify calls in parallel via
        //     Promise.all. All 17 hits land in Mongo within ~1s window →
        //     cap=15 strictly exceeded → ≥2× 429 returned. This is a
        //     test-correctness fix (more realistic threat model), NOT an
        //     assertion loosening — pass criterion unchanged (≥1× 429).
        const challenges = [];
        for (let i = 0; i < 17; i++) {
            const login = await freshLogin(request, email, password);
            if (!login.ok || !login.body?.challenge_token) {
                recFinding(testInfo, 'P1', MOD,
                    `Throttle burst iterasyon ${i + 1} için challenge alınamadı`,
                    `status=${login.status} body=${JSON.stringify(login.body).slice(0, 200)}. Önceki iterasyonlardan LOGIN_IP throttle tripped olabilir; cap=20/60s, başarılı login reset eder.`);
                expect(login.ok, `throttle test iter=${i + 1} needs challenge status=${login.status}`).toBe(true);
                return;
            }
            challenges.push(login.body.challenge_token);
        }
        // Parallel burst — all 17 verify calls fire concurrently so the
        // sliding-window count strictly exceeds the cap. Per-call timeout
        // is bumped to 60s (throttle window) because head-of-line blocking
        // on serialized Mongo writes under single-worker uvicorn can push
        // tail requests past the default 15s, returning status=0
        // (Playwright client cancel) instead of the expected 429. With 60s
        // every request completes within the throttle window; the inserts
        // still all land before any age out, so cap=15 is exceeded.
        const verifyResponses = await Promise.all(
            challenges.map((ct) => call2faVerify(request, ct, '111111', { timeout: 60_000 }))
        );
        const results = verifyResponses.map((r) => r.status);
        const got429 = results.includes(429);
        rec(testInfo, { module: MOD, step: 'verify_throttle',
            status: got429 ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/auth/2fa/verify (burst)',
            note: `attempts=${results.length} statuses=${JSON.stringify(results)} got_429=${got429}` });
        if (!got429) {
            recFinding(testInfo, 'P0', MOD,
                'TWOFA_VERIFY_IP throttle 17 deneme sonrası 429 üretmedi — brute-force surface açık',
                `attempts=${results.length} statuses=${JSON.stringify(results)}. 6-digit TOTP code space=1M; throttle yoksa ~5dk içinde tamamı denenebilir.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'verify_throttle', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('E) Backup code single-use — consume one → second use rejected', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || !twofaEnabled || !Array.isArray(backupCodes) || backupCodes.length < 2) {
            rec(testInfo, { module: MOD, step: 'backup_single_use', status: 'SKIP', note: 'precondition missing' });
            test.skip(true, 'no backup codes');
            return;
        }
        // Wait for throttle window to clear from test D burst (TWOFA_VERIFY_IP).
        // /api/auth/2fa/verify path is throttled per-IP; we just used it. Sleep
        // 62s to let the 60s window expire (idempotent — also covers clock skew).
        // NOTE: this test doesn't call /2fa/verify; it uses /api/2fa/disable
        // (different endpoint, different throttle bucket SENSITIVE_AUTH_USER),
        // but /api/2fa/disable also calls SENSITIVE_AUTH_USER 5/900s — we've
        // not yet hit /disable so we have full budget. No sleep needed.

        const code = backupCodes[0];
        // First use via /disable would actually disable 2FA. We don't want
        // that mid-spec. Instead, test single-use semantics by using the
        // backup code via /api/auth/2fa/verify which also consumes it.
        const email = process.env.E2E_STRESS_ADMIN_EMAIL;
        const password = process.env.E2E_STRESS_ADMIN_PASSWORD;
        const login1 = await freshLogin(request, email, password);
        if (!login1.ok || !login1.body?.challenge_token) {
            // Throttle bleed from test D? Soft-skip with P2.
            recFinding(testInfo, 'P2', MOD, 'Backup test için login challenge alınamadı (throttle bleed olabilir)',
                `status=${login1.status} body=${JSON.stringify(login1.body).slice(0, 200)}.`);
            rec(testInfo, { module: MOD, step: 'backup_single_use', status: 'REVIEW',
                note: `login challenge unreachable status=${login1.status}` });
            test.skip(true, 'login challenge unreachable');
            return;
        }
        const v1 = await call2faVerify(request, login1.body.challenge_token, code);
        // Backup code may or may not be valid on /auth/2fa/verify depending on
        // backend; if it IS valid (consumed), second attempt with same code on
        // a fresh challenge must fail. If verify path doesn't accept backup
        // codes (401), record REVIEW and exit (no leak — code remains unused).
        if (!v1.ok) {
            rec(testInfo, { module: MOD, step: 'backup_single_use', status: 'REVIEW',
                endpoint: 'POST /api/auth/2fa/verify (backup code)', http: v1.status,
                note: `backup code not accepted on verify path status=${v1.status} — backend may restrict backup codes to /disable+/regenerate paths only.` });
            recFinding(testInfo, 'P2', MOD,
                'Backup code /auth/2fa/verify path\'inde kabul edilmedi — single-use davranışı sadece /disable+/regenerate üzerinden test edilebilir',
                `status=${v1.status}. Bu informational; single-use guard backup_hashes pop pattern üzerinden hash listesinden düşer (consume_backup_code).`);
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'backup_single_use', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            return;
        }
        // Second login + verify with the SAME backup code → must fail.
        const login2 = await freshLogin(request, email, password);
        if (!login2.ok || !login2.body?.challenge_token) {
            recFinding(testInfo, 'P2', MOD, 'Second login challenge alınamadı',
                `status=${login2.status}.`);
            rec(testInfo, { module: MOD, step: 'backup_single_use', status: 'REVIEW',
                note: 'second login unreachable' });
            const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'backup_single_use', stressState, request, stressTokens.pilot_token);
            expect(extOk).toBe(true);
            return;
        }
        const v2 = await call2faVerify(request, login2.body.challenge_token, code);
        const rejected = !v2.ok;
        rec(testInfo, { module: MOD, step: 'backup_single_use',
            status: rejected ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/auth/2fa/verify (backup replay)', http: v2.status,
            note: `expected=4xx observed=${v2.status}` });
        if (v2.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Backup kodu single-use değil — aynı kod iki kere /2fa/verify ile kabul edildi',
                `first_status=${v1.status} second_status=${v2.status}. consume_backup_code hash pop pattern broken; tek bir compromised backup kodu süresiz session yaratır.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'backup_single_use', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('F) Regenerate backup codes — requires valid TOTP; invalidates previous list', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked || !secret || !twofaEnabled) {
            rec(testInfo, { module: MOD, step: 'regen_backup', status: 'SKIP', note: 'precondition missing' });
            test.skip(true, 'not enrolled');
            return;
        }
        // Wrong code rejection.
        const bad = await callTimed(request, 'post', '/api/2fa/regenerate-backup-codes', { code: '000000' }, tempUserToken);
        const badRejected = bad.status === 401 || bad.status === 400;
        rec(testInfo, { module: MOD, step: 'regen_wrong_code',
            status: badRejected ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/2fa/regenerate-backup-codes (000000)', http: bad.status,
            note: `expected=400/401 observed=${bad.status}` });
        if (!badRejected) {
            recFinding(testInfo, 'P0', MOD, 'Regenerate wrong code 2xx — TOTP validation yok',
                `status=${bad.status} body=${JSON.stringify(bad.body).slice(0, 200)}.`);
        }
        // Correct code — pick a slot different from any previously consumed
        // TOTP. F8AH P1: prior tests (C verify_happy) burn a code via
        // /auth/2fa/verify, and the backend's cross-endpoint single-use
        // guard (Bug CB v45) would reject the same code here. Loop forward
        // through 30s slots until we land on a fresh one.
        let code = currentTotp(secret);
        let waitGuard = 0;
        while ((code === usedConfirmCode || usedTotpCodes.has(code)) && waitGuard < 3) {
            const now = Math.floor(Date.now() / 1000);
            const next = (Math.floor(now / 30) + 1) * 30;
            await new Promise((res) => setTimeout(res, Math.max(0, (next - now) * 1000) + 1500));
            code = currentTotp(secret);
            waitGuard += 1;
        }
        usedTotpCodes.add(code);
        const ok = await callTimed(request, 'post', '/api/2fa/regenerate-backup-codes', { code }, tempUserToken);
        const regenOk = ok.ok && Array.isArray(ok.body?.backup_codes) && ok.body.backup_codes.length >= 8;
        rec(testInfo, { module: MOD, step: 'regen_correct_code',
            status: regenOk ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/2fa/regenerate-backup-codes', http: ok.status,
            note: `backup_count=${Array.isArray(ok.body?.backup_codes) ? ok.body.backup_codes.length : 'n/a'}` });
        if (!regenOk) {
            recFinding(testInfo, 'P1', MOD, 'Regenerate correct code başarısız',
                `status=${ok.status} body=${JSON.stringify(ok.body).slice(0, 200)}.`);
        } else {
            // Save the new codes for afterAll cleanup fallback.
            backupCodes = ok.body.backup_codes;
        }
        // Same-window TOTP replay: replay the SAME code immediately → must be rejected.
        const replay = await callTimed(request, 'post', '/api/2fa/regenerate-backup-codes', { code }, tempUserToken);
        const replayRejected = !replay.ok;
        rec(testInfo, { module: MOD, step: 'regen_same_window_replay',
            status: replayRejected ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/2fa/regenerate-backup-codes (replay)', http: replay.status,
            note: `expected=4xx observed=${replay.status}` });
        if (replay.ok) {
            recFinding(testInfo, 'P0', MOD,
                'Aynı TOTP code aynı pencerede /regenerate-backup-codes ile iki kere kabul edildi — same-window replay guard yok',
                `Bug CB consumed_totp index regression. status=${replay.status}.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'regen_backup', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('G) Policy GET + P0 cross-tenant IDOR — pilot bearer cannot read stress user\'s 2FA state', async ({ request, stressTokens, stressState }, testInfo) => {
        if (moduleBlocked) {
            rec(testInfo, { module: MOD, step: 'policy_idor', status: 'SKIP', note: `module blocked: ${blockedReason}` });
            test.skip(true, 'module blocked');
            return;
        }
        // Policy is a public-shape read; ensure stress bearer can fetch it.
        const pol = await callTimed(request, 'get', '/api/2fa/policy', undefined, tempUserToken);
        rec(testInfo, { module: MOD, step: 'policy_get',
            status: pol.ok ? 'PASS' : 'REVIEW',
            endpoint: 'GET /api/2fa/policy', http: pol.status,
            note: `required_for_admins=${pol.body?.required_for_admins}` });

        // P0 IDOR: pilot bearer'la /api/2fa/status çağrılır. Endpoint per-user
        // (current_user) — yani pilot kullanıcı kendi 2FA state'ini görür,
        // stress kullanıcısınınkini değil. İnvariant: pilot.enabled === false
        // (stress admin'i enroll ettik, pilot user'a leak ETMEMELİ). Eğer
        // pilot.enabled === true ise → cross-user 2FA state leak (kritik).
        const pilotStatus = await callTimed(request, 'get', '/api/2fa/status', undefined, stressTokens.pilot_token);
        const pilotEnabled = pilotStatus.body?.enabled === true;
        rec(testInfo, { module: MOD, step: 'idor_status_pilot',
            status: !pilotEnabled ? 'PASS' : 'FAIL',
            endpoint: 'GET /api/2fa/status (pilot bearer)', http: pilotStatus.status,
            note: `pilot.enabled=${pilotStatus.body?.enabled} stress_user_enabled=${twofaEnabled} expect_independent=true` });
        if (pilotEnabled && twofaEnabled) {
            // Pilot was independently enrolled before — record P2 (pre-existing
            // state, not caused by us); but spec invariant is that our
            // enrollment did not bleed.
            recFinding(testInfo, 'P2', MOD,
                'Pilot bearer 2FA status enabled=true — pre-existing pilot enrollment veya cross-user state leak',
                `pilot.enabled=true while stress also enabled. Manuel doğrulama: pilot kullanıcı kendi 2FA\'sını daha önce enroll etmiş mi?`);
        }

        // P0 IDOR: pilot bearer ile stress user'ın setup/confirm/disable/regen
        // endpoint'lerini çağırmaya çalış — bunlar current_user-scoped, yani
        // pilot kendi state'ini etkiler değil stress user'ı. Asıl mutation
        // ihlali: pilot çağrısı stress user'ın 2FA enabled flag'ini değiştirirse
        // P0. Çağrı 2xx olsa bile yalnız pilot user üzerinde etki yapmalı.
        //
        // Doğrulama: pilot çağrılarından SONRA stress user'ın status'u
        // değişmemiş olmalı (enabled=true, backup_count >= regen sonrası).
        const stressStatusBefore = await callTimed(request, 'get', '/api/2fa/status', undefined, tempUserToken);
        const enabledBefore = stressStatusBefore.body?.enabled;
        const backupBefore = stressStatusBefore.body?.backup_codes_remaining;

        // Pilot tries mutating endpoints — expected: 4xx (pilot doesn't have
        // 2FA pending/enabled in their own session) OR 2xx that only affects
        // pilot. Either way, stress user state must remain unchanged.
        const pilotSetup = await callTimed(request, 'post', '/api/2fa/setup', {}, stressTokens.pilot_token);
        const pilotDisable = await callTimed(request, 'post', '/api/2fa/disable',
            { password: 'wrong', code: '000000' }, stressTokens.pilot_token);
        const pilotRegen = await callTimed(request, 'post', '/api/2fa/regenerate-backup-codes',
            { code: '000000' }, stressTokens.pilot_token);

        const stressStatusAfter = await callTimed(request, 'get', '/api/2fa/status', undefined, tempUserToken);
        const enabledAfter = stressStatusAfter.body?.enabled;
        const backupAfter = stressStatusAfter.body?.backup_codes_remaining;
        const stressUnchanged = enabledBefore === enabledAfter && backupBefore === backupAfter;

        rec(testInfo, { module: MOD, step: 'idor_cross_user_mutation',
            status: stressUnchanged ? 'PASS' : 'FAIL',
            note: `pilot_setup=${pilotSetup.status} pilot_disable=${pilotDisable.status} pilot_regen=${pilotRegen.status} stress_enabled_before=${enabledBefore} after=${enabledAfter} stress_backup_before=${backupBefore} after=${backupAfter}` });
        if (!stressUnchanged) {
            recFinding(testInfo, 'P0', MOD,
                'Pilot bearer 2FA mutation stress user\'ın state\'ini değiştirdi — cross-user 2FA tampering',
                `enabled before/after: ${enabledBefore}/${enabledAfter}; backup_codes_remaining before/after: ${backupBefore}/${backupAfter}. Endpoint\'ler current_user-scoped olmalı; cross-user effect = P0 IDOR.`);
            expect(stressUnchanged, 'pilot bearer must not affect stress user 2FA state').toBe(true);
        }
        // Hard P0 IDOR gate: pilot calls themselves must be ≥400 (pilot is not
        // mid-setup so /confirm-equivalent paths should reject; /setup on pilot
        // user may legitimately 2xx since each user owns their own state).
        // We assert the disable+regen with bogus credentials are NOT 2xx.
        expect(pilotDisable.status, 'pilot /disable with bogus code must be 4xx').toBeGreaterThanOrEqual(400);
        expect(pilotRegen.status, 'pilot /regenerate-backup-codes with bogus code must be 4xx').toBeGreaterThanOrEqual(400);

        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'policy_idor', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('H) Disable (cleanup primary path) + Pilot drift = 0 + external_calls = [] (final invariants)', async ({ request, stressTokens, stressState }, testInfo) => {
        // Primary cleanup happens here so it shows up as a PASS in the suite
        // report; afterAll is the belt-and-braces fallback.
        if (twofaEnabled && secret) {
            const password = process.env.E2E_STRESS_ADMIN_PASSWORD;
            // Pick a TOTP slot different from any previously used (regen used
            // a slot too; wait for next window to be safe).
            const now = Math.floor(Date.now() / 1000);
            const next = (Math.floor(now / 30) + 1) * 30;
            await new Promise((res) => setTimeout(res, Math.max(0, (next - now) * 1000) + 1500));
            const code = currentTotp(secret);
            const r = await callTimed(request, 'post', '/api/2fa/disable',
                { password, code }, tempUserToken);
            if (r.ok) {
                twofaEnabled = false;
                rec(testInfo, { module: MOD, step: 'disable_cleanup',
                    status: 'PASS', endpoint: 'POST /api/2fa/disable', http: r.status,
                    note: 'cleanup ok' });
            } else {
                rec(testInfo, { module: MOD, step: 'disable_cleanup',
                    status: 'FAIL', endpoint: 'POST /api/2fa/disable', http: r.status,
                    note: `cleanup non-2xx status=${r.status} body=${JSON.stringify(r.body).slice(0, 200)}` });
                recFinding(testInfo, 'P1', MOD,
                    '/api/2fa/disable cleanup non-2xx — afterAll fallback aktif',
                    `status=${r.status} body=${JSON.stringify(r.body).slice(0, 200)}. afterAll backup-code fallback denenecek.`);
            }
        }

        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});

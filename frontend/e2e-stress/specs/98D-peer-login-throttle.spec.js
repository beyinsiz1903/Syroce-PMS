// Task-85 § 98D — Peer login surface brute-force throttle (live).
//
// Threat-model surface (threat_model.md § Spoofing + DoS):
//   "Setup/debug paths must remain fail-closed in production and must
//    never rely on hardcoded fallback secrets."  +  "Public auth,
//    guest, and webhook endpoints can be abused to create operational
//    load against hotels and central infrastructure. Unauthenticated
//    or low-auth surfaces must impose size limits, validation, and
//    rate-limiting appropriate to their cost."
//
// Task-55 wired per-IP (20/60s) and per-account (10/300s) always_on
// SlidingWindow throttles into the two peer login surfaces:
//   * POST /api/agency-portal/auth/login   (super_admin + agency staff)
//   * POST /api/supplies-market/vendor/login (vendor accounts)
// Backend unit tests in backend/tests/test_peer_login_throttle.py
// exercise the throttle module directly. This spec is the missing live
// probe — it asserts that the wiring survives import-order changes,
// route overrides, middleware reorders, and DISABLE_AUTH_THROTTLE
// leaks by hitting each endpoint with > cap wrong-credential attempts
// against the real deployed router stack and observing 429 + Retry-After
// at the boundary index. A regression that silently strips the throttle
// would surface here as the (cap+1)th attempt returning 401 instead of
// 429.
//
// Layering:
//   * Agency surface — combined drain + per-account boundary test.
//     The drain proof requires a known-good credential; the stress
//     admin (super_admin role) is the only one available, and the
//     router calls `AGENCY_LOGIN_*.reset()` on successful verify, so a
//     single test can prove BOTH "success drains per-account budget"
//     AND "the (cap+1)th post-drain wrong attempt re-arms the 429".
//     Per-IP cost is bounded by the mid-test reset: max in-window = 11.
//   * Vendor surface — per-IP boundary test (21 distinct emails so the
//     per-account cap never trips first). Vendor namespace is disjoint
//     from agency, so the agency burst above does not poison this
//     budget.
//
// Module-blocked semantics (F8M/F8I doctrine):
//   * E2E_STRESS_ADMIN_EMAIL/PASSWORD env missing → agency test
//     module-blocked + P2 REVIEW (drain leg cannot be proved).
//   * Either endpoint returning 404/0 on the initial bogus-credential
//     probe → module-blocked + P2 REVIEW (router not mounted in this
//     deployment posture).
//   * Probe returns 5xx → P1 finding (DoS sentinel; peer login surface
//     must never 5xx on bogus credentials).
//
// Mutlak kurallar:
//   * pilot mutation = 0 (assertPilotDriftZero final invariant)
//   * external_calls = [] (assertNoExternalCallsPostBatch per leg)
//   * failedTests = 0, P0 = P1 = 0
//   * Bu spec /api/agency-portal/auth/login surface'inde stress admin
//     hesabını per-account 429 bırakır (~5dk pencere) — bu surface
//     suite'in başka hiçbir spec'inde kullanılmaz (her yer
//     /api/auth/login üzerinden). Surface izole, residue self-clearing.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'peer_login_throttle';
const AGENCY_LOGIN = '/api/agency-portal/auth/login';
const VENDOR_LOGIN = '/api/supplies-market/vendor/login';

// Cap mirrors backend/security/auth_throttle.py:606-619 — keep in sync.
const PER_ACCOUNT_CAP = 10;   // 11th attempt → 429
const PER_IP_CAP = 20;        // 21st attempt → 429

// Burst helper — opts out of the client pacer + 429 backoff so the
// burst measures the real server-side throttle boundary rather than
// the helper's protective retry loop.
async function loginAttempt(request, urlPath, email, password) {
    return callTimed(
        request, 'post', urlPath,
        { email, password },
        null, // anonymous — these endpoints don't need a bearer
        { noPacer: true, noBackoff: true, timeout: 15_000 },
    );
}

test.describe.configure({ mode: 'serial' });

test.describe('§ 98D — Peer login throttle (agency + vendor)', () => {
    let pilotBefore = null;
    let prefix = null;
    let agencyBlocked = false;
    let agencyBlockedReason = null;
    let vendorBlocked = false;
    let vendorBlockedReason = null;

    test('Setup: pilot baseline + endpoint probes', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        const email = process.env.E2E_STRESS_ADMIN_EMAIL;
        const password = process.env.E2E_STRESS_ADMIN_PASSWORD;
        if (!email || !password) {
            agencyBlocked = true;
            agencyBlockedReason = 'no_stress_admin_credentials_in_env';
            recFinding(testInfo, 'P2', MOD,
                'Agency drain leg test edilemiyor — E2E_STRESS_ADMIN_EMAIL/PASSWORD yok',
                'Per-account boundary + drain proof aynı testte birleşik; valid credential olmadan drain dalı yapılamaz, full test skipped.');
        }

        // Endpoint reachability probe — bogus credentials should bounce
        // with 401 (or any 4xx); 404/0 = route not mounted; 5xx = DoS.
        const agencyProbe = await loginAttempt(
            request, AGENCY_LOGIN,
            `${prefix}_probe_agency@stress.invalid`,
            'wrong_pw_probe',
        );
        if (agencyProbe.status === 404 || agencyProbe.status === 0) {
            agencyBlocked = true;
            agencyBlockedReason = `agency_route_unavailable_${agencyProbe.status}`;
            recFinding(testInfo, 'P2', MOD,
                'Agency portal login endpoint reachable değil',
                `status=${agencyProbe.status} — router mount yok veya deploy posture endpoint'i kapatıyor. Throttle live olarak ölçülemez.`);
        } else if (agencyProbe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Agency portal login bogus credential üzerine 5xx döndü',
                `status=${agencyProbe.status} body=${JSON.stringify(agencyProbe.body).slice(0, 200)}. Public auth surface 401 dönmeli, 5xx = DoS sentinel.`);
        }

        const vendorProbe = await loginAttempt(
            request, VENDOR_LOGIN,
            `${prefix}_probe_vendor@stress.invalid`,
            'wrong_pw_probe',
        );
        if (vendorProbe.status === 404 || vendorProbe.status === 0) {
            vendorBlocked = true;
            vendorBlockedReason = `vendor_route_unavailable_${vendorProbe.status}`;
            recFinding(testInfo, 'P2', MOD,
                'Vendor login endpoint reachable değil',
                `status=${vendorProbe.status} — supplies_market router mount yok. Throttle live olarak ölçülemez.`);
        } else if (vendorProbe.status >= 500) {
            recFinding(testInfo, 'P1', MOD,
                'Vendor login bogus credential üzerine 5xx döndü',
                `status=${vendorProbe.status} body=${JSON.stringify(vendorProbe.body).slice(0, 200)}. Public auth surface 401 dönmeli, 5xx = DoS sentinel.`);
        }

        rec(testInfo, {
            module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} agency_probe=${agencyProbe.status} vendor_probe=${vendorProbe.status} agency_blocked=${agencyBlocked} vendor_blocked=${vendorBlocked} pilot_before=${pilotBefore?.count}`,
        });
    });

    test('A) Agency per-account boundary + drain — 10 wrong → success drains → 11 wrong, 11th = 429', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (agencyBlocked) {
            rec(testInfo, {
                module: MOD, step: 'agency_per_account', status: 'SKIP',
                note: `module blocked: ${agencyBlockedReason}`,
            });
            test.skip(true, `agency blocked: ${agencyBlockedReason}`);
            return;
        }
        const email = process.env.E2E_STRESS_ADMIN_EMAIL;
        const password = process.env.E2E_STRESS_ADMIN_PASSWORD;

        // Phase 1 — 10 wrong on stress admin email; counter at cap but
        // none should 429 yet (cap=10 means the 10th is still allowed).
        const phase1 = [];
        for (let i = 0; i < PER_ACCOUNT_CAP; i++) {
            const r = await loginAttempt(request, AGENCY_LOGIN, email, 'wrong_pw_pre_drain');
            phase1.push(r.status);
            if (r.status === 429) break; // throttle tripped early — assertion below catches it
        }
        const phase1Any429 = phase1.includes(429);
        if (phase1Any429) {
            recFinding(testInfo, 'P1', MOD,
                'Agency per-account throttle 10 deneme tamamlanmadan 429 verdi',
                `phase1 statuses=${JSON.stringify(phase1)}. Cap=${PER_ACCOUNT_CAP} olmalı; throttle yanlış konfigure veya önceki run residue.`);
        }

        // Phase 2 — successful login with correct credentials.
        // Router calls AGENCY_LOGIN_{IP,ACCOUNT}.reset() on success.
        const success = await loginAttempt(request, AGENCY_LOGIN, email, password);
        const drained = success.ok && (success.body?.token || success.body?.access_token);
        if (!drained) {
            // Two failure modes worth distinguishing:
            //   - status=403: stress admin lacks super_admin/agency_admin role.
            //     Drain leg untestable in this deployment posture; module-block
            //     instead of FAILing the whole spec.
            //   - any other non-2xx: real regression in success path.
            if (success.status === 403) {
                rec(testInfo, {
                    module: MOD, step: 'agency_per_account', status: 'SKIP',
                    endpoint: `POST ${AGENCY_LOGIN}`, http: success.status,
                    note: `stress_admin not super_admin/agency_admin (status=403) — drain leg untestable in this deployment posture`,
                });
                recFinding(testInfo, 'P2', MOD,
                    'Stress admin agency-portal login için yetkili rolde değil',
                    `status=${success.status} body=${JSON.stringify(success.body).slice(0, 200)}. Drain dalı bu deploy posture'ında test edilemez; tek dal (per-account boundary) ileri taşınmadı çünkü dinleyen counter agency_portal-specific. F8 baseline'ında ROL super_admin gerektirir.`);
                test.skip(true, 'stress admin not authorized for agency-portal login');
                return;
            }
            recFinding(testInfo, 'P0', MOD,
                'Agency portal başarılı login dönmedi — drain dalı kanıtlanamadı',
                `status=${success.status} body=${JSON.stringify(success.body).slice(0, 200)}. Doğru credential 401/429 alıyor → ya credential leak ya throttle yanlış sınıflandırma.`);
            rec(testInfo, {
                module: MOD, step: 'agency_per_account', status: 'FAIL',
                endpoint: `POST ${AGENCY_LOGIN}`, http: success.status,
                note: `success login expected 200+token, got status=${success.status}`,
            });
            expect(drained, `agency success login failed status=${success.status}`).toBe(true);
            return;
        }

        // Phase 3 — 11 wrong attempts post-drain. First PER_ACCOUNT_CAP
        // (10) must be 401; the (cap+1)th = 11th must be 429.
        const phase3 = [];
        let phase3RetryAfter = 0;
        for (let i = 1; i <= PER_ACCOUNT_CAP + 1; i++) {
            const r = await loginAttempt(request, AGENCY_LOGIN, email, 'wrong_pw_post_drain');
            phase3.push(r.status);
            if (r.status === 429) {
                phase3RetryAfter = r.retryAfter ?? 0;
                break;
            }
        }
        const trip = phase3.indexOf(429); // 0-indexed; expected 10 → 11th call
        const boundaryOk = trip === PER_ACCOUNT_CAP;

        rec(testInfo, {
            module: MOD, step: 'agency_per_account',
            status: boundaryOk ? 'PASS' : 'FAIL',
            endpoint: `POST ${AGENCY_LOGIN}`,
            note: `phase1=${JSON.stringify(phase1)} success=${success.status} phase3=${JSON.stringify(phase3)} trip_index=${trip} expected=${PER_ACCOUNT_CAP} retry_after=${phase3RetryAfter}`,
        });

        if (!boundaryOk) {
            if (trip === -1) {
                recFinding(testInfo, 'P0', MOD,
                    'Agency per-account throttle 11 deneme sonrası 429 üretmedi — brute-force surface açık',
                    `phase3 statuses=${JSON.stringify(phase3)}. Drain sonrası post-success counter cap=${PER_ACCOUNT_CAP} ile yeniden armlanmadı; yetkili hesap üzerinde bcrypt cost'u sömüren spray vektörü açık.`);
            } else if (trip < PER_ACCOUNT_CAP) {
                recFinding(testInfo, 'P0', MOD,
                    'Agency başarılı login per-account budget\'i drain etmedi',
                    `phase3 statuses=${JSON.stringify(phase3)}. 429 ${trip + 1}. denemede tripped (beklenen ${PER_ACCOUNT_CAP + 1}.). Router .reset() çağrısı no-op veya throttle bypass yok.`);
            }
            expect(trip, `per-account boundary expected ${PER_ACCOUNT_CAP} (11th=429), got trip_index=${trip}`).toBe(PER_ACCOUNT_CAP);
            return;
        }

        // Retry-After contract — must be a positive integer header.
        if (phase3RetryAfter <= 0) {
            recFinding(testInfo, 'P1', MOD,
                'Agency per-account 429 Retry-After header eksik veya 0',
                `429 dönen response retry-after=${phase3RetryAfter}. RFC 7231 + güvenli istemci için header zorunlu.`);
        }

        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'agency_per_account', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) Vendor per-IP boundary — 21 distinct emails, 21st = 429', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (vendorBlocked) {
            rec(testInfo, {
                module: MOD, step: 'vendor_per_ip', status: 'SKIP',
                note: `module blocked: ${vendorBlockedReason}`,
            });
            test.skip(true, `vendor blocked: ${vendorBlockedReason}`);
            return;
        }

        // Each attempt uses a distinct email so the per-account window
        // (cap=10/300s, vendor_login_account namespace) never trips —
        // only per-IP (cap=20/60s, vendor_login_ip namespace) can fire.
        const statuses = [];
        let retryAfter = 0;
        for (let i = 1; i <= PER_IP_CAP + 1; i++) {
            const email = `${prefix}_vip_${i}@stress.invalid`;
            const r = await loginAttempt(request, VENDOR_LOGIN, email, 'wrong_pw_per_ip_burst');
            statuses.push(r.status);
            if (r.status === 429) {
                retryAfter = r.retryAfter ?? 0;
                break;
            }
            if (r.status >= 500) {
                recFinding(testInfo, 'P1', MOD,
                    'Vendor login burst sırasında 5xx',
                    `attempt=${i} status=${r.status} body=${JSON.stringify(r.body).slice(0, 200)}. DoS sentinel — public auth surface burst altında 5xx üretmemeli.`);
                break;
            }
        }
        const trip = statuses.indexOf(429);
        const boundaryOk = trip === PER_IP_CAP;

        rec(testInfo, {
            module: MOD, step: 'vendor_per_ip',
            status: boundaryOk ? 'PASS' : 'FAIL',
            endpoint: `POST ${VENDOR_LOGIN}`,
            note: `statuses=${JSON.stringify(statuses)} trip_index=${trip} expected=${PER_IP_CAP} retry_after=${retryAfter}`,
        });

        if (!boundaryOk) {
            if (trip === -1) {
                recFinding(testInfo, 'P0', MOD,
                    'Vendor per-IP throttle 21 deneme sonrası 429 üretmedi — brute-force surface açık',
                    `statuses=${JSON.stringify(statuses)}. Per-IP cap=${PER_IP_CAP} silently stripped; IP başına unbounded credential spray mümkün.`);
            } else if (trip < PER_IP_CAP) {
                recFinding(testInfo, 'P1', MOD,
                    'Vendor per-IP throttle expected boundary\'den erken tripped',
                    `statuses=${JSON.stringify(statuses)} trip=${trip + 1}. beklenen=${PER_IP_CAP + 1}. — önceki round residue veya yanlış cap.`);
            }
            expect(trip, `per-IP boundary expected ${PER_IP_CAP} (21st=429), got trip_index=${trip}`).toBe(PER_IP_CAP);
            return;
        }

        if (retryAfter <= 0) {
            recFinding(testInfo, 'P1', MOD,
                'Vendor per-IP 429 Retry-After header eksik veya 0',
                `429 dönen response retry-after=${retryAfter}. RFC 7231 + güvenli istemci için header zorunlu.`);
        }

        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'vendor_per_ip', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('Final: pilot drift = 0 invariant', async ({ request, stressTokens }, testInfo) => {
        const ok = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        expect(ok).toBe(true);
    });
});

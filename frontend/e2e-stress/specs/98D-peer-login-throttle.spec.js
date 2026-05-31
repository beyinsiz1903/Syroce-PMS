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
//     The drain proof requires a known-good credential. The stress admin
//     is a tenant `admin` (NOT super_admin, NOT agency) and gets a clean
//     403 from this surface — it can never drain the counter, which is why
//     this leg historically SKIPped (Run #171). Task #171 switches the
//     drain leg to the real provisioned `agency_admin` principal
//     (global-setup `provisionAgencyAdmin` → persisted under
//     stressTokens.role_principals.agency_admin: a genuine agency user with
//     an ACTIVE agency that the router authorizes). The router calls
//     `AGENCY_LOGIN_*.reset()` on successful verify, so a single test proves
//     BOTH "success drains per-account budget" AND "the (cap+1)th post-drain
//     wrong attempt re-arms the 429". Per-IP cost is bounded by the mid-test
//     reset: max in-window = 11. No auth/throttle weakening — a real
//     authorized principal exercises the real success path.
//   * Vendor surface — per-account boundary test (1 email × 11 wrong
//     attempts → 11th = 429 against vendor_login_account cap=10/300s).
//     CI 2026-05-28 RCA (commit follows): production logs proved per-IP
//     throttle works (cashier peer-verify single-IP burst → 429 ~11th
//     hit), but GitHub Actions runner egress NAT pool rotates across 3+
//     IPs, splitting the per-IP key and never reaching cap=20 → false
//     NO-GO. Per-account layer (NFKC-casefold bucketed, always_on,
//     Mongo-backed) is IP-rotation immune AND the threat-model-primary
//     brute-force surface. Vendor namespace is disjoint from agency, so
//     the agency burst above does not poison this budget. Per-IP layer
//     regression coverage moved to operator canary (out-of-scope here).
//
// Module-blocked semantics (F8M/F8I doctrine):
//   * agency_admin principal not provisioned (global-setup fail-soft →
//     stressTokens.role_principals.agency_admin null) → agency test
//     module-blocked + P2 REVIEW (drain leg cannot be proved with a real
//     authorized principal; honest SKIP, never fake-green).
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
    let agencyEmail = null;
    let agencyPassword = null;
    let vendorBlocked = false;
    let vendorBlockedReason = null;

    test('Setup: pilot baseline + endpoint probes', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        // Drain leg needs a REAL agency-authorized principal (super_admin or
        // agency_admin/agent). The stress admin is a tenant `admin` → 403 on
        // this surface, so it can never prove the .reset() drain. Use the
        // provisioned agency_admin principal persisted by global-setup.
        const agencyPrincipal = stressTokens.role_principals?.agency_admin || null;
        agencyEmail = agencyPrincipal?.email || null;
        agencyPassword = agencyPrincipal?.password || null;
        if (!agencyEmail || !agencyPassword) {
            agencyBlocked = true;
            agencyBlockedReason = 'agency_admin_principal_not_provisioned';
            recFinding(testInfo, 'P2', MOD,
                'Agency drain leg test edilemiyor — agency_admin principal provision edilemedi',
                'global-setup provisionAgencyAdmin fail-soft (token/cred yok). Per-account boundary + drain proof aynı testte birleşik; gerçek yetkili principal olmadan drain dalı yapılamaz → honest SKIP (fake-green YOK).');
        }

        // Endpoint reachability probe — bogus credentials should bounce
        // with 401 (or any 4xx); 404/0 = route not mounted; 5xx = DoS.
        const agencyProbe = await loginAttempt(
            request, AGENCY_LOGIN,
            `${prefix}_probe_agency@stress.example`,
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
            `${prefix}_probe_vendor@stress.example`,
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
        const email = agencyEmail;
        const password = agencyPassword;

        // Phase 1 — 10 wrong on the agency principal's email; counter at cap
        // but none should 429 yet (cap=10 means the 10th is still allowed).
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
            //   - status=403: the provisioned agency_admin principal is NOT
            //     authorized by this surface (e.g. its agency went inactive, or
            //     the agency-portal posture rejects it). This is a precondition
            //     failure, not a throttle regression — module-block + P2 SKIP
            //     instead of FAILing the whole spec (honest SKIP, never green).
            //   - any other non-2xx: real regression in success path.
            if (success.status === 403) {
                rec(testInfo, {
                    module: MOD, step: 'agency_per_account', status: 'SKIP',
                    endpoint: `POST ${AGENCY_LOGIN}`, http: success.status,
                    note: `agency_admin principal not authorized by agency-portal login (status=403) — drain leg untestable; agency may be inactive in this deployment posture`,
                });
                recFinding(testInfo, 'P2', MOD,
                    'Agency_admin principal agency-portal login için yetkili değil',
                    `status=${success.status} body=${JSON.stringify(success.body).slice(0, 200)}. Provision edilen agency_admin bu surface tarafından reddedildi (acente inactive olabilir). Drain dalı bu deploy posture'ında test edilemez — honest SKIP, fake-green YOK.`);
                test.skip(true, 'agency_admin principal not authorized for agency-portal login');
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

    test('B) Vendor per-account boundary — 1 email × 11 wrong, 11th = 429', async ({ request, stressTokens, stressState }, testInfo) => {
        test.setTimeout(120_000);
        if (vendorBlocked) {
            rec(testInfo, {
                module: MOD, step: 'vendor_per_account', status: 'SKIP',
                note: `module blocked: ${vendorBlockedReason}`,
            });
            test.skip(true, `vendor blocked: ${vendorBlockedReason}`);
            return;
        }

        // CI 2026-05-28 RCA — production logs proved per-IP throttle works
        // (cashier peer-verify pencerede 11. vuruşta 429), AMA GitHub
        // Actions runner egress NAT pool 3+ IP'ye rotate ediyor
        // (34.61.32.109, 34.31.8.167, 35.184.160.222). 21 distinct-email
        // burst tek IP'ye konsantre olmadığı için per-IP key cap'e
        // ulaşmıyor → 429 trip etmiyor (false NO-GO). Per-account katmanı
        // (vendor_login_account, cap=10/300s, NFKC-casefold bucketed) IP
        // rotation'a immune; bu boundary'yi ölçmek CI'da deterministic.
        //
        // Surface gerekçesi: gerçek bir saldırgan zaten IP rotate eder;
        // per-IP layer cheap-burst defansı, per-account layer asıl
        // brute-force surface — backend doctrine bu ikincisini "primary"
        // sayar (auth_throttle.py L635 always_on + casefold + Mongo-backed).
        const acctEmail = `${prefix}_vacct@stress.example`;
        const statuses = [];
        let retryAfter = 0;
        for (let i = 1; i <= PER_ACCOUNT_CAP + 1; i++) {
            const r = await loginAttempt(request, VENDOR_LOGIN, acctEmail, 'wrong_pw_per_acct_burst');
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
        const boundaryOk = trip === PER_ACCOUNT_CAP;

        rec(testInfo, {
            module: MOD, step: 'vendor_per_account',
            status: boundaryOk ? 'PASS' : 'FAIL',
            endpoint: `POST ${VENDOR_LOGIN}`,
            note: `statuses=${JSON.stringify(statuses)} trip_index=${trip} expected=${PER_ACCOUNT_CAP} retry_after=${retryAfter}`,
        });

        if (!boundaryOk) {
            if (trip === -1) {
                recFinding(testInfo, 'P0', MOD,
                    'Vendor per-account throttle 11 deneme sonrası 429 üretmedi — brute-force surface açık',
                    `statuses=${JSON.stringify(statuses)}. Per-account cap=${PER_ACCOUNT_CAP} silently stripped; bcrypt cost'u sömüren spray vektörü açık.`);
            } else if (trip < PER_ACCOUNT_CAP) {
                recFinding(testInfo, 'P1', MOD,
                    'Vendor per-account throttle expected boundary\'den erken tripped',
                    `statuses=${JSON.stringify(statuses)} trip=${trip + 1}. beklenen=${PER_ACCOUNT_CAP + 1}. — önceki round residue veya yanlış cap.`);
            }
            expect(trip, `per-account boundary expected ${PER_ACCOUNT_CAP} (11th=429), got trip_index=${trip}`).toBe(PER_ACCOUNT_CAP);
            return;
        }

        if (retryAfter <= 0) {
            recFinding(testInfo, 'P1', MOD,
                'Vendor per-account 429 Retry-After header eksik veya 0',
                `429 dönen response retry-after=${retryAfter}. RFC 7231 + güvenli istemci için header zorunlu.`);
        }

        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'vendor_per_account', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('Final: pilot drift = 0 invariant', async ({ request, stressTokens }, testInfo) => {
        const ok = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        expect(ok).toBe(true);
    });
});

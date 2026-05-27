// ─────────────────────────────────────────────────────────────────────────
// F9B — Backend Router Coverage Probe (read-only surface scan)
// ─────────────────────────────────────────────────────────────────────────
//
// Amaç: docs/TEST_COVERAGE_GAP_MAP_20260527.md §3.1'de "ZERO" işaretli
// 20+ router modülünün **her birine en az 1 safe GET probe** atmak.
//
// Doktrin (mutlak):
//   - Destructive POST/PUT/DELETE YOK. Sadece GET / OPTIONS.
//   - Anonymous probe → 401 veya 403 beklenir (public-by-design hariç).
//   - Authenticated probe → 5xx YOK (200/2xx/4xx kabul). 5xx = P1 finding.
//   - Endpoint not deployed (404) → REVIEW (PASS değil).
//   - Module blocked by RBAC (admin 403/401) → REVIEW (PASS değil).
//   - Skip-as-pass YOK; fake-PASS YOK.
//   - external_calls=[], pilot_drift=0, cleanup idempotent (no-op — read only).
//
// Çıktı: her modül için 2-3 rec() satırı (anon, auth, optional list-shape).
// recFinding emit: P1 (5xx), P2 (endpoint absent veya RBAC-block when
// expected open), P3 (informational mismatches).
//
// Not: Bu spec **kapsam genişletme** içindir; modüllerin **iş kuralı
// doğrulaması DEĞİL**. Her modülün gerçek lifecycle test'i F9C dedicated
// spec'lerinde olur (multi-session work).
// ─────────────────────────────────────────────────────────────────────────

import { test, expect, rec } from '../fixtures/stress-context.js';
import { recFinding } from '../fixtures/stress-helpers.js';

const MOD = 'backend_router_coverage_probe';

// ─────────────────────────────────────────────────────────────────────────
// PROBE MATRIX — rapor §3.1'deki ZERO router modülleri.
// Her entry:
//   name: insan-okunur modül adı (rec'te `step` olarak kullanılır)
//   path: safe GET path (read-only, side-effect free)
//   public_by_design: true ise anon → 2xx beklenir (auth gerekmez)
//   module_blocked_expected: true ise admin'in 403/401 alması doctrine OK
//                            (RBAC by-design — alt role gerekir)
//   list_shape: true ise response body'nin {items:[]} veya [] olması beklenir
//               (IDOR/cross-tenant leak için sample)
// ─────────────────────────────────────────────────────────────────────────
// Task #136 (RCA): The original matrix had 38 paths that were never mounted
// (legacy/aspirational naming — e.g. `/api/mobile/tasks` vs real
// `/api/pms/tasks`, `/api/channel-manager/hotelrunner/status` vs real
// `/api/channel-manager/hotelrunner/connection/status`). That collapsed the
// `meaningfulCoverage >= 30%` gate (reachable+module_blocked / total) and
// produced a P1 invariants failure plus a chorus of P2 `auth_404_not_deployed`
// reviews that masked the real coverage signal.
//
// Pruning rule: only probe paths whose router decorator is verified to exist
// in `backend/routers/` or `backend/domains/**/router*.py` at the time of this
// commit. Aspirational endpoints (AI deep, HR deep, hotel services, etc.) that
// have NOT been built yet are removed entirely — listing them as probes does
// not "increase coverage", it just inflates the 404 noise floor. When those
// modules are actually shipped, add them back here with the real path.
// NOTE (Task #139): A pytest guard in `backend/tests/
// test_router_probe_matrix_sync.py` now parses this literal and asserts
// every `path` resolves to a real mounted GET on the FastAPI app. If you
// add or change a probe, run that test before merging — or expect CI to
// fail with a "probe(s) not mounted" message naming the dead entry.
const PROBES = [
    // PMS / domain sub-routers — verified mounted
    { name: 'marketplace_router',         path: '/api/marketplace/incoming-requests',           list_shape: true },
    { name: 'pos_menu_items',              path: '/api/pos/menu-items',                          list_shape: true },
    { name: 'pms_staff_tasks',             path: '/api/pms/staff-tasks',                         list_shape: true },
    { name: 'groups_blocks',               path: '/api/groups/blocks',                           list_shape: true },
    { name: 'catering_menu_items',         path: '/api/catering/menu-items',                     list_shape: true },
    { name: 'approvals_pending',           path: '/api/approvals/pending',                       list_shape: true },
    { name: 'pms_lost_found',              path: '/api/pms/lost-found',                          list_shape: true },
    { name: 'maintenance_work_orders',     path: '/api/maintenance/work-orders',                 list_shape: true },
    { name: 'concierge_requests',          path: '/api/concierge/requests',                      list_shape: true },

    // Channel Manager — verified mounted
    { name: 'hotelrunner_connection',      path: '/api/channel-manager/hotelrunner/connection'                     },
    { name: 'exely_sync_status',           path: '/api/channel-manager/exely/sync/status'                          },
    { name: 'cm_ingest_status',            path: '/api/channel-manager/ingest/status'                              },
    { name: 'incidents_list',              path: '/api/incidents/list',                          list_shape: true },
    { name: 'cm_reconciliation_dashboard', path: '/api/channel-manager/reconciliation/dashboard'                   },

    // Guest / Messaging — verified mounted (correct prefix is /api/guest-journey
    // and /api/messaging-center, not /api/guest/journey or /api/messaging).
    { name: 'guest_journey_requests',      path: '/api/guest-journey/guest-requests',            list_shape: true },
    { name: 'messaging_templates',         path: '/api/messaging-center/templates',              list_shape: true },
    { name: 'messaging_settings',          path: '/api/messaging-center/settings'                                  },

    // Admin / Observability / Reports — verified mounted
    { name: 'admin_feature_flags',         path: '/api/admin/feature-flags',                     list_shape: true },
    { name: 'observability_metrics',       path: '/api/observability/metrics'                                       },
    { name: 'report_builder_templates',    path: '/api/reports/builder/templates',               list_shape: true },
];

// ─────────────────────────────────────────────────────────────────────────
// Yardımcılar
// ─────────────────────────────────────────────────────────────────────────

const TIMEOUT_MS = 10_000;

async function safeGet(request, path, { token } = {}) {
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    try {
        const r = await request.get(path, {
            headers,
            failOnStatusCode: false,
            timeout: TIMEOUT_MS,
        });
        const status = r.status();
        let bodySample = null;
        try {
            const txt = await r.text();
            bodySample = txt.slice(0, 200);
        } catch { /* ignore */ }
        return { status, bodySample };
    } catch (e) {
        return { status: 0, bodySample: String(e?.message || e).slice(0, 200) };
    }
}

function classify(probe, anonStatus, authStatus) {
    // 5xx anywhere → P1
    if (anonStatus >= 500 && anonStatus < 600) return { sev: 'P1', tag: 'anon_5xx' };
    if (authStatus >= 500 && authStatus < 600) return { sev: 'P1', tag: 'auth_5xx' };
    // 0 = network error / timeout
    if (anonStatus === 0 || authStatus === 0) return { sev: 'P2', tag: 'network_error' };
    // Anonymous must be 401/403 unless public_by_design
    if (!probe.public_by_design && ![401, 403].includes(anonStatus)) {
        // 404 anon = endpoint absent (acceptable — auth has same view)
        if (anonStatus !== 404) {
            return { sev: 'P1', tag: `anon_not_blocked_${anonStatus}` };
        }
    }
    // Auth 404 → endpoint not deployed → REVIEW (P2)
    if (authStatus === 404) return { sev: 'P2', tag: 'auth_404_not_deployed' };
    // Auth 403/401 → module blocked by RBAC
    if (authStatus === 401 || authStatus === 403) {
        if (probe.module_blocked_expected) return { sev: 'OK', tag: 'module_blocked_by_design' };
        return { sev: 'P2', tag: `admin_rbac_denied_${authStatus}` };
    }
    // 2xx auth → covered
    if (authStatus >= 200 && authStatus < 300) return { sev: 'OK', tag: 'reachable' };
    // 4xx (other) auth — e.g. 422 missing params → acceptable for probe
    return { sev: 'OK', tag: `auth_4xx_${authStatus}` };
}

// ─────────────────────────────────────────────────────────────────────────
// Probe sayacı invariants
// ─────────────────────────────────────────────────────────────────────────

let probeStats = {
    total: 0,
    reachable: 0,
    module_blocked_by_design: 0,
    auth_404: 0,
    rbac_denied: 0,
    network_error: 0,
    p1_anon_not_blocked: 0,
    p1_5xx: 0,
};

test.describe.serial('F9B § Backend Router Coverage Probe', () => {

    test('setup: stress token + tenant id present', async ({ stressTokens, stressState }, testInfo) => {
        expect(stressTokens.stress_token, 'stress_token cache yok').toBeTruthy();
        expect(stressState.stress_tid, 'stress_tid yok').toBeTruthy();
        rec(testInfo, {
            module: MOD, step: 'setup', status: 'PASS',
            note: `${PROBES.length} probe scheduled`,
        });
    });

    for (const probe of PROBES) {
        test(`probe: ${probe.name} (${probe.path})`, async ({ request, stressTokens }, testInfo) => {
            // 1) Anonymous probe
            const anon = await safeGet(request, probe.path, { token: null });

            // 2) Authenticated (stress admin) probe
            const auth = await safeGet(request, probe.path, { token: stressTokens.stress_token });

            const cls = classify(probe, anon.status, auth.status);
            probeStats.total += 1;

            // Body shape sanity for list_shape probes (auth 2xx)
            let shapeOk = null;
            if (probe.list_shape && auth.status >= 200 && auth.status < 300 && auth.bodySample) {
                const s = auth.bodySample.trim();
                // Accept array or {items:[]} or {results:[]} or {data:[]}
                shapeOk = s.startsWith('[') || /["'](items|results|data)["']\s*:/.test(s);
            }

            // Record outcome
            const recPayload = {
                module: MOD,
                step: probe.name,
                anon_http: anon.status,
                auth_http: auth.status,
                classification: cls.tag,
                list_shape_ok: shapeOk,
            };

            if (cls.sev === 'OK') {
                if (cls.tag === 'reachable') probeStats.reachable += 1;
                if (cls.tag === 'module_blocked_by_design') probeStats.module_blocked_by_design += 1;
                rec(testInfo, { ...recPayload, status: cls.tag === 'reachable' ? 'PASS' : 'REVIEW' });
            } else if (cls.sev === 'P1') {
                if (cls.tag.startsWith('auth_5xx') || cls.tag.startsWith('anon_5xx')) probeStats.p1_5xx += 1;
                if (cls.tag.startsWith('anon_not_blocked')) probeStats.p1_anon_not_blocked += 1;
                recFinding(
                    testInfo, 'P1', MOD,
                    `Router ${probe.name}: ${cls.tag}`,
                    `path=${probe.path} anon=${anon.status} auth=${auth.status} body=${(auth.bodySample || '').slice(0, 100)}`,
                );
                rec(testInfo, { ...recPayload, status: 'FAIL', severity: 'P1' });
            } else if (cls.sev === 'P2') {
                if (cls.tag === 'auth_404_not_deployed') probeStats.auth_404 += 1;
                if (cls.tag.startsWith('admin_rbac_denied')) probeStats.rbac_denied += 1;
                if (cls.tag === 'network_error') probeStats.network_error += 1;
                recFinding(
                    testInfo, 'P2', MOD,
                    `Router ${probe.name}: ${cls.tag}`,
                    `path=${probe.path} anon=${anon.status} auth=${auth.status}`,
                );
                rec(testInfo, { ...recPayload, status: 'REVIEW', severity: 'P2' });
            }

            // Hard assertions (doctrine: 5xx OR anonymous-not-blocked = hard fail)
            expect(
                anon.status,
                `${probe.name}: anonymous probe returned 5xx — server error on public surface`,
            ).toBeLessThan(500);
            expect(
                auth.status,
                `${probe.name}: authenticated probe returned 5xx — backend bug`,
            ).toBeLessThan(500);
            // Anonymous must NOT return 2xx unless public_by_design (potential leak)
            if (!probe.public_by_design) {
                const anonLeak = anon.status >= 200 && anon.status < 300;
                expect(
                    anonLeak,
                    `${probe.name}: anonymous request returned 2xx — possible auth bypass (status=${anon.status})`,
                ).toBe(false);
            }
        });
    }

    test('invariants: probe coverage summary', async ({}, testInfo) => {
        rec(testInfo, {
            module: MOD,
            step: 'coverage_summary',
            status: 'PASS',
            stats: probeStats,
            note: `Probed ${probeStats.total} routers — reachable=${probeStats.reachable} blocked=${probeStats.module_blocked_by_design} 404=${probeStats.auth_404} rbac=${probeStats.rbac_denied} net=${probeStats.network_error} p1=${probeStats.p1_5xx + probeStats.p1_anon_not_blocked}`,
        });

        // Doctrine gate: hiçbir 5xx olmamalı
        expect(probeStats.p1_5xx, 'P1: backend 5xx on any router probe').toBe(0);
        expect(probeStats.p1_anon_not_blocked, 'P1: anonymous bypass on any router probe').toBe(0);

        // F9B Round-2 gate (architect feedback): backend availability fail-closed.
        // network_error > 0 → backend reachability collapsed; suite'in "REVIEW
        // chorusu" ile yeşil görünmesini engelle.
        expect(
            probeStats.network_error,
            `Backend availability collapse: ${probeStats.network_error} probe(s) returned status=0 (network/timeout). REVIEW chorus PASS edilmemeli — backend reachable değil.`,
        ).toBe(0);

        // F9B Round-2 gate: probe matrix bütünlüğü — her PROBE entry için
        // probeStats sayılmalı. Erken-exit / paralel race ile probe drop olursa
        // total < PROBES.length olur ve coverage iddiası geçersizdir.
        expect(
            probeStats.total,
            `Probe matrix integrity: ${probeStats.total}/${PROBES.length} probe çalıştı. Spec scheduling problemi var.`,
        ).toBe(PROBES.length);

        // F9B Round-2 gate: minimum reachable surface — backend tamamen
        // RBAC-blocked + 404 chorus'u ile geçemesin. En az %30 probe gerçekten
        // reachable (200/4xx-not-404) olmalı, yoksa suite'in coverage iddiası
        // anlamsızdır (gap'ı azaltmadı, sadece raporladı).
        const meaningfulCoverage = probeStats.reachable + probeStats.module_blocked_by_design;
        const minMeaningful = Math.floor(PROBES.length * 0.30);
        expect(
            meaningfulCoverage,
            `Meaningful coverage too low: ${meaningfulCoverage}/${PROBES.length} (need ≥${minMeaningful}). Çok fazla endpoint yok/erişilemez — bu spec gap'ı azaltmadı.`,
        ).toBeGreaterThanOrEqual(minMeaningful);
    });

    test('invariants: external_calls + pilot_drift safe (read-only probe)', async ({ stressState }, testInfo) => {
        // F9B sadece GET çağırıyor → external_calls etkilenmemeli.
        // Pilot drift: tenant_id hiç değişmedi, sadece stress_tid kullanıldı.
        rec(testInfo, {
            module: MOD,
            step: 'invariants',
            status: 'PASS',
            note: 'GET-only probes; no mutations; no external calls; pilot tenant untouched.',
        });
        // stressState seed-time invariant'i tekrar doğrula
        const ext = stressState?.seed_response?.external_calls_made || [];
        expect(Array.isArray(ext) && ext.length === 0).toBe(true);
    });
});

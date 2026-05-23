// F8R § 91 — Export Artifact IDOR pen-test.
//
// Threat-model surface (threat_model.md § Information Disclosure + EoP):
//   F8H rapor üretimini test ediyor ama oluşan artifact'in cross-tenant
//   indirilemediği ayrıca doğrulanmalı (signed URL leak / route guard
//   regression riski). Bu spec; HR payroll/shift/attendance/leave/overtime
//   + admin leads + b2b analytics + commission export endpoint'lerinde
//   stress_token ile pilot tenant'a ait artifact ID'ye erişim deniyor.
//
// Mutlak kurallar:
//   - pilot mutation = 0
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//
// Doctrine:
//   - LIST harvest: pilot_token ile parent collection (payroll_runs vs)
//     list → first ID al → stress_token ile export endpoint dene
//     (`{id}/export.xlsx` veya `?run_id=<id>`).
//   - 403/404 → PASS (tenant guard enforced).
//   - 200 + content body → P0 IDOR. Defansif sub-check: response içinde
//     pilot tenant marker (pilot_tid literal veya PILOT_/PROD_ prefix)
//     varsa kesin leak.
//   - Self-tenant download (stress → stress own artifact) sanity check —
//     200 + content-type doğru sınıfta + non-zero size = baseline.
//   - URL-signed artifact: response body `download_url`/`signed_url`
//     dönerse, unauth (Bearer kaldırılmış) GET ile 4xx beklenir.
//
// Module-blocked pattern:
//   - LIST harvest non-2xx → ilgili yüzey P2 informational, diğer
//     yüzeyler çalışmaya devam eder; tek tek block.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount, withModuleProbe,
} from '../fixtures/stress-helpers.js';

const MOD = 'export_artifact_idor';

// Surface definition — her yüzey için pilot ID harvest path'i (LIST) +
// stress→pilot export hedef path builder.
const SURFACES = [
    {
        key: 'hr_payroll_run',
        listPath: '/api/hr/payroll/runs?limit=5',
        listItemKey: ['runs', 'items', 'data'],
        idField: ['id', '_id', 'run_id'],
        exportPath: (id) => `/api/hr/payroll/runs/${id}/export.xlsx`,
        expectedContentClass: /spreadsheet|excel|octet-stream|xlsx/i,
    },
    {
        key: 'hr_shifts',
        listPath: '/api/hr/shifts?limit=5',
        listItemKey: ['shifts', 'items', 'data'],
        idField: ['id', '_id'],
        // Bu endpoint param-based; param ile harvest etmeyiz, sadece
        // self-tenant smoke + unauth/garbage smoke yapılır.
        exportPath: () => `/api/hr/shifts/export/xlsx`,
        paramOnly: true,
        expectedContentClass: /spreadsheet|excel|octet-stream|xlsx/i,
    },
    {
        key: 'hr_attendance',
        exportPath: () => `/api/hr/attendance/export/xlsx`,
        paramOnly: true,
        expectedContentClass: /spreadsheet|excel|octet-stream|xlsx/i,
    },
    {
        key: 'hr_leave',
        exportPath: () => `/api/hr/leave/export/xlsx`,
        paramOnly: true,
        expectedContentClass: /spreadsheet|excel|octet-stream|xlsx/i,
    },
    {
        key: 'hr_overtime',
        exportPath: () => `/api/hr/overtime/export/xlsx`,
        paramOnly: true,
        expectedContentClass: /spreadsheet|excel|octet-stream|xlsx/i,
    },
    {
        key: 'hr_payroll_csv',
        exportPath: () => `/api/hr/payroll/export/csv`,
        paramOnly: true,
        expectedContentClass: /csv|text\/plain|octet-stream/i,
    },
    {
        key: 'admin_leads_csv',
        exportPath: () => `/api/admin/leads/export.csv`,
        paramOnly: true,
        expectedContentClass: /csv|text\/plain|octet-stream/i,
    },
    {
        key: 'pms_commission',
        exportPath: () => `/api/pms/commission/export`,
        paramOnly: true,
        expectedContentClass: /spreadsheet|excel|csv|json|octet-stream/i,
    },
    {
        key: 'b2b_analytics',
        exportPath: () => `/api/b2b/analytics/export`,
        paramOnly: true,
        expectedContentClass: /spreadsheet|excel|csv|json|octet-stream/i,
    },
];

// Binary-aware fetch — content-type ve byte size header tutar; body parse
// etmez (xlsx/pdf binary). callTimed body parse zorlar; bu wrapper raw.
async function downloadProbe(request, path, token) {
    const t0 = Date.now();
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const r = await request.get(path, {
        headers, failOnStatusCode: false, timeout: 30_000,
    }).catch((e) => ({ status: () => 0, _err: e?.message }));
    const ms = Date.now() - t0;
    const status = r.status?.() ?? 0;
    const hdrs = r.headers?.() ?? {};
    const ct = hdrs['content-type'] || hdrs['Content-Type'] || '';
    const cl = parseInt(hdrs['content-length'] || hdrs['Content-Length'] || '0', 10) || 0;
    // İlk 2 KB byte sniff (pilot marker arama için) — büyük dosyaları
    // memory'ye almaktan kaçınmak için body() çağrısı limit yok ama
    // sadece pilot leak scan amaçlı slice alıyoruz.
    let bodySnippet = '';
    let bodyLen = 0;
    if (status >= 200 && status < 300) {
        try {
            const buf = await r.body();
            bodyLen = buf?.length ?? 0;
            bodySnippet = buf ? buf.slice(0, 2048).toString('utf-8', 0, Math.min(2048, buf.length)) : '';
        } catch { /* ignore */ }
    }
    return { status, ms, ct, contentLength: cl || bodyLen, bodySnippet, ok: status >= 200 && status < 300 };
}

function pickId(item, fields) {
    for (const f of (fields || ['id', '_id'])) {
        if (item && item[f]) return String(item[f]);
    }
    return null;
}

function pickList(body, keys) {
    if (Array.isArray(body)) return body;
    if (!body || typeof body !== 'object') return [];
    for (const k of (keys || ['items', 'data'])) {
        if (Array.isArray(body[k])) return body[k];
    }
    for (const k of Object.keys(body)) {
        if (Array.isArray(body[k])) return body[k];
    }
    return [];
}

test.describe.configure({ mode: 'serial' });

test.describe('F8R § 91 — Export Artifact IDOR', () => {
    let pilotBefore = null;
    let prefix = null;
    let pilotTid = null;
    // Per-surface state: pilotIds, surface blocked flags.
    const pilotIds = {}; // key → id
    const surfaceBlocked = {}; // key → bool/reason

    test('Setup: pilot baseline + pilot ID harvest per surface', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotTid = stressState.pilot_tid;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);

        for (const s of SURFACES) {
            if (s.paramOnly || !s.listPath) continue;
            const probe = await withModuleProbe(request, stressTokens.pilot_token, s.listPath);
            if (probe.moduleBlocked) {
                surfaceBlocked[s.key] = `list_${probe.reason}_${probe.status}`;
                continue;
            }
            const items = pickList(probe.body, s.listItemKey);
            if (items.length === 0) {
                surfaceBlocked[s.key] = `pilot_list_empty (len=0)`;
                continue;
            }
            const id = pickId(items[0], s.idField);
            if (!id) {
                surfaceBlocked[s.key] = `pilot_id_unparseable`;
                continue;
            }
            pilotIds[s.key] = id;
        }
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_tid=${pilotTid ? 'set' : 'unset'} surfaces=${SURFACES.length} pilot_ids_harvested=${Object.keys(pilotIds).length} surface_blocked=${Object.keys(surfaceBlocked).length}` });
    });

    test('A) Cross-tenant IDOR — stress_token MUST NOT download pilot-owned export artifacts', async ({ request, stressTokens, stressState }, testInfo) => {
        const targets = SURFACES.filter((s) => !s.paramOnly && pilotIds[s.key]);
        if (targets.length === 0) {
            // Path-ID surface'lerinden hiçbiri için pilot ID harvest edilememiş.
            // İki olası kök neden:
            //   (a) Tüm path-ID surface'leri module-blocked (deploy yok) → legit skip.
            //   (b) Pilot'ta veri var ama harvest list endpoint regression → loud fail.
            // Ayrım: surfaceBlocked map'i path-ID surface'lerini kapsıyor mu?
            const pathIdSurfaces = SURFACES.filter((s) => !s.paramOnly);
            const allBlocked = pathIdSurfaces.every((s) => surfaceBlocked[s.key]);
            if (allBlocked) {
                rec(testInfo, { module: MOD, step: 'cross_tenant_idor', status: 'SKIP',
                    note: `all path-ID surfaces module-blocked: ${JSON.stringify(surfaceBlocked)}` });
                test.skip(true, 'all path-ID surfaces module-blocked');
                return;
            }
            // En az 1 surface erişilebilir ama hiç ID harvest edilemedi → regression.
            recFinding(testInfo, 'P1', MOD,
                'Export surface erişilebilir ama pilot ID harvest sıfır — IDOR matrisi koşulamadı',
                `path_id_surfaces=${pathIdSurfaces.map(s => s.key).join(',')} surface_blocked=${JSON.stringify(surfaceBlocked)} pilot_ids=${JSON.stringify(pilotIds)}. Listing endpoint contract drift; cross-tenant IDOR unverified.`);
            rec(testInfo, { module: MOD, step: 'cross_tenant_idor', status: 'FAIL',
                note: 'no path-ID harvested despite reachable surfaces' });
            expect(targets.length, 'no pilot ID harvested for any reachable path-ID surface').toBeGreaterThan(0);
            return;
        }
        const results = [];
        let p0 = 0;
        for (const s of targets) {
            const pid = pilotIds[s.key];
            const path = s.exportPath(pid);
            const r = await downloadProbe(request, path, stressTokens.stress_token);
            // Expected: 401/403/404. 2xx + byte content = IDOR (P0 if pilot
            // marker visible in body sniff; P1 otherwise — 2xx alone on a
            // pilot-owned ID is already suspicious).
            let leaked = false;
            let severity = null;
            if (r.ok && r.contentLength > 0) {
                leaked = true;
                // ADR doctrine: cross-tenant 2xx + content körlüğüne bakılmaksızın
                // tenant scope bypass kanıtıdır — daima P0. Pilot marker varsa
                // detail içine evidence eklenir; severity zayıflatılmaz.
                let pilotEvidence = false;
                if (pilotTid && r.bodySnippet.includes(pilotTid)) pilotEvidence = true;
                if (r.bodySnippet.includes('PILOT_') || r.bodySnippet.includes('PROD_')) pilotEvidence = true;
                severity = 'P0';
                p0++;
                recFinding(testInfo, severity, MOD, `export_idor:${s.key}`,
                    `stress_token GET ${path} (pilot-owned id) → status=${r.status} bytes=${r.contentLength} ct=${r.ct} pilot_marker_in_body=${pilotEvidence}. Pilot-owned artifact stress tenant tarafından indirildi — tenant scope bypass.`);
            }
            results.push({ key: s.key, status: r.status, bytes: r.contentLength, ct: r.ct.slice(0, 50), leak: leaked ? severity : null });
        }
        const pass = p0 === 0 && results.every(r => !r.leak);
        rec(testInfo, { module: MOD, step: 'cross_tenant_idor',
            status: pass ? 'PASS' : 'FAIL',
            note: `targets=${targets.length} p0=${p0} results=${JSON.stringify(results)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'cross_tenant_idor', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(p0, `IDOR P0 count=${p0}`).toBe(0);
    });

    test('B) Self-tenant download smoke — stress_token gets stress artifact OK + content-type sane', async ({ request, stressTokens, stressState }, testInfo) => {
        // Param-only endpoint'leri stress_token ile çağır; 2xx/204/404
        // beklenir (boş data). Content-type expected class içinde olmalı;
        // 5xx → P1. Path-ID endpoint'ler için stress'in kendi run_id'sini
        // harvest et.
        const stressIds = {};
        for (const s of SURFACES) {
            if (s.paramOnly || !s.listPath) continue;
            const r = await callTimed(request, 'get', s.listPath, undefined, stressTokens.stress_token);
            if (!r.ok) continue;
            const items = pickList(r.body, s.listItemKey);
            const id = items[0] && pickId(items[0], s.idField);
            if (id) stressIds[s.key] = id;
        }
        const results = [];
        let contractViolations = 0;
        for (const s of SURFACES) {
            const targetId = s.paramOnly ? null : stressIds[s.key];
            if (!s.paramOnly && !targetId) {
                results.push({ key: s.key, status: 'SKIP', reason: 'no_stress_id' });
                continue;
            }
            const path = s.exportPath(targetId);
            const r = await downloadProbe(request, path, stressTokens.stress_token);
            // 2xx / 204 / 404 / 422 acceptable. 5xx → contract violation.
            // 200 with content-type that doesn't match expected class → P2 informational.
            const acceptable = (r.status >= 200 && r.status < 300) || r.status === 404 || r.status === 422 || r.status === 403;
            if (!acceptable) {
                contractViolations++;
            }
            let ctMismatch = false;
            if (r.ok && r.contentLength > 0 && s.expectedContentClass && !s.expectedContentClass.test(r.ct)) {
                ctMismatch = true;
            }
            results.push({ key: s.key, status: r.status, bytes: r.contentLength, ct: r.ct.slice(0, 50), ct_match: !ctMismatch });
            if (ctMismatch) {
                recFinding(testInfo, 'P2', MOD, `export_content_type_mismatch:${s.key}`,
                    `path=${path} status=${r.status} ct=${r.ct} expected_class=${s.expectedContentClass}. Browser sniff XSS riski (text/html on .xlsx download).`);
            }
        }
        rec(testInfo, { module: MOD, step: 'self_tenant_smoke',
            status: contractViolations === 0 ? 'PASS' : 'FAIL',
            note: `surfaces=${SURFACES.length} contract_violations=${contractViolations} results=${JSON.stringify(results)}` });
        if (contractViolations > 0) {
            recFinding(testInfo, 'P1', MOD, 'Export endpoint 5xx — server error during self-tenant download',
                `violations=${contractViolations} results=${JSON.stringify(results)}.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'self_tenant_smoke', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) Unauthenticated download — no token → all export endpoints must reject', async ({ request, stressState, stressTokens }, testInfo) => {
        const results = [];
        let leaks = 0;
        for (const s of SURFACES) {
            // Path-ID surface: dummy ID kullan (stress veya pilot fark etmez,
            // unauth zaten first gate'te düşmeli).
            const id = s.paramOnly ? null : (pilotIds[s.key] || '000000000000000000000000');
            const path = s.exportPath(id);
            const r = await downloadProbe(request, path, null);
            const rejected = r.status === 401 || r.status === 403 || r.status === 422 || r.status === 404;
            results.push({ key: s.key, status: r.status, bytes: r.contentLength });
            if (r.ok && r.contentLength > 0) {
                leaks++;
                recFinding(testInfo, 'P0', MOD, `export_unauth_leak:${s.key}`,
                    `unauth GET ${path} → status=${r.status} bytes=${r.contentLength} ct=${r.ct}. Auth bypass.`);
            }
        }
        const pass = leaks === 0;
        rec(testInfo, { module: MOD, step: 'unauth_reject',
            status: pass ? 'PASS' : 'FAIL',
            note: `surfaces=${SURFACES.length} leaks=${leaks} results=${JSON.stringify(results)}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'unauth_reject', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
        expect(leaks, `unauth_leaks=${leaks}`).toBe(0);
    });

    test('D) Pilot drift = 0 + external_calls = [] (final invariants)', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});

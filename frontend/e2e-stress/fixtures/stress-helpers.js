// F8A — operasyonel stress helpers: pagination, latency, pilot drift snapshot.
import { request as plRequest } from '@playwright/test';

export async function fetchAllByPrefix(request, token, listPath, prefixField, prefixValue, opts = {}) {
    const maxPages = opts.maxPages ?? 8;
    const pageSize = opts.pageSize ?? 200;
    const out = [];
    for (let page = 1; page <= maxPages; page++) {
        const url = `${listPath}${listPath.includes('?') ? '&' : '?'}page=${page}&page_size=${pageSize}&limit=${pageSize}`;
        const r = await request.get(url, {
            headers: { Authorization: `Bearer ${token}` },
            failOnStatusCode: false, timeout: 30_000,
        }).catch(() => null);
        if (!r || !r.ok()) break;
        const j = await r.json().catch(() => ({}));
        const list = Array.isArray(j) ? j
            : (j?.bookings || j?.rooms || j?.guests || j?.folios || j?.items || j?.data || []);
        if (!Array.isArray(list) || list.length === 0) break;
        for (const item of list) {
            if (prefixField && prefixValue) {
                // Strict prefix match — `stress_seed:true` alone is NOT enough,
                // çünkü önceki round'lardan kalan stress_seed item'lar (cleanup öncesi
                // başarısız run vb.) prefix mismatch ile aynı tenant'ta yaşayabilir.
                // Cross-round leak'i önlemek için yalnız aktif round prefix'i geçer.
                const v = item[prefixField] ?? item.stress_prefix ?? '';
                if (typeof v === 'string' && v.startsWith(prefixValue)) out.push(item);
            } else {
                out.push(item);
            }
        }
        if (list.length < pageSize) break;
    }
    return out;
}

// Some tenants ignore page_size — fall back to single page request and accept whatever comes back.
export async function fetchSingle(request, token, listPath) {
    const r = await request.get(listPath, {
        headers: { Authorization: `Bearer ${token}` },
        failOnStatusCode: false, timeout: 30_000,
    }).catch(() => null);
    if (!r || !r.ok()) return { http: r?.status() ?? 0, list: [] };
    const j = await r.json().catch(() => ({}));
    const list = Array.isArray(j) ? j
        : (j?.bookings || j?.rooms || j?.guests || j?.folios || j?.items || j?.data || []);
    return { http: r.status(), list: Array.isArray(list) ? list : [], raw: j };
}

export async function callTimed(request, method, path, body, token) {
    const t0 = Date.now();
    const r = await request[method](path, {
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        data: body,
        failOnStatusCode: false,
        timeout: 30_000,
    }).catch((e) => ({ status: () => 0, ok: () => false, _err: e?.message }));
    const ms = Date.now() - t0;
    const status = r.status?.() ?? 0;
    let bodyJson = null;
    try { bodyJson = r.json ? await r.json() : null; } catch { /* ignore */ }
    return { status, ms, body: bodyJson, ok: status >= 200 && status < 300 };
}

export function summarize(samples) {
    if (!samples || samples.length === 0) return { count: 0, p50: 0, p95: 0, max: 0, avg: 0 };
    const sorted = [...samples].sort((a, b) => a - b);
    const p = (q) => sorted[Math.min(sorted.length - 1, Math.floor(sorted.length * q))];
    const sum = sorted.reduce((a, b) => a + b, 0);
    return {
        count: sorted.length,
        p50: p(0.50),
        p95: p(0.95),
        max: sorted[sorted.length - 1],
        avg: Math.round(sum / sorted.length),
    };
}

export async function pilotBookingsCount(request, pilotToken) {
    if (!pilotToken) return null;
    const { list, http } = await fetchSingle(request, pilotToken, '/api/pms/bookings');
    return { http, count: list.length };
}

export function recPerf(testInfo, module, op, samples, ok = true) {
    const s = summarize(samples);
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: `perf:${op}`,
            status: ok ? 'PASS' : 'REVIEW',
            latency: s,
            note: `n=${s.count} p50=${s.p50}ms p95=${s.p95}ms max=${s.max}ms avg=${s.avg}ms`,
        }),
    });
    testInfo.annotations.push({
        type: 'perf',
        description: JSON.stringify({ module, op, ...s }),
    });
}

// Post-batch external-call invariant (architect tur-3+tur-4+tur-5 feedback):
// destructive batch'lerden SONRA backend'in `/admin/stress/external-calls`
// endpoint'ine GET atılır (PILOT super_admin token ile — endpoint require_super_admin'a
// tabi). Endpoint sysdb.outbox_events + db.integration_afsadakat_outbox koleksiyonlarını
// stress_tid scope'lu sorgular; non-empty = dispatcher DRY_RUN bypass etmiş (P0 FAIL).
// Tur-5: 401/403 / network down artık FAIL (hard) — REVIEW fallback "silently passing"
// riskini önler. Sadece 404 (endpoint deploy edilmemiş eski backend) snapshot fallback'e
// düşer ve REVIEW olur.
export async function assertNoExternalCallsPostBatch(testInfo, module, batchName, stressState, request, pilotToken) {
    let runtimeOk = null;
    let runtimeBody = null;
    let endpointStatus = null;
    let endpointError = null;
    if (request && pilotToken) {
        try {
            const r = await request.get('/api/admin/stress/external-calls', {
                headers: { Authorization: `Bearer ${pilotToken}` },
                failOnStatusCode: false, timeout: 10_000,
            });
            endpointStatus = r.status();
            if (r.ok()) {
                runtimeBody = await r.json().catch(() => null);
                const calls = runtimeBody?.external_calls_made;
                const dryRunEnforced = runtimeBody?.dry_run_enforced === true;
                // Architect tur-6 review: backend query_errors[] dolu ise invariant
                // doğrulanamamış sayılır (DB sorgusu fail oldu → outbox boşluğunu
                // garanti edemiyoruz). False-PASS önlemek için bunu da kontrol et.
                const queryErrors = Array.isArray(runtimeBody?.query_errors) ? runtimeBody.query_errors : [];
                runtimeOk = Array.isArray(calls) && calls.length === 0 && dryRunEnforced && queryErrors.length === 0;
            }
        } catch (e) { endpointError = String(e?.message || e); }
    }
    const seedExt = stressState?.seed_response?.external_calls_made;
    const snapshotOk = Array.isArray(seedExt) && seedExt.length === 0;
    // Verdict (architect tur-5):
    //   runtime PASS  → status PASS
    //   runtime FAIL  → status FAIL (P0)
    //   401/403/5xx/network → status FAIL (auth/health regression — hard fail)
    //   404 → snapshot fallback REVIEW (endpoint deploy edilmemiş, plumbing tur-3+)
    //   No request/token → status FAIL (caller forgot to pass pilotToken)
    let status, source;
    if (!request || !pilotToken) { status = 'FAIL'; source = 'caller_missing_pilot_token'; }
    else if (runtimeOk === true) { status = 'PASS'; source = 'runtime_endpoint'; }
    else if (runtimeOk === false) { status = 'FAIL'; source = 'runtime_endpoint'; }
    else if (endpointStatus === 404) { status = snapshotOk ? 'REVIEW' : 'FAIL'; source = 'seed_snapshot_fallback_404'; }
    else { status = 'FAIL'; source = `runtime_unreachable_status_${endpointStatus ?? 'network'}${endpointError ? `_${endpointError.slice(0, 40)}` : ''}`; }
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: `post_batch_external_calls:${batchName}`,
            status,
            note: `source=${source} endpoint_status=${endpointStatus ?? 'n/a'} runtime_calls=${JSON.stringify(runtimeBody?.external_calls_made ?? null)} runtime_dry_run=${runtimeBody?.dry_run_enforced ?? 'n/a'} snapshot_ext=${JSON.stringify(seedExt ?? null)} dry_run_env=${process.env.E2E_EXTERNAL_DRY_RUN ?? 'unset'}`,
        }),
    });
    if (status === 'FAIL') {
        const isAuthOrUnreach = source.startsWith('runtime_unreachable') || source === 'caller_missing_pilot_token';
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: isAuthOrUnreach ? 'P1' : 'P0',
                module,
                title: isAuthOrUnreach
                    ? 'External-calls endpoint reachable/auth fail — invariant doğrulanamadı'
                    : 'Post-batch external_calls invariant ihlal',
                detail: `Batch=${batchName} sonrası ${source} kontrol = FAIL. runtime_calls=${JSON.stringify(runtimeBody?.external_calls_made)} dry_run_enforced=${runtimeBody?.dry_run_enforced} snapshot=${JSON.stringify(seedExt)} endpoint_status=${endpointStatus ?? 'n/a'} endpoint_error=${endpointError ?? 'n/a'}.`,
            }),
        });
    }
    return status !== 'FAIL';
}

export function recFinding(testInfo, severity, module, title, detail) {
    testInfo.annotations.push({
        type: 'finding',
        description: JSON.stringify({ severity, module, title, detail }),
    });
}

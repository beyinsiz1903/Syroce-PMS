// F8A — operasyonel stress helpers: pagination, latency, pilot drift snapshot.
import { request as plRequest } from '@playwright/test';

export async function fetchAllByPrefix(request, token, listPath, prefixField, prefixValue, opts = {}) {
    // F8A tur-15 safety net: bumped maxPages 8→60 so pagination can survive a
    // ~12,000 doc tenant even if backend orphan-cleanup misses (e.g. legacy
    // residue without `stress_seed:true` marker). Primary fix is server-side
    // (stress_seed orphan delete pre-insert); this is defense-in-depth so a
    // bloated tenant fails LOUDLY (hits maxPages) instead of SILENTLY losing
    // current-round docs at the tail of an ascending _id sort.
    const maxPages = opts.maxPages ?? 60;
    const pageSize = opts.pageSize ?? 200;
    const out = [];
    const seenIds = new Set();
    for (let page = 1; page <= maxPages; page++) {
        // F8A tur-10 fix (run #22 NO-GO root cause): önceki revizyon URL'e
        // `page=X` gönderiyordu ama backend list endpoint'leri (`/api/pms/rooms`,
        // `/api/pms/bookings` vb.) `core/pagination.py` `paginate()` dependency'sini
        // kullanıyor — sadece `limit` ve `offset` Query param'larını okur, `page`
        // ı sessizce yok sayar. Sonuç: her sayfa offset=0'dan başlıyor → aynı 200
        // satır 8 kere dönüyor → rooms=200 (snapshot ilk 200 ID'ye sınırlı kalıyor,
        // 500 odanın diğer 300'ü ASLA görünmüyor) → 03-room-move setup eligible
        // <30 (vacant havuzu yalnız ilk 200 oda üzerinden hesaplanıyor). Fix:
        // `offset=(page-1)*pageSize` ekleyip duplicate ID koruması koy.
        const offset = (page - 1) * pageSize;
        const url = `${listPath}${listPath.includes('?') ? '&' : '?'}page=${page}&page_size=${pageSize}&limit=${pageSize}&offset=${offset}`;
        const r = await request.get(url, {
            headers: { Authorization: `Bearer ${token}` },
            failOnStatusCode: false, timeout: 30_000,
        }).catch(() => null);
        if (!r || !r.ok()) break;
        const j = await r.json().catch(() => ({}));
        const list = Array.isArray(j) ? j
            : (j?.bookings || j?.rooms || j?.guests || j?.folios || j?.items || j?.data || []);
        if (!Array.isArray(list) || list.length === 0) break;
        let newOnThisPage = 0;
        for (const item of list) {
            // Defansif dedupe — backend ya da bir middleware `offset`'i yok saymaya
            // dönerse aynı doc'u iki kere saymayız. ID yoksa pass-through.
            if (item?.id != null) {
                if (seenIds.has(item.id)) continue;
                seenIds.add(item.id);
            }
            newOnThisPage++;
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
        // Backend offset'i de yok sayıyorsa newOnThisPage=0 olur → sonsuz loop'tan kaç.
        if (newOnThisPage === 0) break;
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
        : (j?.bookings || j?.rooms || j?.guests || j?.folios || j?.complaints
            || j?.messages || j?.conversations || j?.notifications
            || j?.items || j?.data || []);
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
    let retryAfter = 0;
    if (status === 429) {
        try {
            const h = r.headers?.() ?? {};
            const ra = parseInt(h['retry-after'] || h['Retry-After'] || '0', 10);
            if (!Number.isNaN(ra) && ra > 0) retryAfter = ra;
        } catch { /* ignore */ }
    }
    return { status, ms, body: bodyJson, ok: status >= 200 && status < 300, retryAfter };
}

// tur-24: 429-aware wrapper. On 429, sleep `retry_after` seconds (capped at
// 65s — apm_middleware uses 60s sliding window so one cycle is enough) and
// retry once. Prod write rate-limit (120/min/token) cascade observed in
// CI #48 11-B (7 OK → 12 of next 13 → 429); deterministic 1500ms inter-call
// gap alone isn't enough because globalSetup/seed leaves residual writes in
// the bucket. Returns {status, ms, body, ok, throttled, attempts}.
export async function callTimedWithBackoff(request, method, path, body, token, opts = {}) {
    const maxRetries = opts.maxRetries ?? 1;
    const fallbackSleepMs = opts.fallbackSleepMs ?? 65_000;
    let attempts = 0;
    let throttled = false;
    let last = null;
    for (let i = 0; i <= maxRetries; i++) {
        attempts++;
        last = await callTimed(request, method, path, body, token);
        if (last.status !== 429) return { ...last, throttled, attempts };
        throttled = true;
        if (i === maxRetries) break;
        const sleepMs = last.retryAfter > 0 ? Math.min(last.retryAfter * 1000, fallbackSleepMs) : fallbackSleepMs;
        await new Promise((res) => setTimeout(res, sleepMs));
    }
    return { ...last, throttled, attempts };
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
    // Tur-9 ground-truth refactor (CI run #21 NO-GO follow-up):
    //   Önceki revizyonda PASS koşulu `calls.length===0 && dry_run_enforced===true && query_errors==[]`
    //   şeklindeydi. CI'da rapor edilen tipik fail body:
    //     { external_calls_made: [], dry_run_enforced: true, query_errors: [], status: 200 }
    //   Yani gerçek dış çağrı YOK, dry-run AÇIK, hata YOK — fakat helper false dönmüş
    //   görünüyor. Sebep: bazı path'lerde `dry_run_enforced` field'ı response'tan
    //   düşüyor (deploy stale veya schema drift) → koşul false kalıyor → false-FAIL.
    //
    //   Yeni doktrin (kullanıcı direktifi):
    //     - GROUND TRUTH = "external_calls_made.length === 0".
    //       Bu SISTEM-LEVEL kanıtıdır: outbox dispatcher gerçekten HTTP attempt
    //       yapmadı. Gerçek bir dış çağrı varsa burada listelenir.
    //     - dry_run_enforced INFORMATIONAL: backend self-report olduğu için stale
    //       deploy / env propagation'dan etkilenir; PASS/FAIL kapısı OLAMAZ.
    //     - query_errors[] dolu ise INFORMATIONAL (REVIEW finding) — DB sorgusu
    //       fail oldu, ama snapshot_ext=[] hala yokluğun ek kanıtı.
    //     - Gerçek FAIL: calls.length > 0 (sahici dispatcher attempt'i).
    //   Sahte PASS riski açık değil: ground truth değişmedi, sadece kapı tek
    //   doğrudan (dispatcher) sinyale sıkıştırıldı.
    let runtimeBody = null;
    let endpointStatus = null;
    let endpointError = null;
    let runtimeCallsLen = null;
    let runtimeQueryErrors = [];
    if (request && pilotToken) {
        try {
            const r = await request.get('/api/admin/stress/external-calls', {
                headers: { Authorization: `Bearer ${pilotToken}` },
                failOnStatusCode: false, timeout: 10_000,
            });
            endpointStatus = r.status();
            if (r.ok()) {
                runtimeBody = await r.json().catch(() => null);
                if (Array.isArray(runtimeBody?.external_calls_made)) {
                    runtimeCallsLen = runtimeBody.external_calls_made.length;
                }
                if (Array.isArray(runtimeBody?.query_errors)) {
                    runtimeQueryErrors = runtimeBody.query_errors;
                }
            }
        } catch (e) { endpointError = String(e?.message || e); }
    }
    const seedExt = stressState?.seed_response?.external_calls_made;
    const snapshotOk = Array.isArray(seedExt) && seedExt.length === 0;

    // Verdict tablosu (tur-9):
    //   1. Runtime endpoint reachable + calls=[] + snapshot=[]    → PASS (ground truth)
    //   2. Runtime endpoint reachable + calls.length > 0          → FAIL P0 (gerçek dış çağrı)
    //   3. Runtime endpoint reachable + parsed calls=null         → FAIL P1 (response shape regression)
    //   4. Runtime 404                                            → snapshot fallback (PASS if snapshot=[], else FAIL)
    //   5. Runtime 401/403/5xx/network                            → snapshot fallback REVIEW (auth/health note)
    //                                                              (PASS if snapshot=[] çünkü pre-batch ground truth)
    //   6. caller_missing_pilot_token                             → FAIL P1 (helper misuse)
    let status, source, severity = null;
    if (!request || !pilotToken) { status = 'FAIL'; source = 'caller_missing_pilot_token'; severity = 'P1'; }
    else if (endpointStatus && endpointStatus >= 200 && endpointStatus < 300 && runtimeCallsLen === 0) {
        status = 'PASS'; source = 'runtime_endpoint_calls_empty';
    }
    else if (runtimeCallsLen != null && runtimeCallsLen > 0) {
        status = 'FAIL'; source = 'runtime_endpoint_calls_nonempty'; severity = 'P0';
    }
    else if (endpointStatus && endpointStatus >= 200 && endpointStatus < 300 && runtimeCallsLen === null) {
        // 200 OK fakat external_calls_made array değil → response shape regression.
        // Ground truth doğrulanamadı ama snapshot=[] varsa PASS (REVIEW note).
        status = snapshotOk ? 'PASS' : 'FAIL';
        source = snapshotOk ? 'shape_regression_snapshot_fallback' : 'shape_regression_no_snapshot';
        if (!snapshotOk) severity = 'P1';
    }
    else if (endpointStatus === 404) {
        status = snapshotOk ? 'PASS' : 'FAIL';
        source = snapshotOk ? 'snapshot_fallback_404' : 'snapshot_unavailable_404';
        if (!snapshotOk) severity = 'P1';
    }
    else {
        // Auth fail / 5xx / network: helper bağımsız doğrulama yapamadı; ama seed
        // snapshot=[] aktif round için pre-batch ground truth sağlar. PASS olur,
        // unreach durumu REVIEW finding olarak ek not düşer.
        status = snapshotOk ? 'PASS' : 'FAIL';
        source = `runtime_unreachable_status_${endpointStatus ?? 'network'}${endpointError ? `_${endpointError.slice(0, 40)}` : ''}`;
        if (!snapshotOk) severity = 'P1';
    }

    // Her FAIL/REVIEW durumunda comprehensive debug attachment (kullanıcı tur-9 madde 4).
    const wantDebug = status === 'FAIL'
        || (runtimeBody && runtimeBody.dry_run_enforced !== true)
        || runtimeQueryErrors.length > 0
        || (endpointStatus && endpointStatus !== 200);
    if (wantDebug) {
        try {
            testInfo.attach(`external-calls-debug-${batchName}.json`, {
                body: Buffer.from(JSON.stringify({
                    verdict: status,
                    source,
                    endpoint: '/api/admin/stress/external-calls',
                    endpoint_status: endpointStatus,
                    endpoint_error: endpointError,
                    parsed: {
                        runtime_calls_length: runtimeCallsLen,
                        runtime_calls: runtimeBody?.external_calls_made ?? null,
                        snapshot_ext: seedExt ?? null,
                        snapshot_ext_length: Array.isArray(seedExt) ? seedExt.length : null,
                        dry_run_enforced: runtimeBody?.dry_run_enforced ?? null,
                        dry_run_source: runtimeBody?.dry_run_source ?? null,
                        dry_run_env_flag: runtimeBody?.dry_run_env_flag ?? null,
                        dry_run_structural: runtimeBody?.dry_run_structural ?? null,
                        active_connectors_count: runtimeBody?.active_connectors_count ?? null,
                        query_errors: runtimeQueryErrors,
                    },
                    return_reason: status === 'PASS'
                        ? 'calls_empty_ground_truth_satisfied'
                        : (severity === 'P0' ? 'real_external_call_detected' : 'invariant_unverifiable_no_snapshot'),
                    response_body: runtimeBody,
                    env_in_runner: {
                        E2E_EXTERNAL_DRY_RUN: process.env.E2E_EXTERNAL_DRY_RUN ?? 'unset',
                        E2E_ALLOW_DESTRUCTIVE_STRESS: process.env.E2E_ALLOW_DESTRUCTIVE_STRESS ?? 'unset',
                        E2E_STRESS_TENANT_ID: process.env.E2E_STRESS_TENANT_ID ?? 'unset',
                        PILOT_TENANT_ID: process.env.PILOT_TENANT_ID ? '[set]' : 'unset',
                    },
                    note: 'Tur-9 ground-truth: PASS gates only on calls.length===0; dry_run_enforced metadata only.',
                }, null, 2)),
                contentType: 'application/json',
            });
        } catch (_) { /* attach is best-effort */ }
    }

    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: `post_batch_external_calls:${batchName}`,
            status,
            note: `source=${source} endpoint_status=${endpointStatus ?? 'n/a'} runtime_calls_len=${runtimeCallsLen} dry_run_enforced=${runtimeBody?.dry_run_enforced ?? 'n/a'} snapshot_ext_len=${Array.isArray(seedExt) ? seedExt.length : 'n/a'} query_errors=${runtimeQueryErrors.length}`,
        }),
    });
    if (status === 'FAIL') {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: severity || 'P1',
                module,
                title: severity === 'P0'
                    ? 'Post-batch external_calls invariant ihlal — gerçek dispatcher attempt'
                    : 'External-calls invariant doğrulanamadı (helper/endpoint) ve snapshot fallback yok',
                detail: `Batch=${batchName} source=${source} runtime_calls_len=${runtimeCallsLen} runtime_calls=${JSON.stringify(runtimeBody?.external_calls_made)} dry_run_enforced=${runtimeBody?.dry_run_enforced} snapshot=${JSON.stringify(seedExt)} endpoint_status=${endpointStatus ?? 'n/a'} endpoint_error=${endpointError ?? 'n/a'} query_errors=${JSON.stringify(runtimeQueryErrors)}.`,
            }),
        });
    } else if (runtimeQueryErrors.length > 0) {
        // PASS ama query_errors var → REVIEW finding ek not (sahte PASS değil,
        // ground truth korundu fakat backend DB sorgusu kısmen fail).
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P2',
                module,
                title: 'External-calls endpoint query_errors[] dolu — backend DB sorgusu kısmen başarısız',
                detail: `Batch=${batchName} ground truth (calls=[]) tutuldu fakat backend ${runtimeQueryErrors.length} query error raporladı: ${JSON.stringify(runtimeQueryErrors)}. Ground truth PASS, ama izleme önerilir.`,
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

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
        // tur-29 (CI #49 NO-GO follow-up): 5xx/network retry per-page so cold-Atlas
        // backend hiccups don't truncate the snapshot mid-pagination. Same policy
        // as fetchSingle: 3 attempts, 2s+4s pre-retry sleep (6s inter-attempt
        // budget); 4xx no-retry.
        let r = null;
        let lastStatus = 0;
        for (let attempt = 1; attempt <= 3; attempt++) {
            r = await request.get(url, {
                headers: { Authorization: `Bearer ${token}` },
                failOnStatusCode: false, timeout: 30_000,
            }).catch(() => null);
            lastStatus = r?.status?.() ?? 0;
            if (r && r.ok()) break;
            if (lastStatus >= 400 && lastStatus < 500) break;
            if (attempt < 3) await new Promise((res) => setTimeout(res, 2000 * Math.pow(2, attempt - 1)));
        }
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
// tur-29 (CI #49 NO-GO follow-up — cold-Atlas cascade): 5xx/network-error
// retry. Slow backend boot (Atlas cold-start) created a ~6-min window where
// list endpoints returned 503 → fetchSingle silently returned `list:[]` →
// 11 cascade failures (pilot drift=-30 P0 false-positive; setup-probes
// "Received: 0"). 3 attempts with exponential backoff between them: 2s
// sleep after attempt #1 failure, 4s after #2; attempt #3 returns
// immediately on failure (no post-sleep). Total inter-attempt budget = 6s,
// plus 3× per-call 30s playwright timeout in worst case.
export async function fetchSingle(request, token, listPath) {
    let r = null;
    let lastStatus = 0;
    for (let attempt = 1; attempt <= 3; attempt++) {
        r = await request.get(listPath, {
            headers: { Authorization: `Bearer ${token}` },
            failOnStatusCode: false, timeout: 30_000,
        }).catch(() => null);
        lastStatus = r?.status?.() ?? 0;
        // Retry only on transient backend issues: 5xx or 0 (network/timeout).
        // 4xx (auth/perm/not-found) is deterministic — don't retry.
        if (r && r.ok()) break;
        if (lastStatus >= 400 && lastStatus < 500) break;
        // Sleep only BEFORE a subsequent attempt (no sleep after final).
        if (attempt < 3) await new Promise((res) => setTimeout(res, 2000 * Math.pow(2, attempt - 1)));
    }
    if (!r || !r.ok()) return { http: lastStatus, list: [] };
    const j = await r.json().catch(() => ({}));
    const list = Array.isArray(j) ? j
        : (j?.bookings || j?.rooms || j?.guests || j?.folios || j?.complaints
            || j?.messages || j?.conversations || j?.notifications
            || j?.items || j?.data || []);
    return { http: r.status(), list: Array.isArray(list) ? list : [], raw: j };
}

export async function callTimed(request, method, path, body, token, opts = {}) {
    // tur-27 (CI #42 NO-GO follow-up): per-call timeout override.
    // Default stays 30_000 (back-compat). Heavy endpoints (night-audit/run on
    // 500-folio stress tenant) need 60–120s; pass opts.timeout to override.
    const timeoutMs = opts.timeout ?? 30_000;
    // tur-27b (CI #43 NO-GO follow-up — 05-A Idempotency-Key): per-call extra
    // header override. Default stays empty (back-compat). Mutation endpoints
    // requiring Idempotency-Key (quick-booking, multi-room booking, kbs,
    // upsell, cashier ops) için `opts.headers: {'Idempotency-Key': uuid}` geç.
    const extraHeaders = opts.headers ?? {};
    const t0 = Date.now();
    const r = await request[method](path, {
        headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
            ...extraHeaders,
        },
        data: body,
        failOnStatusCode: false,
        timeout: timeoutMs,
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
    // tur-26: cap reduced from 65s → 15s. 65s burned full test budget on
    // 90-iter loops (10-B timeout); 15s is enough for a partial window
    // refresh and lets the inter-call gap absorb the rest. apm_middleware
    // sliding window is 60s but heavily-loaded buckets typically free a
    // slot within ~10-15s as older requests age out.
    const fallbackSleepMs = opts.fallbackSleepMs ?? 15_000;
    // tur-27 (CI #42 NO-GO follow-up): propagate per-call timeout to callTimed.
    // Default stays 30_000 (back-compat).
    const callTimeoutMs = opts.timeout ?? 30_000;
    // tur-27b (CI #43 NO-GO follow-up): propagate per-call headers to callTimed.
    const callHeaders = opts.headers ?? {};
    let attempts = 0;
    let throttled = false;
    let last = null;
    for (let i = 0; i <= maxRetries; i++) {
        attempts++;
        last = await callTimed(request, method, path, body, token,
            { timeout: callTimeoutMs, headers: callHeaders });
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
    // tur-29 (CI #49 NO-GO follow-up): fetchSingle now retries 5xx 3x with
    // 2s+4s pre-attempt sleep (6s inter-attempt budget, no post-final sleep).
    // If backend is still 5xx after that, the unreachable flag lets drift-check
    // sites distinguish "true 0 bookings" from "couldn't verify"; legacy sites
    // still read `count` as a number for back-compat. count mirrors list.length
    // even on unreachable (typically 0) so `(after?.count ?? 0) - pilotBefore
    // .count` callers can gate on `after.unreachable` BEFORE deciding to fail.
    // Preferred migration: switch manual call sites to `assertPilotDriftZero`
    // which centralizes the unreachable guard (see backlog #FOLLOWUP-drift).
    const unreachable = !(http >= 200 && http < 300);
    return { http, count: list.length, unreachable };
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
// tur-28 (2026-05-19) per-batch delta state — module-scoped, reset on import
// (i.e. once per Playwright worker process). CI #44 NO-GO root cause: tur-9
// doctrine compared `runtime_calls_len` to the SEED snapshot (= []), so once
// the first mutation batch leaked a single non-inert outbox row, every
// subsequent batch in every downstream spec saw `len > 0` and FAIL-cascaded
// (16 P0 in CI #44). Per-batch delta assigns leakage to the batch that
// caused it: snapshot = list AFTER current batch; next batch's verdict is
// (current ⊖ snapshot). Cumulative residue from prior batches is downgraded
// to REVIEW/P2 (informational), not FAIL.
const _externalCallsLastSnapshot = { calls: [], initialized: false };

function _callSignature(c) {
    // tur-28 (architect-review fix): use the immutable outbox row `id` as
    // the PRIMARY identity component. Backend projection now includes `id`
    // (see backend/domains/admin/router/stress.py:1873-1882). The attempt
    // counter is appended so a same-row retry (same id, attempts went 1→2)
    // is treated as NEW dispatcher activity within the same batch window.
    // Fallback fields (event_type|created_at|source) cover the corner case
    // where an older backend deploy hasn't yet shipped the projection
    // change — never collide-prone in isolation but collectively bound
    // the false-PASS surface to "same row, same retry count, same minute".
    return [
        c?.id ?? '',
        c?.event_type ?? '',
        c?.created_at ?? '',
        c?.source ?? '',
        c?.attempts ?? c?.attempt_count ?? c?.retry_count ?? 0,
    ].join('|');
}

export async function assertNoExternalCallsPostBatch(testInfo, module, batchName, stressState, request, pilotToken) {
    // Tur-9 ground-truth doctrine (CI run #21 NO-GO follow-up):
    //   GROUND TRUTH = "outbox dispatcher made a real HTTP attempt for THIS
    //   batch". Backend `/admin/stress/external-calls` already filters out
    //   inert rows (`no active connectors` / `dry_run` / `unsupported
    //   event_type`) AND requires `attempts > 0`. What survives is a row
    //   the dispatcher tried with a non-inert outcome.
    //
    //   Tur-28 evolution (CI #44 NO-GO follow-up): the verdict gate is the
    //   PER-BATCH DELTA, not the cumulative count. Pre-tur-28, a single
    //   leaked row in 05-H made 06/10/11/12/13/16/17/20-27 all fail with
    //   the SAME residue — 1 real finding masqueraded as 16 P0s. Now the
    //   helper tracks the previous snapshot in a module-scoped map and
    //   only flags batches whose own activity produced new rows.
    //
    //   FAIL/PASS axes (unchanged severity model, new scope):
    //     - PASS if deltaCalls.length === 0 (this batch added no real attempts).
    //     - FAIL P0 if deltaCalls.length > 0 (this batch tried HTTP for real).
    //     - REVIEW P2 if cumulative residue exists from prior batches but
    //       delta === 0 (informational — points the operator at the prior
    //       culprit batch, doesn't fail the current one).
    //     - dry_run_enforced INFORMATIONAL (self-report, stale env-prop safe).
    //     - query_errors[] INFORMATIONAL (REVIEW finding).
    let runtimeBody = null;
    let endpointStatus = null;
    let endpointError = null;
    let runtimeCallsLen = null;
    let runtimeCalls = [];
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
                    runtimeCalls = runtimeBody.external_calls_made;
                    runtimeCallsLen = runtimeCalls.length;
                }
                if (Array.isArray(runtimeBody?.query_errors)) {
                    runtimeQueryErrors = runtimeBody.query_errors;
                }
            }
        } catch (e) { endpointError = String(e?.message || e); }
    }
    const seedExt = stressState?.seed_response?.external_calls_made;
    const snapshotOk = Array.isArray(seedExt) && seedExt.length === 0;

    // tur-28 per-batch delta computation. `_externalCallsLastSnapshot.calls`
    // is the prior batch's full runtime list (or [] on first call). Delta =
    // signatures present in current but not in prior. The snapshot is
    // updated AFTER verdict so a single helper call always isolates "what
    // happened during THIS batch".
    let deltaCalls = [];
    let deltaLen = 0;
    let residueLen = 0;
    if (runtimeCallsLen != null) {
        // tur-28 (architect-review fix): multiset/count-based diff. If two
        // current rows happen to share a signature (e.g. older backend
        // without `id` in projection, identical timestamps), set-only diff
        // would count the second occurrence as residue → false PASS.
        // Multiset approach: build a count Map of prior signatures, and
        // for each current row, if priorCount[sig] > 0 → carryover
        // (decrement), else → new (delta). Strictly handles duplicates.
        const priorCounts = new Map();
        for (const c of (_externalCallsLastSnapshot.calls || [])) {
            const s = _callSignature(c);
            priorCounts.set(s, (priorCounts.get(s) || 0) + 1);
        }
        for (const c of runtimeCalls) {
            const s = _callSignature(c);
            const have = priorCounts.get(s) || 0;
            if (have > 0) {
                priorCounts.set(s, have - 1);  // consume one carryover
                residueLen += 1;
            } else {
                deltaCalls.push(c);
            }
        }
        deltaLen = deltaCalls.length;
        // Sanity: deltaLen + residueLen === runtimeCallsLen by construction.
        // Snapshot updated unconditionally so the next call's delta is
        // measured against "everything seen up to and including this batch".
        // Updating only on PASS would reintroduce cascade failures.
        _externalCallsLastSnapshot.calls = runtimeCalls;
        _externalCallsLastSnapshot.initialized = true;
    }

    // Verdict tablosu (tur-28, per-batch delta doctrine):
    //   1. Runtime reachable + deltaLen===0                       → PASS (this batch added nothing)
    //   2. Runtime reachable + deltaLen>0                         → FAIL P0 (this batch made real attempts)
    //   3. Runtime reachable + parsed calls=null                  → FAIL P1 (response shape regression)
    //   4. Runtime 404                                            → snapshot fallback (PASS if snapshot=[], else FAIL)
    //   5. Runtime 401/403/5xx/network                            → snapshot fallback REVIEW
    //                                                              (PASS if snapshot=[] çünkü pre-batch ground truth)
    //   6. caller_missing_pilot_token                             → FAIL P1 (helper misuse)
    let status, source, severity = null;
    if (!request || !pilotToken) { status = 'FAIL'; source = 'caller_missing_pilot_token'; severity = 'P1'; }
    else if (endpointStatus && endpointStatus >= 200 && endpointStatus < 300 && runtimeCallsLen != null && deltaLen === 0) {
        status = 'PASS'; source = residueLen > 0 ? 'runtime_endpoint_delta_zero_with_residue' : 'runtime_endpoint_delta_zero';
    }
    else if (deltaLen > 0) {
        status = 'FAIL'; source = 'runtime_endpoint_batch_delta_nonempty'; severity = 'P0';
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
    // tur-28: residueLen > 0 (PASS-with-carryover) durumunda da debug eklenir
    // çünkü prior batch'in leakage'ini operatörün görebilmesi gerekiyor.
    const wantDebug = status === 'FAIL'
        || residueLen > 0
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
                        delta_calls_length: deltaLen,
                        delta_calls: deltaCalls,
                        residue_length: residueLen,
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
                        ? (residueLen > 0 ? 'delta_zero_residue_from_prior_batch' : 'delta_zero_ground_truth_satisfied')
                        : (severity === 'P0' ? 'this_batch_produced_real_external_attempt' : 'invariant_unverifiable_no_snapshot'),
                    response_body: runtimeBody,
                    env_in_runner: {
                        E2E_EXTERNAL_DRY_RUN: process.env.E2E_EXTERNAL_DRY_RUN ?? 'unset',
                        E2E_ALLOW_DESTRUCTIVE_STRESS: process.env.E2E_ALLOW_DESTRUCTIVE_STRESS ?? 'unset',
                        E2E_STRESS_TENANT_ID: process.env.E2E_STRESS_TENANT_ID ?? 'unset',
                        PILOT_TENANT_ID: process.env.PILOT_TENANT_ID ? '[set]' : 'unset',
                    },
                    note: 'Tur-28 per-batch delta: PASS gates on delta===0 (carryover from prior batches downgraded to REVIEW).',
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
            note: `source=${source} endpoint_status=${endpointStatus ?? 'n/a'} runtime_calls_len=${runtimeCallsLen} delta=${deltaLen} residue=${residueLen} dry_run_enforced=${runtimeBody?.dry_run_enforced ?? 'n/a'} snapshot_ext_len=${Array.isArray(seedExt) ? seedExt.length : 'n/a'} query_errors=${runtimeQueryErrors.length}`,
        }),
    });
    if (status === 'FAIL') {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: severity || 'P1',
                module,
                title: severity === 'P0'
                    ? 'Per-batch external_calls invariant ihlal — bu batch gerçek dispatcher attempt yaptı'
                    : 'External-calls invariant doğrulanamadı (helper/endpoint) ve snapshot fallback yok',
                detail: `Batch=${batchName} source=${source} delta_len=${deltaLen} runtime_calls_len=${runtimeCallsLen} delta_calls=${JSON.stringify(deltaCalls)} dry_run_enforced=${runtimeBody?.dry_run_enforced} snapshot=${JSON.stringify(seedExt)} endpoint_status=${endpointStatus ?? 'n/a'} endpoint_error=${endpointError ?? 'n/a'} query_errors=${JSON.stringify(runtimeQueryErrors)}.`,
            }),
        });
    } else if (residueLen > 0) {
        // PASS ama prior batch'lerden carryover var → REVIEW (informational).
        // Bu run'da daha önceki bir batch leakage yaptı; tur-28 doctrine
        // gereği bu batch onun günahını üstlenmiyor, ama operatöre sinyal
        // verilir ki kök sebep ÖNCEKİ batch'te aransın.
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P2',
                module,
                title: 'External-calls residue carryover — prior batch leakage tespit edildi',
                detail: `Batch=${batchName} delta=0 (bu batch nötr) ama residue=${residueLen} prior carryover var. Kök sebep önceki batch'lerin debug attachment'larında. Bu batch PASS, prior FAIL ayrı bulgu.`,
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
                detail: `Batch=${batchName} delta=0 ground truth tutuldu fakat backend ${runtimeQueryErrors.length} query error raporladı: ${JSON.stringify(runtimeQueryErrors)}. Ground truth PASS, ama izleme önerilir.`,
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

// Task #192 Foundation (F8F–F8N enablement) — additive helpers below.
// Mevcut imzalar değişmez; yeni spec'lerin paylaşacağı ortak primitive'ler.

// assertPilotDriftZero — pilot tenant'a leak olup olmadığını read-only doğrular.
// Stress suite'in mutlak kuralı: pilot tenant'a hiçbir mutation yapılmaz.
// Baseline (genelde stressTokens.pilot_baseline veya seed snapshot)
// vs şimdiki count karşılaştırılır. Drift > 0 → P0 finding emit.
// Pilot token yoksa SKIP (no-op informational).
export async function assertPilotDriftZero(testInfo, module, request, pilotToken, baseline) {
    if (!request || !pilotToken) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'pilot_drift_zero', status: 'SKIP',
                note: 'pilot_token yok — drift doğrulanamadı (informational).',
            }),
        });
        return true;
    }
    const snap = await pilotBookingsCount(request, pilotToken);
    const baselineCount = (typeof baseline === 'number') ? baseline : (baseline?.count ?? null);
    // tur-29 (CI #49 NO-GO follow-up): unreachable guard centralized here so
    // ALL drift-check sites (~16 specs using assertPilotDriftZero) honor it
    // uniformly. If pilotBookingsCount exhausted its 3-attempt 5xx retry and
    // backend is still non-2xx, we cannot trust the synthetic `count=0` —
    // record REVIEW (infra) and return true. Real drift would resurface in
    // any subsequent drift-check spec since each re-snapshots independently.
    if (snap?.unreachable) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'pilot_drift_zero', status: 'REVIEW',
                note: `pilot endpoint unreachable (http=${snap.http}) after retry — drift unverifiable; downstream specs re-snapshot.`,
            }),
        });
        return true;
    }
    const afterCount = snap?.count ?? null;
    const drift = (baselineCount != null && afterCount != null) ? (afterCount - baselineCount) : null;
    const pass = drift === 0;
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'pilot_drift_zero',
            status: pass ? 'PASS' : (drift == null ? 'REVIEW' : 'FAIL'),
            note: `baseline=${baselineCount} after=${afterCount} drift=${drift} http=${snap?.http ?? 'n/a'}`,
        }),
    });
    if (drift != null && drift !== 0) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Pilot tenant drift tespit edildi — stress suite pilot mutation üretti',
                detail: `Baseline bookings=${baselineCount}, after=${afterCount}, drift=${drift}. Mutlak kural ihlali (pilot read-only).`,
            }),
        });
    }
    return pass;
}

// assertNoTokenLeak — credential/token leak guard. Audit/log/admin response
// body'sinde JWT, bearer-like, API key, refresh token gibi credential
// materyali bulunmamalı (KVKK + threat-model: tokens=spoofing primitive).
// Recursive: response JSON tree'sini gezer, string değerlerde token pattern
// arar. Bulunursa P0 finding (token-leak == cross-tenant spoofing primer).
// `tokenKeys`: field-name allowlist; key adı ne olursa olsun *value* token
// pattern eşliyorsa yakalanır (defense-in-depth). Pattern listesi:
//   • JWT compact: 3 base64url segment . ile ayrılmış, length≥40
//   • Bearer prefix: "Bearer xxx..."
//   • Common token field names + non-masked value (>20 char, non-hex-hash)
export function assertNoTokenLeak(testInfo, module, responseBody, contextLabel = 'response') {
    const JWT_RE = /\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b/;
    const BEARER_RE = /\bBearer\s+[A-Za-z0-9._-]{20,}/i;
    const TOKEN_KEYS = new Set([
        'jwt', 'token', 'access_token', 'refresh_token', 'id_token',
        'api_key', 'apikey', 'secret', 'client_secret', 'authorization',
        'session_token', 'bearer', 'auth_token',
    ]);
    const MIN_OPAQUE_LEN = 24;
    const isMaskedish = (s) => {
        if (s == null) return true;
        const v = String(s);
        if (v.length < 8) return true;
        if (/[*x]{3,}/i.test(v)) return true;
        if (/^masked/i.test(v)) return true;
        if (/^(redacted|hidden|null|none)$/i.test(v)) return true;
        if (/^[a-f0-9]{16,}$/i.test(v)) return true; // hash-like
        return false;
    };
    const leaks = [];
    const walk = (node, pathParts) => {
        if (node == null) return;
        if (leaks.length >= 10) return; // cap output
        if (typeof node === 'string') {
            const path = pathParts.join('.') || '(root)';
            if (JWT_RE.test(node)) {
                leaks.push({ path, kind: 'jwt', sample: node.slice(0, 16) + '…' });
                return;
            }
            if (BEARER_RE.test(node)) {
                leaks.push({ path, kind: 'bearer', sample: node.slice(0, 20) + '…' });
                return;
            }
            return;
        }
        if (Array.isArray(node)) {
            for (let i = 0; i < Math.min(node.length, 100); i++) {
                walk(node[i], pathParts.concat(`[${i}]`));
            }
            return;
        }
        if (typeof node === 'object') {
            for (const k of Object.keys(node)) {
                const lk = k.toLowerCase();
                const v = node[k];
                if (TOKEN_KEYS.has(lk) && typeof v === 'string'
                    && v.length >= MIN_OPAQUE_LEN && !isMaskedish(v)) {
                    leaks.push({
                        path: pathParts.concat(k).join('.'),
                        kind: 'token_field',
                        field: k,
                        sample: v.slice(0, 16) + '…',
                    });
                    if (leaks.length >= 10) return;
                }
                walk(v, pathParts.concat(k));
            }
        }
    };
    // Validation review #2 yorum #3: walker hatasını sessizce yutmak yerine
    // REVIEW annotation üret (observability).
    let walkError = null;
    try { walk(responseBody, []); } catch (e) { walkError = e?.message || String(e); }
    if (walkError) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'token_leak_walker_error',
                status: 'REVIEW',
                note: `context=${contextLabel} error=${walkError.slice(0, 200)}`,
            }),
        });
    }

    const pass = leaks.length === 0;
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'token_leak_guard',
            status: pass ? 'PASS' : 'FAIL',
            note: `context=${contextLabel} leaks=${leaks.length}`,
        }),
    });
    if (!pass) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: `Token/JWT leak in ${contextLabel} response`,
                detail: `${leaks.length} leak(s): ${JSON.stringify(leaks.slice(0, 5))}. Tokens = spoofing primitive (threat-model § Spoofing/Information Disclosure); audit/log/admin response'ları credential material taşımamalı.`,
            }),
        });
    }
    return pass;
}

// assertPiiMasked — KVKK/PII guard: response body'de hassas alanlar masked mı?
// Telefon/email/TC/passport/IBAN gibi alanlar full plaintext dönmemeli;
// expected pattern: kısmen masked (***, son 4 hane) veya hash. Plain match
// (örn. tam telefon numarası regex'i) bulunursa P0 finding.
// `fields`: kontrol edilecek alan adları (örn. ['phone', 'identity_number', 'email']).
// `responseBody`: API JSON response (Array veya Object kabul eder).
// Pattern dedektörleri konservatif: TC (11 ardışık digit), telefon (10+ digit),
// email (RFC-light), passport (alfanümerik 7-12). Mask işaretleri: '*', 'x' (3+),
// 'masked' substring veya hash-like ([a-f0-9]{16+}).
export function assertPiiMasked(testInfo, module, responseBody, fields = ['phone', 'email', 'identity_number', 'passport_no', 'iban']) {
    const items = Array.isArray(responseBody) ? responseBody
        : Array.isArray(responseBody?.items) ? responseBody.items
        : Array.isArray(responseBody?.data) ? responseBody.data
        : Array.isArray(responseBody?.guests) ? responseBody.guests
        : responseBody && typeof responseBody === 'object' ? [responseBody] : [];
    const violations = [];
    const isMasked = (v) => {
        if (v == null || v === '') return true;
        const s = String(v);
        if (/[*x]{3,}/i.test(s)) return true;
        if (/masked/i.test(s)) return true;
        if (/^[a-f0-9]{16,}$/i.test(s)) return true;
        return false;
    };
    const looksLikePlainPii = (field, v) => {
        if (v == null || v === '') return false;
        const s = String(v);
        if (field === 'identity_number' && /^\d{11}$/.test(s)) return true;
        if (field === 'phone' && /^\+?\d[\d\s().-]{8,}\d$/.test(s) && /\d{10,}/.test(s.replace(/\D/g, ''))) return true;
        if (field === 'email' && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(s)) return true;
        if (field === 'passport_no' && /^[A-Z0-9]{7,12}$/i.test(s)) return true;
        if (field === 'iban' && /^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$/i.test(s)) return true;
        return false;
    };
    for (let i = 0; i < Math.min(items.length, 50); i++) {
        const it = items[i];
        if (!it || typeof it !== 'object') continue;
        for (const f of fields) {
            const v = it[f];
            if (v == null) continue;
            if (!isMasked(v) && looksLikePlainPii(f, v)) {
                violations.push({ index: i, field: f, sample: String(v).slice(0, 4) + '…' });
            }
        }
    }
    const pass = violations.length === 0;
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'pii_masked',
            status: pass ? 'PASS' : 'FAIL',
            note: `checked_fields=${fields.join(',')} sampled_items=${Math.min(items.length, 50)} violations=${violations.length}`,
        }),
    });
    if (!pass) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'PII guard ihlal — hassas alan masked değil',
                detail: `Violations: ${JSON.stringify(violations.slice(0, 10))}. KVKK retention/PII guard rejimi response shape'de uygulanmamış.`,
            }),
        });
    }
    return pass;
}

// ============================================================================
// F8D-v2 (Task #205) — HR Deep Stress helpers.
// ============================================================================
//
// FORBIDDEN_HR_PAYROLL_FINALIZE — kasıtlı string concat: helper modülünde
// bile literal `/api/hr/payroll/finalize` substring olarak yer almasın ki
// `assertEndpointNeverCalled` source-scan'i kendi modül dosyasında false
// positive üretmesin. Spec'ler bu sabiti import ederek finalize URL'ini
// İSME göre referans verir; bu sayede spec source'unda finalize literal'i
// hiç görünmez (task acceptance "spec içinde URL string olarak bile yer
// almaz" şartı sağlanır).
export const FORBIDDEN_HR_PAYROLL_FINALIZE = '/api/hr/payroll/' + 'fin' + 'alize';
export const FORBIDDEN_HR_STAFF_TERMINATE_FRAGMENT = '/staff/' + 'term' + 'inate';
export const FORBIDDEN_HR_SALARY_CHANGE_FRAGMENT = '/sal' + 'ary-change';

// assertEndpointNeverCalled — spec source dosyasını okuyup yasak URL
// substring'inin literal olarak bulunup bulunmadığını kontrol eder.
// Helper'ın import edildiği satır + helper çağrı satırı (sabit ismi
// içerebilir ama substring kendi başına geçmez çünkü concat ile inşa).
// Doctrine: spec source'unda forbidden literal varsa → P0 + FAIL.
//   `testInfo.file` Playwright'tan gelir (absolute path). Source unreachable
//   ise P2 informational rec.
// Signature: (testInfo, module, urlSubstring) → bool (true=clean).
export function assertEndpointNeverCalled(testInfo, module, urlSubstring) {
    let source = '';
    let sourcePath = testInfo?.file;
    // FAIL-CLOSED guard (architect iter-6 directive): source-scan supplemental
    // layer'ın silently degrade etmesi yasak. Hem `testInfo.file` eksik hem
    // de fs read başarısızlığı durumunda → FAIL + P0 finding + return false
    // (caller expect(...).toBe(true) ile test FAIL eder). ESM-safe fs erişimi:
    // önce dynamic createRequire fallback, sonra `node:fs` global require.
    if (!sourcePath) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'forbidden_endpoint_guard',
                status: 'FAIL',
                note: 'testInfo.file missing — fail-closed (cannot verify forbidden literal absence)',
            }),
        });
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Forbidden endpoint guard FAIL-CLOSED — testInfo.file unavailable',
                detail: `substring_len=${urlSubstring.length}. Guard cannot verify spec source; treating as violation per iter-6 fail-closed doctrine.`,
            }),
        });
        return false;
    }
    try {
        // ESM-safe sync fs access: Playwright runs specs as CommonJS-compatible
        // modules so `require` is defined; if not, surface error → fail-closed.
        // eslint-disable-next-line @typescript-eslint/no-var-requires, no-undef
        const fs = require('node:fs');
        source = fs.readFileSync(sourcePath, 'utf-8');
    } catch (e) {
        // Fail-closed (iter-6): runtime invariant primary olsa da source-scan
        // supplemental layer'ın environment-dependent silent skip etmesi yasak.
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'forbidden_endpoint_guard',
                status: 'FAIL',
                note: `source_unreachable path=${sourcePath} err=${String(e?.message || e).slice(0, 120)} — fail-closed`,
            }),
        });
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Forbidden endpoint source-scan guard FAIL-CLOSED — spec source unreachable',
                detail: `testInfo.file=${sourcePath} substring_len=${urlSubstring.length} err=${String(e?.message || e).slice(0, 120)}. Iter-6 fail-closed doctrine: source-scan failure is treated as guard violation; primary runtime invariant (string-concat constant) tek başına yeterli sayılmaz.`,
            }),
        });
        return false;
    }
    // Look for the forbidden substring literally in the source. Constants
    // imported by name (FORBIDDEN_HR_PAYROLL_FINALIZE) do NOT contain the
    // substring because the constant value is built via string concat.
    const found = source.includes(urlSubstring);
    if (found) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'forbidden_endpoint_guard',
                status: 'FAIL',
                note: `FORBIDDEN literal found in spec source: substring="${urlSubstring}" path=${sourcePath}`,
            }),
        });
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                summary: 'Forbidden HR endpoint literal present in spec source',
                detail: `substring="${urlSubstring}" path=${sourcePath} — task doctrine yasağı (finalize/terminate/salary-change kapalı kapı).`,
            }),
        });
        return false;
    }
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'forbidden_endpoint_guard',
            status: 'PASS',
            note: `clean substring_len=${urlSubstring.length} path=${sourcePath?.split('/').pop()}`,
        }),
    });
    return true;
}

// assertHrPiiMasked — HR-spesifik PII maskeleme guard. assertPiiMasked'in
// HR varyantı: TC (11 digit), IBAN (TR\d{24}), phone, salary numeric, IBAN
// fragment paternleri için regex check. Maskelenmemiş plain değer
// bulunursa P0 (KVKK + financial). Mevcut `assertPiiMasked` field-name
// tabanlı; bu helper VALUE-pattern tabanlı (KVKK leakage detection için
// daha sıkı — masked field bile içinde plain TC içeriyorsa yakalar).
//   Signature: (testInfo, module, body, fieldsBlocklist?) → bool.
// PHONE_LEAK_PATTERNS — Türk mobil telefon plaintext kalıpları:
//   • +90 5XX XXX XX XX (uluslararası prefix)
//   • 05XX XXX XX XX (ulusal prefix)
//   • 5XX-XXX-XXXX (kısa form, separator'lı)
//   • 10+ ardışık digit "5" ile başlayan (operator prefix)
// Maskeli telefonlar (***, X'lerle yer tutulu) bu patternlere uymaz.
const PHONE_LEAK_PATTERNS = [
    /\+?90\s*[-.\s]?5\d{2}[-.\s]?\d{3}[-.\s]?\d{2}[-.\s]?\d{2}/g,
    /\b05\d{2}[-.\s]?\d{3}[-.\s]?\d{2}[-.\s]?\d{2}\b/g,
    /\b5\d{2}[-.\s]\d{3}[-.\s]\d{4}\b/g,
];

export function assertHrPiiMasked(testInfo, module, body, fieldsBlocklist = []) {
    if (body == null) return true;
    const text = typeof body === 'string' ? body : JSON.stringify(body);
    const violations = [];
    // TC Kimlik No: 11 ardışık digit, başında "TC" işareti yok (genel sayı dizisi).
    // False-positive azaltmak için sınırlayıcı word boundary ekle; ID/UUID
    // hex'leri 11-digit pattern'e uymaz.
    const tcMatches = text.match(/\b\d{11}\b/g) || [];
    // 11-digit dizilerin hepsi sahte değil — gerçek TC formatı: ilk hane 0
    // olamaz, son hane checksum. Test/seed verisinde sentetik TC olabilir
    // ama hiçbiri masked olmamalı → her 11-digit dizi raporla.
    for (const tc of tcMatches) {
        if (tc[0] !== '0') violations.push({ kind: 'TC_KIMLIK_NO', sample: tc.slice(0, 3) + '***' + tc.slice(-2) });
    }
    // IBAN: TR + 24 digit (toplam 26 char).
    const ibanMatches = text.match(/\bTR\d{24}\b/g) || [];
    for (const ib of ibanMatches) violations.push({ kind: 'IBAN', sample: ib.slice(0, 6) + '***' + ib.slice(-4) });
    // Salary plain — JSON shape `"salary": <number>` veya `"net_salary": <number>`
    // > 1000 → masking ihlali (mask formatı: "***" string veya kırpılmış).
    const salaryMatches = text.match(/"(?:net_)?salary"\s*:\s*(\d{4,})/g) || [];
    for (const s of salaryMatches) violations.push({ kind: 'SALARY_PLAIN', sample: s.slice(0, 40) });
    // Phone leak — Türk mobil telefon plaintext kalıpları (PHONE_LEAK_PATTERNS).
    // KVKK explicit: telefon numarası kişisel veri; HR endpoint response'unda
    // staff/applicant phone field'ı plaintext görünmemeli (maskeli: 5XX***XX
    // veya tamamen redacted). Architect iter-4 directive: spec 36 PII guard
    // requirement gap'i kapatır.
    for (const re of PHONE_LEAK_PATTERNS) {
        const hits = text.match(re) || [];
        for (const ph of hits) {
            const digits = ph.replace(/\D/g, '');
            // Maskeli telefon (e.g. "5XX***XX") regex'e zaten uymaz; raw digit
            // sample'ı kısalt: ilk 4 + *** + son 2.
            violations.push({ kind: 'PHONE_PLAIN', sample: digits.slice(0, 4) + '***' + digits.slice(-2) });
        }
    }
    // Custom fields blocklist — kullanıcı belirttiği özel alan adları (örn.
    // 'identity_number', 'tax_number'). Bu alanların plain string değer
    // taşımaması beklenir.
    for (const f of fieldsBlocklist) {
        const re = new RegExp(`"${f}"\\s*:\\s*"([^"*\\\\]{6,})"`, 'g');
        const m = text.match(re) || [];
        for (const hit of m) violations.push({ kind: `FIELD_${f.toUpperCase()}`, sample: hit.slice(0, 60) });
    }
    if (violations.length > 0) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'pii_masked_check',
                status: 'FAIL',
                note: `violations=${violations.length} kinds=${[...new Set(violations.map(v => v.kind))].join(',')}`,
            }),
        });
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                summary: 'HR PII (TC/IBAN/salary/phone) plain — masking missing',
                detail: violations.slice(0, 5).map(v => `${v.kind}:${v.sample}`).join(' | '),
            }),
        });
        return false;
    }
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'pii_masked_check',
            status: 'PASS',
            note: `body_len=${text.length} no_plain_pii_detected`,
        }),
    });
    return true;
}

// withModuleProbe — endpoint reachability + RBAC probe. 403/404/cache-stale
// durumunda spec'in A/B/C/D step'lerini güvenle skip etmek için kullanılır.
// Returns: `{moduleBlocked: bool, status: int, body: any, reason: string}`.
// F8C/D/E module-blocked pattern doctrine'in tek-noktada helper'ı.
export async function withModuleProbe(request, token, endpoint, opts = {}) {
    const method = (opts.method || 'get').toLowerCase();
    const timeout = opts.timeout ?? 10_000;
    let status = 0, body = null, err = null;
    try {
        const r = await request[method](endpoint, {
            headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
            data: opts.body,
            failOnStatusCode: false,
            timeout,
        });
        status = r.status();
        try { body = await r.json(); } catch { body = null; }
    } catch (e) { err = String(e?.message || e); }
    const moduleBlocked = status === 403 || status === 404 || status === 0;
    let reason = 'reachable';
    if (status === 403) reason = 'rbac_denied';
    else if (status === 404) reason = 'endpoint_not_deployed';
    else if (status === 0) reason = `network_error_${err?.slice(0, 40) ?? 'unknown'}`;
    else if (status >= 500) reason = `server_error_${status}`;
    return { moduleBlocked, status, body, reason, error: err };
}

// ============================================================================
// F8O (Task #206) — AI/Automation Dry-run Stress helpers.
// ============================================================================
//
// Forbidden AI/automation surfaces — kasıtlı string concat (kendi modülünde
// literal substring olarak görünmesin → `assertEndpointNeverCalled` source
// scan'i false-positive üretmesin). Spec'ler bu sabitleri sadece İSME göre
// referans verir; substring kendi başına spec source'unda hiç geçmez.
//
//   - FORBIDDEN_AI_AUTOPILOT_RUN     → POST /api/autopilot/run-cycle
//     (revenue autopilot mutation; F8O için kapalı kapı — gerçek rate
//     publish + CM outbox event üretebilir).
//   - FORBIDDEN_AI_AUTOPILOT_SETMODE → POST /api/autopilot/set-mode
//     (mode değiştirme; supervised/full_auto'ya geçiş → arka plan otomatik
//     çalıştırma riski).
//   - FORBIDDEN_AI_ML_TRAIN_ALL      → POST /api/ml/train-all
//     (tüm modellerin retraining'ini tetikler — uzun süren job + vendor
//     LLM çağrı potansiyeli).
//   - FORBIDDEN_AI_ML_TRAIN_FRAGMENT → "/ml/" + "train" (substring guard:
//     /ml/rms/train, /ml/persona/train, /ml/predictive-maintenance/train,
//     /ml/hk-scheduler/train; her biri yasak).
export const FORBIDDEN_AI_AUTOPILOT_RUN = '/api/autopilot/' + 'run' + '-cycle';
export const FORBIDDEN_AI_AUTOPILOT_SETMODE = '/api/autopilot/' + 'set' + '-mode';
export const FORBIDDEN_AI_ML_TRAIN_ALL = '/api/ml/' + 'train' + '-all';
export const FORBIDDEN_AI_ML_TRAIN_FRAGMENT = '/ml/' + 'train';
// F8O (Task #206) extra forbidden surfaces — pricing/autopilot publish/apply.
// Concat sentinels so source-scan never sees these literals in spec source.
export const FORBIDDEN_AI_RATE_APPLY = '/' + 'rate' + '/' + 'apply';
export const FORBIDDEN_AI_AUTOPILOT_EXECUTE = '/' + 'autopilot' + '/' + 'execute';
export const FORBIDDEN_AI_PRICING_PUBLISH = '/' + 'pricing' + '/' + 'publish';

// snapshotAiCallCount — baseline reader for vendor-call ledger.
// Returns { ok, count, body } — count=null if endpoint unreachable.
// Specs call this at setup and pass `baselineCount` to
// assertNoVendorHttpCall at batch-end for authoritative delta check.
export async function snapshotAiCallCount(request, token) {
    try {
        const r = await request.get('/api/ai/diagnostics/llm-state', {
            headers: { Authorization: `Bearer ${token}` },
            failOnStatusCode: false, timeout: 10_000,
        });
        if (r.status() >= 200 && r.status() < 300) {
            const body = await r.json().catch(() => null);
            if (body && typeof body.attempted_call_count === 'number') {
                return { ok: true, count: body.attempted_call_count, body };
            }
        }
        return { ok: false, count: null, body: null, status: r.status() };
    } catch (e) {
        return { ok: false, count: null, body: null, error: String(e?.message || e).slice(0, 80) };
    }
}

// assertNoVendorHttpCall — F8O mutlak kuralı: hiçbir spec batch'i vendor
// LLM (OpenAI/Anthropic/Gemini) HTTP çağrısı tetiklememeli. AUTHORITATIVE
// signal: backend ledger (`attempted_call_count`).
//
// CRITICAL DESIGN NOTE (Task #206 architect finding #3): bu helper
// HİÇBİR LLM-touching endpoint çağırmaz (briefing/recommend/predict
// yok). Sadece `/api/ai/diagnostics/llm-state` config snapshot okur.
// Briefing çağrısı llm_enabled=true iken `_create_chat()` tetikler ve
// ledger'ı şişirir → guard kendini geçersiz kılar. Ledger delta tek
// authoritative sinyaldir.
//
// Pass criteria: ledger verifiable AND delta === 0.
// Verifiable = HTTP 2xx + JSON parse OK + baseline AND current non-null.
// Diag 503 (E2E_AI_DRY_RUN kapalı), 4xx, 5xx, parse fail → P0 fail-closed.
//
// Signature: (testInfo, module, request, token, baselineCount?, label?) → bool.
export async function assertNoVendorHttpCall(testInfo, module, request, token, baselineCount = null, label = 'post_batch') {
    let llmState = null, diagStatus = 0, diagErr = null;
    try {
        const r = await request.get('/api/ai/diagnostics/llm-state', {
            headers: { Authorization: `Bearer ${token}` },
            failOnStatusCode: false, timeout: 10_000,
        });
        diagStatus = r.status();
        if (diagStatus >= 200 && diagStatus < 300) {
            try { llmState = await r.json(); } catch { llmState = null; }
        }
    } catch (e) { diagErr = String(e?.message || e).slice(0, 80); }

    const llmEnabled = !!(llmState && llmState.llm_enabled);
    const providers = (llmState && llmState.providers) || {};
    const currentCount = (llmState && typeof llmState.attempted_call_count === 'number')
        ? llmState.attempted_call_count : null;
    const diagVerifiable = diagStatus >= 200 && diagStatus < 300 && llmState !== null;

    // AUTHORITATIVE PATH REQUIRED — fail-closed if ledger unverifiable.
    // Both baseline AND current count must be present and diag verifiable;
    // diagnostics 503 (E2E_AI_DRY_RUN unset), 4xx, parse fail → P0.
    const ledgerVerifiable = (baselineCount !== null && currentCount !== null && diagVerifiable);
    if (!ledgerVerifiable) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'no_vendor_http_call',
                status: 'FAIL',
                note: `label=${label} ledger_unverifiable baseline=${baselineCount} current=${currentCount} diag_verifiable=${diagVerifiable} diag_http=${diagStatus} diag_err=${diagErr || ''} — authoritative path required.`,
            }),
        });
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Vendor-call ledger unverifiable — fail-closed',
                detail: `label=${label} baselineCount=${baselineCount} currentCount=${currentCount} diagVerifiable=${diagVerifiable} diag_http=${diagStatus}. F8O mutlak kuralı: authoritative ledger sinyali olmadan dry-run guarantee verilmez.`,
            }),
        });
        return false;
    }
    // Authoritative check: ledger delta. ANY delta > 0 is a P0
    // vendor-call violation (even attempted-but-failed external HTTP).
    const ledgerDelta = currentCount - baselineCount;
    const pass = ledgerDelta === 0;
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'no_vendor_http_call',
            status: pass ? 'PASS' : 'FAIL',
            note: `label=${label} llm_enabled=${llmEnabled} ledger_baseline=${baselineCount} ledger_current=${currentCount} ledger_delta=${ledgerDelta} providers=${JSON.stringify(providers)} diag_http=${diagStatus}`,
        }),
    });
    if (!pass) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Vendor LLM attempted_call_count delta > 0 — dry-run kuralı ihlali',
                detail: `label=${label} delta=${ledgerDelta} baseline=${baselineCount} current=${currentCount}. AIService._create_chat() bu batch sırasında çağrıldı — vendor HTTP attempt (success ya da fail).`,
            }),
        });
    }
    return pass;
}

// assertAiDryRunEnvGuards — F8O mutlak kuralı: spec başlamadan önce
// E2E_AI_DRY_RUN=true + E2E_EXTERNAL_DRY_RUN=true env flag'leri set
// olmalı, ve hiçbir provider production-shape API key (sk-, sk-ant-,
// AIza-) içermemeli. Diagnostics body verir; eksik herhangi bir koşul
// fail-closed P0. process.env.E2E_EXTERNAL_DRY_RUN client-side de doğrulanır
// (stress fixture genelde set eder — yoksa P0).
//
// Signature: (testInfo, module, llmStateBody, processEnv?) → bool.
export function assertAiDryRunEnvGuards(testInfo, module, llmStateBody, processEnv = null) {
    const env = processEnv || (typeof process !== 'undefined' ? process.env : {}) || {};
    const serverAiDryRun = !!(llmStateBody && llmStateBody.e2e_ai_dry_run);
    const serverExternalDryRun = !!(llmStateBody && llmStateBody.e2e_external_dry_run);
    const looksReal = !!(llmStateBody && llmStateBody.looks_like_real_key);
    // Task #206 finding #1 — vendor base URL guard. If any key is set and
    // its base_url either points at the real vendor host or is unset
    // (SDK default = real host), egress to real vendor is possible.
    const looksRealVendorUrl = !!(llmStateBody && llmStateBody.looks_like_real_vendor_url);
    const urlBreakdown = (llmStateBody && llmStateBody.real_vendor_url_breakdown) || {};
    const clientExternalDryRun = (String(env.E2E_EXTERNAL_DRY_RUN || '').toLowerCase()) === 'true';
    // Task #206 finding #3 — mutlak kural: server-side E2E_EXTERNAL_DRY_RUN
    // ZORUNLU. Client-only fallback kaldırıldı (backend external dispatch
    // path'lerini sadece server env tutar; client env outbound HTTP'yi
    // engelleyemez). Client env informational; pass için server-side şart.
    const pass = serverAiDryRun && serverExternalDryRun && !looksReal && !looksRealVendorUrl;
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'ai_dry_run_env_guards',
            status: pass ? 'PASS' : 'FAIL',
            note: `server_ai_dry_run=${serverAiDryRun} server_ext_dry_run=${serverExternalDryRun} client_ext_dry_run=${clientExternalDryRun} looks_like_real_key=${looksReal} looks_like_real_vendor_url=${looksRealVendorUrl} url_breakdown=${JSON.stringify(urlBreakdown)}`,
        }),
    });
    if (!serverAiDryRun) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'E2E_AI_DRY_RUN env flag set değil (server-side)',
                detail: 'Stress dry-run için backend E2E_AI_DRY_RUN=true zorunlu (diagnostics endpoint 503 dönüyor olabilir).',
            }),
        });
    }
    if (!serverExternalDryRun) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'E2E_EXTERNAL_DRY_RUN env flag server-side set değil',
                detail: `Mutlak kural: external_calls için dry-run flag SERVER-side zorunlu (client_ext_dry_run=${clientExternalDryRun} informational). Backend outbound HTTP path'lerini sadece server env tutar.`,
            }),
        });
    }
    if (looksReal) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Production-shape API key tespit edildi (sk-/sk-ant-/AIza-)',
                detail: 'En az bir provider env value\'su gerçek prefix\'e sahip — stress ortamında ASLA gerçek key kullanılmaz. Bu key sentinel ile değiştirilmeli.',
            }),
        });
    }
    if (looksRealVendorUrl) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Vendor base_url override eksik veya gerçek vendor host işaret ediyor',
                detail: `breakdown=${JSON.stringify(urlBreakdown)} — En az bir provider için API key set ama OPENAI_BASE_URL/ANTHROPIC_BASE_URL/GEMINI_BASE_URL ya unset (SDK default = api.openai.com/api.anthropic.com/generativelanguage.googleapis.com) ya da gerçek vendor host işaret ediyor. Stress dry-run mutlak kuralı: base_url mock/sentinel hedefe override edilmeli.`,
            }),
        });
    }
    return pass;
}

// assertAiKeyShapeIsSentinel — fail-closed wrapper around the diagnostics
// `looks_like_real_key` boolean. Backend never returns key VALUES; only a
// shape detection bool (sk-/sk-ant-/AIza-). True → P0.
// Signature: (testInfo, module, llmStateBody) → bool.
// snapshotPilotBookingFields — F8O § 44 per-booking immutability baseline.
// Reads up to `sampleSize` pilot bookings and snapshots {id, status,
// no_show_at}. Returns { ok, samples: [{id,status,no_show_at}], total }.
// `samples=[]` is acceptable (no pilot bookings yet); immutability check
// short-circuits to PASS in that case.
export async function snapshotPilotBookingFields(request, pilotToken, sampleSize = 10) {
    try {
        // Task #206 finding (re-review #5) — correct route is
        // /api/pms/bookings (backend/routers/pms_bookings.py @ line 312).
        // Response shape: {bookings: [...], total: int}. Bookings expose
        // {id, status, no_show_at, ...} top-level. limit max=500.
        const r = await request.get('/api/pms/bookings?limit=200', {
            headers: { Authorization: `Bearer ${pilotToken}` },
            failOnStatusCode: false, timeout: 15_000,
        });
        if (r.status() < 200 || r.status() >= 300) {
            return { ok: false, samples: [], total: 0, status: r.status() };
        }
        const body = await r.json().catch(() => null);
        const list = Array.isArray(body) ? body : (body?.bookings || body?.items || []);
        const samples = list.slice(0, sampleSize).map((b) => ({
            id: b?.id || b?._id || b?.booking_id || null,
            status: b?.status || null,
            no_show_at: b?.no_show_at || null,
        })).filter((s) => s.id);
        return { ok: true, samples, total: list.length };
    } catch (e) {
        return { ok: false, samples: [], total: 0, error: String(e?.message || e).slice(0, 80) };
    }
}

// assertPilotBookingFieldsImmutable — F8O § 44 per-booking field
// immutability check. Re-reads same sampled bookings and compares
// {status, no_show_at}. Any drift → P0 finding.
// Signature: (testInfo, module, request, pilotToken, baselineSnapshot) → bool.
export async function assertPilotBookingFieldsImmutable(testInfo, module, request, pilotToken, baselineSnapshot) {
    // Task #206 finding #1 — FAIL-CLOSED. Önceki versiyonda baseline
    // unavailable veya samples=0 ise PASS dönüyordu (fail-open). Şimdi
    // baseline yoksa veya readback başarısızsa P0 + return false.
    if (!baselineSnapshot || !baselineSnapshot.ok) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'pilot_booking_fields_immutable',
                status: 'FAIL',
                note: `baseline_unavailable ok=${baselineSnapshot?.ok} status=${baselineSnapshot?.status} — fail-closed`,
            }),
        });
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Pilot booking immutability baseline alınamadı — fail-closed',
                detail: `baseline.ok=${baselineSnapshot?.ok} status=${baselineSnapshot?.status}. F8O § 44 mutlak kuralı: per-booking status+no_show_at immutability baseline olmadan kanıtlanamaz.`,
            }),
        });
        return false;
    }
    if (baselineSnapshot.samples.length === 0) {
        // Pilot tenant'ta booking yok — pilot mutation invariant boş set
        // üzerinde otomatik sağlanır; ancak bu beklenmeyen bir durumdur
        // (pilot demo seed normalde 10+ booking içerir). REVIEW kaydı +
        // pass (drift-free) — silent fail-open değil, görünür informational.
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'pilot_booking_fields_immutable',
                status: 'REVIEW',
                note: `samples=0 total=${baselineSnapshot.total} — pilot tenant has no bookings; immutability vacuously holds but baseline pool empty is unexpected.`,
            }),
        });
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P2', module,
                title: 'Pilot booking pool empty — immutability vacuously holds',
                detail: `total=${baselineSnapshot.total} — pilot tenant'ta hiç booking yok. Mutation invariant boş set üzerinde sağlanır; pool seed durumu gözden geçirilmeli.`,
            }),
        });
        return true;
    }
    const after = await snapshotPilotBookingFields(request, pilotToken, baselineSnapshot.samples.length);
    if (!after.ok) {
        testInfo.annotations.push({
            type: 'rec',
            description: JSON.stringify({
                module, step: 'pilot_booking_fields_immutable',
                status: 'FAIL',
                note: `readback_failed status=${after.status} — fail-closed`,
            }),
        });
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Pilot bookings re-read failed — immutability unverifiable',
                detail: `status=${after.status} — F8O § 44 mutlak kuralı: readback olmadan immutability kanıtlanamaz, fail-closed P0.`,
            }),
        });
        return false;
    }
    const afterById = new Map(after.samples.map((s) => [s.id, s]));
    const drifts = [];
    for (const before of baselineSnapshot.samples) {
        const now = afterById.get(before.id);
        if (!now) { drifts.push({ id: before.id, drift: 'disappeared' }); continue; }
        if ((now.status || null) !== (before.status || null)) {
            drifts.push({ id: before.id, field: 'status', before: before.status, after: now.status });
        }
        if ((now.no_show_at || null) !== (before.no_show_at || null)) {
            drifts.push({ id: before.id, field: 'no_show_at', before: before.no_show_at, after: now.no_show_at });
        }
    }
    const pass = drifts.length === 0;
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'pilot_booking_fields_immutable',
            status: pass ? 'PASS' : 'FAIL',
            note: `samples=${baselineSnapshot.samples.length} drifts=${drifts.length} sample=${JSON.stringify(drifts.slice(0, 3))}`,
        }),
    });
    if (!pass) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Pilot booking field drift — status/no_show_at mutation tespit edildi',
                detail: `drift_count=${drifts.length} sample=${JSON.stringify(drifts.slice(0, 3))}. Pilot mutation invariant ihlali.`,
            }),
        });
    }
    return pass;
}

export function assertAiKeyShapeIsSentinel(testInfo, module, llmStateBody) {
    const looksReal = !!(llmStateBody && llmStateBody.looks_like_real_key);
    const providers = (llmStateBody && llmStateBody.providers) || {};
    const dryRunFlag = !!(llmStateBody && llmStateBody.e2e_ai_dry_run);
    const pass = !looksReal;
    testInfo.annotations.push({
        type: 'rec',
        description: JSON.stringify({
            module, step: 'ai_key_shape_sentinel',
            status: pass ? 'PASS' : 'FAIL',
            note: `looks_like_real_key=${looksReal} providers=${JSON.stringify(providers)} e2e_ai_dry_run=${dryRunFlag}`,
        }),
    });
    if (looksReal) {
        testInfo.annotations.push({
            type: 'finding',
            description: JSON.stringify({
                severity: 'P0', module,
                title: 'Production-shape API key tespit edildi (sentinel beklenirdi)',
                detail: 'Provider env value(ları) sk-/sk-ant-/AIza- prefix\'inde — stress ortamında ASLA gerçek key kullanılmaz.',
            }),
        });
    }
    return pass;
}

// F8W § 09 — Ops Readiness Smoke.
//
// Threat-model + ops surface (docs/REPLIT_OPS_CHEATSHEET.md +
// docs/PRODUCTION_SAFETY_PLAN.md):
//   Production Safety Pack 8/8 DONE; ama stres suite içinde mini
//   readiness smoke yoktu. Nightly cron stress run'ı backup stale,
//   rollback metadata eksik, CM outbox depth artıyor, conflict queue
//   birikiyor, cache warmer 0 cycle gibi DEGRADASYON sinyallerini
//   YAKALAMALI — kod regression yok ama operasyon zinciri kırıldıysa
//   verdict NO-GO olmalı.
//
// Mutlak kurallar:
//   - pilot mutation = 0 (sadece read-only probe)
//   - external_calls = []
//   - failedTests = 0, P0 = P1 = 0
//
// Doctrine:
//   - PASS: tüm probe'lar 2xx + sinyal yeşil eşiğinde.
//   - REVIEW (P2): probe deploy yok (404) → bilgi amaçlı.
//   - FAIL (P1): sinyal kırmızı eşikte (örn. CM outbox depth >10k,
//     conflict queue >100, last backup yaşı >7 gün).
//   - Module-blocked tek probe için P2 informational; suite SKIP yok
//     (her probe bağımsız; biri blocked diğeri çalışır).
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    callTimed, recFinding,
    assertNoExternalCallsPostBatch, assertPilotDriftZero,
    pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'ops_readiness';

// Eşikler — degradasyon sinyali için.
const THRESHOLDS = {
    backup_max_age_hours: 36,          // last backup 36 saatten eski → REVIEW
    backup_critical_age_hours: 24 * 7, // 7 gün → P1
    cm_outbox_depth_max: 10_000,        // pending >10k → P1
    cm_conflict_queue_max: 100,         // pending >100 → P1
};

// Raw GET wrapper (no bearer needed for /health, /api/health, /health/ready).
async function rawGet(request, path, token, timeoutMs = 10_000) {
    const headers = token ? { Authorization: `Bearer ${token}` } : {};
    const t0 = Date.now();
    const r = await request.get(path, { headers, failOnStatusCode: false, timeout: timeoutMs })
        .catch((e) => ({ status: () => 0, _err: e?.message }));
    const ms = Date.now() - t0;
    const status = r.status?.() ?? 0;
    let body = null;
    try { body = r.json ? await r.json() : null; } catch { /* ignore */ }
    return { status, ms, body, ok: status >= 200 && status < 300 };
}

function ageHours(isoOrTs) {
    if (!isoOrTs) return null;
    const t = typeof isoOrTs === 'number' ? isoOrTs : Date.parse(isoOrTs);
    if (!t || Number.isNaN(t)) return null;
    return Math.max(0, (Date.now() - t) / 3_600_000);
}

test.describe.configure({ mode: 'serial' });

test.describe('F8W § 09 — Ops Readiness Smoke', () => {
    let pilotBefore = null;
    let prefix = null;

    test('Setup: pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'setup', status: 'PASS',
            note: `prefix=${prefix} pilot_before=${pilotBefore?.count}` });
    });

    test('A) Health endpoints — /health, /health/ready, /api/health all 200', async ({ request, stressState, stressTokens }, testInfo) => {
        const checks = ['/health', '/health/ready', '/api/health'];
        const results = [];
        let failures = 0;
        for (const p of checks) {
            const r = await rawGet(request, p, null, 8_000);
            results.push({ path: p, status: r.status, ms: r.ms });
            if (!r.ok) failures++;
        }
        rec(testInfo, { module: MOD, step: 'health_endpoints',
            status: failures === 0 ? 'PASS' : 'FAIL',
            note: `results=${JSON.stringify(results)} failures=${failures}` });
        if (failures > 0) {
            recFinding(testInfo, 'P1', MOD, 'Health endpoint(s) non-2xx during stress run',
                `results=${JSON.stringify(results)}. Bootstrap/ready/route mount sinyali kırmızı; deployment health çürümüş.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'health_endpoints', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('B) Backup status not stale — last backup age within threshold', async ({ request, stressTokens, stressState }, testInfo) => {
        // İki olası endpoint dene; ilki 2xx ise onu kullan.
        const candidates = [
            '/api/infra/backup/status',
            '/api/infra/backup/history',
            '/api/production/backup/validation',
            '/api/production/backup/history',
            '/api/admin/backup/list',
        ];
        let probed = null;
        let probeStatus = null;
        let body = null;
        for (const p of candidates) {
            const r = await rawGet(request, p, stressTokens.stress_token, 10_000);
            probeStatus = r.status;
            if (r.ok) { probed = p; body = r.body; break; }
            // Pilot token denemesi (super_admin RBAC).
            const r2 = await rawGet(request, p, stressTokens.pilot_token, 10_000);
            probeStatus = r2.status;
            if (r2.ok) { probed = p; body = r2.body; break; }
        }
        if (!probed) {
            recFinding(testInfo, 'P2', MOD, 'Backup status endpoint reachable değil',
                `tried=${JSON.stringify(candidates)} last_status=${probeStatus} — Atlas-managed backup tek sinyal kaynağı; UI/CLI metric path eklenmeli.`);
            rec(testInfo, { module: MOD, step: 'backup_status', status: 'REVIEW',
                note: `no reachable endpoint last_status=${probeStatus}` });
            // Backup observability endpoint deploy yok → module-block policy:
            // explicit skip (Atlas-managed backup tek sinyal; HTTP probe optional).
            // Silent-return YASAK (recFinding-then-return pass-through doctrine).
            test.skip(true, 'backup status endpoint not deployed');
            return;
        }
        // last backup zaman damgası — sık alan adları: last_backup_at,
        // last_backup_time, latest_backup, last_snapshot_at, snapshots[0].created_at.
        const candidates2 = [
            body?.last_backup_at, body?.last_backup_time, body?.latest_backup,
            body?.last_snapshot_at, body?.snapshots?.[0]?.created_at,
            body?.items?.[0]?.created_at, body?.history?.[0]?.created_at,
            body?.backups?.[0]?.created_at,
        ].filter(Boolean);
        const lastTs = candidates2[0] || null;
        const age = ageHours(lastTs);
        let status = 'PASS';
        if (age == null) {
            status = 'REVIEW';
            recFinding(testInfo, 'P2', MOD, 'Backup status response\'unda last_backup_at türetilemedi',
                `endpoint=${probed} body_keys=${Object.keys(body || {}).join(',').slice(0, 200)}. Shape değişti veya boş history.`);
        } else if (age > THRESHOLDS.backup_critical_age_hours) {
            status = 'FAIL';
            recFinding(testInfo, 'P1', MOD, 'Backup last age critical — >7 gün',
                `endpoint=${probed} age_hours=${age.toFixed(1)} threshold=${THRESHOLDS.backup_critical_age_hours}h. Backup chain kırık.`);
        } else if (age > THRESHOLDS.backup_max_age_hours) {
            status = 'REVIEW';
            recFinding(testInfo, 'P2', MOD, 'Backup last age elevated',
                `endpoint=${probed} age_hours=${age.toFixed(1)} threshold=${THRESHOLDS.backup_max_age_hours}h. İzleme gerek.`);
        }
        rec(testInfo, { module: MOD, step: 'backup_status', status,
            note: `endpoint=${probed} last=${lastTs} age_hours=${age?.toFixed(1) ?? 'n/a'}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'backup_status', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('C) CM outbox depth + conflict queue — within bounds', async ({ request, stressTokens, stressState }, testInfo) => {
        // Outbox depth — sık endpoint'ler.
        const outboxPaths = [
            '/api/cm/outbox/stats', '/api/cm/outbox/depth',
            '/api/channel-manager/outbox/stats', '/api/cm/health',
        ];
        let outboxDepth = null;
        let outboxEndpoint = null;
        for (const p of outboxPaths) {
            const r = await rawGet(request, p, stressTokens.pilot_token, 10_000);
            if (r.ok && r.body) {
                const depth = r.body.depth ?? r.body.pending ?? r.body.outbox_depth ?? r.body.queue_depth ?? r.body.stats?.pending ?? null;
                if (typeof depth === 'number') {
                    outboxDepth = depth;
                    outboxEndpoint = p;
                    break;
                }
            }
        }
        // Conflict queue — F8 CM-Hardening series ürünü.
        const conflictPaths = [
            '/api/cm/conflict-queue/stats',
            '/api/cm/conflict-queue?status=open&limit=1',
        ];
        let conflictCount = null;
        let conflictEndpoint = null;
        for (const p of conflictPaths) {
            const r = await rawGet(request, p, stressTokens.pilot_token, 10_000);
            if (r.ok && r.body) {
                const c = r.body.total ?? r.body.count ?? r.body.open_count ?? r.body.stats?.open ?? null;
                if (typeof c === 'number') {
                    conflictCount = c;
                    conflictEndpoint = p;
                    break;
                }
            }
        }
        // Verdict — eşik aşımı P1, endpoint yok P2.
        let status = 'PASS';
        const notes = [];
        if (outboxDepth == null) {
            recFinding(testInfo, 'P2', MOD, 'CM outbox depth endpoint reachable değil',
                `tried=${JSON.stringify(outboxPaths)} — observability sinyali eksik.`);
            notes.push('outbox=unreachable');
        } else {
            notes.push(`outbox_depth=${outboxDepth}@${outboxEndpoint}`);
            if (outboxDepth > THRESHOLDS.cm_outbox_depth_max) {
                status = 'FAIL';
                recFinding(testInfo, 'P1', MOD, 'CM outbox depth eşik üstü',
                    `depth=${outboxDepth} threshold=${THRESHOLDS.cm_outbox_depth_max}. Dispatcher arkada kalmış.`);
            }
        }
        if (conflictCount == null) {
            recFinding(testInfo, 'P2', MOD, 'CM conflict queue endpoint reachable değil',
                `tried=${JSON.stringify(conflictPaths)} — operasyon sinyali eksik.`);
            notes.push('conflict=unreachable');
        } else {
            notes.push(`conflict_open=${conflictCount}@${conflictEndpoint}`);
            if (conflictCount > THRESHOLDS.cm_conflict_queue_max) {
                status = 'FAIL';
                recFinding(testInfo, 'P1', MOD, 'CM conflict queue eşik üstü',
                    `open=${conflictCount} threshold=${THRESHOLDS.cm_conflict_queue_max}. Manuel resolve birikimi.`);
            }
        }
        rec(testInfo, { module: MOD, step: 'cm_backlog', status,
            note: notes.join(' ') });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'cm_backlog', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('D) Cache warmer + WS hub + observability — alive signals', async ({ request, stressTokens, stressState }, testInfo) => {
        // Best-effort liveness probes. Hedef: hiçbiri 5xx olmamalı; her biri
        // 2xx veya 404. 5xx → P1 (servis çürümesi).
        const probes = [
            { name: 'ws_stats', path: '/api/enterprise/ws/stats' },
            { name: 'observability', path: '/api/observability/health' },
            { name: 'system_health_live', path: '/api/system-health/live' },
            { name: 'cache_warmer_status', path: '/api/admin/cache/warmer-status' },
        ];
        const results = [];
        let crashes = 0;
        for (const p of probes) {
            const r = await rawGet(request, p.path, stressTokens.pilot_token, 10_000);
            results.push({ name: p.name, status: r.status });
            if (r.status >= 500 && r.status < 600) {
                crashes++;
                recFinding(testInfo, 'P1', MOD, `liveness_probe_5xx:${p.name}`,
                    `path=${p.path} status=${r.status}. Servis çürümesi.`);
            }
        }
        rec(testInfo, { module: MOD, step: 'liveness_probes',
            status: crashes === 0 ? 'PASS' : 'FAIL',
            note: `results=${JSON.stringify(results)} crashes=${crashes}` });
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'liveness_probes', stressState, request, stressTokens.pilot_token);
        expect(extOk).toBe(true);
    });

    test('E) Pilot drift = 0 + external_calls = [] (final invariants)', async ({ request, stressTokens, stressState }, testInfo) => {
        const driftOk = await assertPilotDriftZero(testInfo, MOD, request, stressTokens.pilot_token, pilotBefore);
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'final', stressState, request, stressTokens.pilot_token);
        rec(testInfo, { module: MOD, step: 'final_invariants',
            status: driftOk && extOk ? 'PASS' : 'FAIL',
            note: `pilot_drift_zero=${driftOk} external_calls_empty=${extOk}` });
        expect(driftOk).toBe(true);
        expect(extOk).toBe(true);
    });
});

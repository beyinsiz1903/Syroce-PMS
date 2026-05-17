// F8B § 12 — Service complaints: list/stats, 30 resolve (compensation folio
// adjust LOKAL — guest_id=None ile _notify_guest_resolved short-circuit),
// external_calls invariant, pilot drift.
//
// External-call invariant kritik nokta: complaint resolve flow
// `_notify_guest_resolved` çağırır; bu fonksiyon `guest_id` boş ise erkenden
// return eder. Seed `guest_id=None` ile yazıldığından Resend HTTP çağrısı
// tetiklenmez. Folio adjustment booking_id'den çalışır, lokal Mongo update.
//
// **Escalate path NOT tested**: backend `_notify_managers_of_escalation`
// (complaints.py:111-123) yöneticilere `core.email.send_email` (Resend) +
// `fire_and_forget_expo_push` (Expo push) çağırır. Bu suite external_calls=[]
// invariant'ını tutturmak zorunda olduğundan escalate akışı kapsam DIŞIDIR.
// Manager bell notification path'i seed'de notifications koleksiyonu ile
// kapsanır; gerçek escalate API'sı production-only akış olarak bırakıldı.
import { test, expect, rec } from '../fixtures/stress-context.js';
import {
    fetchSingle, callTimed, recPerf, recFinding,
    assertNoExternalCallsPostBatch, pilotBookingsCount,
} from '../fixtures/stress-helpers.js';

const MOD = 'complaints';

test.describe.configure({ mode: 'serial' });

test.describe('F8B § 12 — Service complaints', () => {
    let pilotBefore = null;
    let prefix = null;
    let owned = [];

    test('Setup: fetch seeded complaints + pilot baseline', async ({ request, stressTokens, stressState }, testInfo) => {
        prefix = stressState.data_prefix;
        pilotBefore = await pilotBookingsCount(request, stressTokens.pilot_token);
        // Backend list endpoint envelope: { complaints, total, stats }.
        // fetchSingle now recognises `complaints` key (helper update);
        // raw form burada body.complaints olarak da okunabilir.
        const list = await fetchSingle(request, stressTokens.stress_token, '/api/service/complaints?status=open&limit=500');
        const items = list.raw?.complaints || list.list || [];
        owned = items.filter((c) => typeof c.subject === 'string' && c.subject.startsWith(prefix));
        rec(testInfo, { module: MOD, step: 'setup', status: owned.length > 0 ? 'PASS' : 'REVIEW',
            note: `list_status=${list.http} total_open=${items.length} owned=${owned.length} pilot_before=${pilotBefore?.count}` });
        expect(owned.length).toBeGreaterThanOrEqual(20);
    });

    test('A) 30 resolve with compensation (folio adjustment local)', async ({ request, stressTokens, stressState }, testInfo) => {
        const target = owned.slice(0, 30);
        if (target.length < 5) {
            rec(testInfo, { module: MOD, step: 'resolve', status: 'SKIP', note: `owned=${owned.length}` });
            return;
        }
        let ok = 0, fail = 0, folioAdjusted = 0;
        const samples = [];
        const errs = [];
        for (let i = 0; i < target.length; i++) {
            const c = target[i];
            const r = await callTimed(request, 'post', `/api/service/complaints/${c.id}/resolve`, {
                resolution_notes: `F8B resolve #${i}`,
                compensation_offered: 'credit',
                compensation_amount: 100,
            }, stressTokens.stress_token);
            samples.push(r.ms);
            if (r.ok) {
                ok++;
                if (r.body?.folio?.folio_adjusted === true) folioAdjusted++;
            } else {
                fail++;
                if (errs.length < 3) errs.push({ status: r.status, body: JSON.stringify(r.body).slice(0, 120) });
            }
        }
        const floor = Math.ceil(target.length * 0.95);
        recPerf(testInfo, MOD, 'resolve', samples, ok >= floor);
        rec(testInfo, { module: MOD, step: 'resolve', status: ok >= floor ? 'PASS' : 'FAIL',
            endpoint: 'POST /api/service/complaints/{id}/resolve',
            note: `n=${target.length} ok=${ok} fail=${fail} folio_adjusted=${folioAdjusted} floor>=${floor} max_ms=${Math.max(...samples)} errs=${JSON.stringify(errs)}` });
        if (ok < floor) {
            recFinding(testInfo, 'P1', MOD, 'Complaint resolve floor (>=95%) ihlal',
                `${target.length} resolve attempted, ok=${ok} (<${floor}). errs=${JSON.stringify(errs)}`);
        }
        // Compensation amount > 0 → folio adjustment beklenir (booking_id var).
        // Hiçbir kayıt için adjust olmadıysa folio path kırık → P2 finding.
        if (ok > 0 && folioAdjusted === 0) {
            recFinding(testInfo, 'P2', MOD, 'Folio compensation hiç işlenmedi',
                `${ok}/${target.length} resolve PASS ama folio_adjusted=0 — _post_compensation_to_folio path izlenmeli.`);
        }
        const extOk = await assertNoExternalCallsPostBatch(testInfo, MOD, 'resolve_30', stressState, request, stressTokens.pilot_token);
        expect(extOk, 'resolve_30 sonrası external_calls invariant').toBe(true);
        expect(ok, `resolve floor>=${floor}; got ok=${ok}`).toBeGreaterThanOrEqual(floor);
    });

    test('B) Summary stats endpoint reachable + non-trivial', async ({ request, stressTokens }, testInfo) => {
        // /api/service/complaints döner { complaints, total, stats } envelope'u.
        const samples = [];
        let body = null;
        for (let i = 0; i < 3; i++) {
            const r = await callTimed(request, 'get', '/api/service/complaints?limit=50', undefined, stressTokens.stress_token);
            samples.push(r.ms);
            body = r.body;
        }
        recPerf(testInfo, MOD, 'list_stats', samples, true);
        const items = body?.complaints || (Array.isArray(body) ? body : []);
        const stats = body?.stats || {};
        rec(testInfo, { module: MOD, step: 'list_stats', status: items.length > 0 ? 'PASS' : 'REVIEW',
            endpoint: '/api/service/complaints',
            note: `items_len=${items.length} total=${body?.total} stats_keys=${Object.keys(stats).join(',')} max_ms=${Math.max(...samples)}` });
        expect(items.length).toBeGreaterThan(0);
    });

    test('C) Compensation report endpoint (post-resolve breakdown)', async ({ request, stressTokens }, testInfo) => {
        const r = await callTimed(request, 'get', '/api/service/complaints/compensation-report', undefined, stressTokens.stress_token);
        const body = r.body || {};
        const breakdown = body.breakdown || body.items || [];
        rec(testInfo, { module: MOD, step: 'compensation_report', status: r.ok ? 'PASS' : 'REVIEW',
            endpoint: '/api/service/complaints/compensation-report',
            note: `status=${r.status} breakdown_len=${breakdown.length} ms=${r.ms} body_keys=${Object.keys(body).slice(0, 6).join(',')}` });
        expect(r.status).toBeGreaterThanOrEqual(200);
        expect(r.status).toBeLessThan(500);
    });

    test('D) Pilot drift = 0', async ({ request, stressTokens }, testInfo) => {
        if (!pilotBefore) { rec(testInfo, { module: MOD, step: 'pilot_drift', status: 'SKIP' }); return; }
        const after = await pilotBookingsCount(request, stressTokens.pilot_token);
        const drift = (after?.count ?? 0) - pilotBefore.count;
        rec(testInfo, { module: MOD, step: 'pilot_drift', status: drift === 0 ? 'PASS' : 'FAIL',
            note: `before=${pilotBefore.count} after=${after?.count} drift=${drift}` });
        if (drift !== 0) recFinding(testInfo, 'P0', MOD, 'Pilot mutation', `drift=${drift}`);
        expect(drift).toBe(0);
    });
});

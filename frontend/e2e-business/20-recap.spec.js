import fs from 'node:fs';
import path from 'node:path';
import { test } from '@playwright/test';
import { rec, PASS, REVIEW, FAIL } from './fixtures/recorder.js';
import { listEntities } from './fixtures/data-factory.js';
import { makeApi, safePost } from './fixtures/api.js';

const REGISTRY_FILE = path.join(process.cwd(), 'e2e-business', '.auth', 'data-registry.json');

function saveRegistry(r) {
    fs.mkdirSync(path.dirname(REGISTRY_FILE), { recursive: true });
    fs.writeFileSync(REGISTRY_FILE, JSON.stringify(r, null, 2));
}

// Bu spec sondadır — test envanterini raporlar VE pending cleanup'ları kapatır.
// 03/04/05 spec'leri trackEntity(...) ile booking/charge id'lerini biriktirir;
// burada her pending entity'i hedef endpoint'iyle silmeye çalışırız.
test('Scope 20 — Test verileri özetleme + cleanup pass', async ({ baseURL }, testInfo) => {
    const entities = listEntities();
    rec(testInfo, { module: 'recap', scope: 20, step: 'Toplam oluşturulan entity', status: PASS, note: `count=${entities.length}` });

    // Aynı entity id'si birden fazla turda track edilebilir (pending → completed).
    // En son state'i kabul et: id+kind bazında son kayıt belirler.
    const latest = new Map();
    for (const e of entities) latest.set(`${e.kind}:${e.id}`, e);
    const pending = [...latest.values()].filter((e) => e.cleanup === 'pending');
    rec(testInfo, { module: 'recap', scope: 20, step: 'Cleanup pending (run-bazlı)', status: pending.length === 0 ? PASS : REVIEW, note: `count=${pending.length}` });

    if (pending.length === 0) return;

    // Safety guard: yalnız E2E_ prefix taşıyan label'lı entity'ler hedeflenir.
    // trackEntity() spec'lerden factory.guestName/folioLabel ile çağrılır
    // (E2E_<ts>_GUEST / _FOLIO); herhangi bir label E2E_ ile başlamıyorsa
    // recap o satırı atlar (insan-eli veya başka path'in eklediği veriye
    // dokunmama garantisi).
    const PREFIX_RE = /(^|\s|\()E2E_/;
    const api = await makeApi(baseURL);
    let okCount = 0;
    let failCount = 0;
    let skippedNonE2E = 0;
    const updated = [...entities];

    for (const e of pending) {
        if (!e.label || !PREFIX_RE.test(e.label)) {
            skippedNonE2E++;
            rec(testInfo, {
                module: 'recap', scope: 20,
                step: `Cleanup atlandı (non-E2E label) ${e.kind} ${e.id}`,
                status: REVIEW, note: `label="${e.label || ''}" — prefix guard tetiklendi`,
            });
            continue;
        }
        let r;
        if (e.kind === 'booking') {
            r = await safePost(api, e.endpoint || '/api/pms-core/cancel', { booking_id: e.id, reason: 'E2E recap cleanup' });
        } else if (e.kind === 'extra_charge') {
            r = await safePost(api, e.endpoint || '/api/pms-core/folio/void-charge', { charge_id: e.id, reason: 'E2E recap cleanup' });
        } else {
            r = { ok: false, status: 0, body: `unknown kind=${e.kind}` };
        }
        const ok = r.ok && r.json?.success !== false;
        rec(testInfo, {
            module: 'recap', scope: 20,
            step: `Cleanup ${e.kind} ${e.label || e.id}`,
            status: ok ? PASS : REVIEW,
            endpoint: e.endpoint, http: r.status,
            note: ok ? 'cleaned' : (r.body?.slice(0, 200) || r.error || ''),
        });
        if (ok) okCount++; else failCount++;
        updated.push({ ...e, cleanup: ok ? 'completed' : 'failed', cleanedAt: new Date().toISOString() });
    }

    saveRegistry({ entities: updated });
    rec(testInfo, {
        module: 'recap', scope: 20, step: 'Cleanup özeti',
        status: failCount === 0 ? PASS : (okCount > 0 ? REVIEW : FAIL),
        note: `ok=${okCount} fail=${failCount} skipped_non_e2e=${skippedNonE2E}`,
    });
    await api.dispose();
});

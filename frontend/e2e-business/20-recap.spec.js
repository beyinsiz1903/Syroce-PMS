import { test } from '@playwright/test';
import { rec, PASS, REVIEW } from './fixtures/recorder.js';
import { listEntities } from './fixtures/data-factory.js';

// Bu spec sondadır — yalnız test-data envanterini raporlayan no-op test.
test('Scope 20 — Test verileri özetleme + cleanup notu', async ({}, testInfo) => {
    const entities = listEntities();
    rec(testInfo, { module: 'recap', scope: 20, step: 'Toplam oluşturulan entity', status: PASS, note: `count=${entities.length}` });
    const pendingCleanup = entities.filter((e) => e.cleanup === 'pending');
    rec(testInfo, { module: 'recap', scope: 20, step: 'Cleanup pending', status: pendingCleanup.length === 0 ? PASS : REVIEW, note: `count=${pendingCleanup.length}` });
});

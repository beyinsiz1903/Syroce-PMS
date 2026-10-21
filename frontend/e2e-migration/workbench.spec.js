/* global document, window */
import { Buffer } from 'node:buffer';
import { URL } from 'node:url';
import { expect, test } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  await page.route('**/*', route => {
    const host = new URL(route.request().url()).hostname;
    return host === '127.0.0.1' ? route.continue() : route.abort();
  });
  let batch = null;
  const report = { rows: 1, error_count: 0, errors: [], warnings: [{ message: 'Kaynak mutabakatı tamamlanmadı.' }], datasets: [{ dataset_id: 'd1', entity: 'guests', rows: 1, create: 1, reuse: 0, totals: {}, unmapped_columns: [] }], all_source_reconciled: false, active_reservations_archive_only: 0 };
  await page.route('**/api/data-migration/**', async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    let data;
    if (path.endsWith('/schema')) data = { entities: { guests: { fields: ['source_id', 'name', 'email'], required: ['source_id', 'name'] } } };
    else if (path.endsWith('/api-sources')) data = { items: [] };
    else if (path.endsWith('/cutover')) data = null;
    else if (path.endsWith('/mapping-templates')) data = { items: [] };
    else if (path.endsWith('/batches') && request.method() === 'GET') data = { items: batch ? [batch] : [], total: batch ? 1 : 0 };
    else if (path.endsWith('/batches')) data = batch = { ...request.postDataJSON(), id: 'b1', datasets: [], revision: 1, state: 'draft', cursor: 0 };
    else if (path.endsWith('/files')) data = batch = { ...batch, revision: 2, datasets: [{ id: 'd1', entity: 'guests', row_count: 1, headers: ['source_id', 'name', 'email'], mapping: { source_id: 'source_id', name: 'name', email: 'email' }, date_format: '%Y-%m-%d', decimal_separator: '.', value_mapping: {}, guest_links: {} }] };
    else if (path.includes('/datasets/') && request.method() === 'PUT') data = batch = { ...batch, revision: batch.revision + 1, state: 'draft', datasets: [{ ...batch.datasets[0], ...request.postDataJSON() }] };
    else if (path.endsWith('/review')) data = batch = { ...batch, state: 'reviewed', report, review_token: 'a'.repeat(64) };
    else if (path.endsWith('/commit')) data = batch = { ...batch, state: 'complete', cursor: 1 };
    else if (path.endsWith('/rollback')) data = batch = { ...batch, state: 'rolled_back' };
    else if (path.endsWith('/archive')) data = { total: 1, offset: 0, limit: 25, items: [{ id: 'a'.repeat(64), entity: 'guests', namespace: 'old-pms', owner_batch_id: 'b1', batch_state: 'complete', data: { source_id: 'g1', name: 'Yapay Misafir', email: 'synthetic@example.invalid' }, refs: {} }] };
    else if (path.endsWith('/batches/b1')) data = batch;
    else throw new Error(`Unexpected route: ${path}`);
    await route.fulfill({ json: data });
  });
  await page.goto('/e2e-migration/workbench.html');
});

async function prepare(page) {
  await page.getByLabel('Kaynak PMS / dosya açıklaması').fill('Herhangi bir eski PMS');
  await page.getByLabel('Kalıcı kaynak anahtarı').fill('old-pms');
  await page.getByRole('button', { name: /Yeni aktarım oluştur/ }).click();
  await page.getByLabel('Dosya', { exact: true }).setInputFiles({ name: 'synthetic-guests.csv', mimeType: 'text/csv', buffer: Buffer.from('source_id,name,email\ng1,Yapay Misafir,synthetic@example.invalid') });
  await page.getByRole('button', { name: 'Dosyayı ekle' }).click();
  await expect(page.getByText('Misafirler · 1 satır')).toBeVisible();
}

test('upload, map, review, acknowledge, archive and controlled rollback', async ({ page }) => {
  await prepare(page);
  await page.getByLabel('Kaynak raporundaki kayıt sayısı').fill('1');
  await page.getByRole('button', { name: 'Eşleştirmeyi kaydet', exact: true }).click();
  await page.getByRole('button', { name: '3. Deneme aktarımı ve mutabakat' }).click();
  await expect(page.getByRole('button', { name: '4. Onayla ve aktar' })).toBeDisabled();
  await page.getByLabel(/Eşleştirmeleri, eksik kaynak/).check();
  await page.getByRole('button', { name: '4. Onayla ve aktar' }).click();
  await expect(page.getByText(/Arşiv aktarımı tamamlandı. Oda takvimi/)).toBeVisible();
  await expect(page.getByRole('heading', { name: '5. Ayrı onaylı canlı devir' })).toBeVisible();
  await expect(page.getByRole('button', { name: /Canlı devir ayarlarını kaydet/ })).toBeDisabled();
  await page.getByText('Kontrollü arşiv geri alma').click();
  await page.getByLabel('ARSIVI GERI AL yazın').fill('ARSIVI GERI AL');
  await page.getByRole('button', { name: 'Bu arşiv aktarımını geri al' }).click();
  await expect(page.getByRole('heading', { name: /Geri alındı/ })).toBeVisible();
});

test('archive details and linked record navigation remain readable without overflow', async ({ page }, testInfo) => {
  await page.getByRole('button', { name: 'Geçmiş veri arşivi' }).click();
  await page.getByRole('button', { name: 'Arşivi getir' }).click();
  await page.getByRole('button', { name: 'Kaydı incele' }).click();
  await expect(page.getByRole('region', { name: 'Arşiv kayıt detayı' })).toContainText('synthetic@example.invalid');
  await page.getByRole('button', { name: 'Bağlı alt kayıtları getir' }).click();
  await expect(page.getByText(/Bağlantılı alt kayıtlar gösteriliyor/)).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('synthetic-archive.png'), fullPage: true });
});

test('mapping form fits small screens and never auto-imports', async ({ page }, testInfo) => {
  const mutations = [];
  page.on('request', request => { if (request.method() === 'POST') mutations.push(request.url()); });
  await prepare(page);
  await page.getByText('Kod eşleştirme, kontrol toplamları ve mevcut misafir bağlantıları').click();
  await expect(page.getByLabel('Durum / tür / döviz kodları (JSON)')).toBeVisible();
  expect(mutations.some(url => url.endsWith('/commit'))).toBe(false);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('synthetic-mapping.png'), fullPage: true });
});

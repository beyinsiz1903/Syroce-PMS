import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
  page.miceErrors = [];
  page.on('pageerror', error => page.miceErrors.push(error.message));
  await page.goto('/e2e-local/mice.html');
  await expect(page.getByRole('heading', { name: 'MICE & Banquet' })).toBeVisible();
});

test.afterEach(async ({ page }) => { expect(page.miceErrors).toEqual([]); });

test('venue add edit and keyboard dialog close', async ({ page }, testInfo) => {
  await page.getByRole('tab', { name: /Mekanlar/ }).click();
  await page.getByRole('button', { name: 'Yeni Mekan', exact: true }).click();
  await page.getByLabel('Mekan adı', { exact: true }).fill('Yapay Test Salonu');
  await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
  await expect(page.getByText('Yapay Test Salonu', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Yapay Test Salonu düzenle' }).click();
  await page.getByLabel('Mekan adı', { exact: true }).fill('Güncel Test Salonu');
  await page.getByRole('button', { name: 'Kaydet', exact: true }).click();
  await expect(page.getByText('Güncel Test Salonu', { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('mice-venues.png'), fullPage: true });
  await page.getByRole('button', { name: 'Güncel Test Salonu düzenle' }).click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('dialog')).not.toBeVisible();
});

test('new event and server quote are connected', async ({ page }, testInfo) => {
  await page.getByRole('button', { name: 'Yeni Etkinlik', exact: true }).click();
  await page.getByLabel('Etkinlik Adı', { exact: true }).fill('Örnek Düğün');
  await page.getByLabel('Müşteri Adı', { exact: true }).fill('Yapay Müşteri');
  await page.getByLabel('Başlangıç Tarihi', { exact: true }).fill('2026-11-01');
  await page.getByLabel('Bitiş Tarihi', { exact: true }).fill('2026-11-01');
  await page.getByRole('button', { name: 'Tutarı Hesapla' }).click();
  await expect(page.getByText('Hesaplanan satış bedeli:', { exact: false })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('mice-event-form.png'), fullPage: true });
  await page.getByRole('button', { name: 'Oluştur', exact: true }).click();
  await expect(page.getByRole('dialog')).not.toBeVisible();
  expect(await page.evaluate(() => window.__miceCalls.some(c => c.method === 'post' && c.url === '/mice/events'))).toBe(true);
});

test('readiness issues and filters are actionable', async ({ page }, testInfo) => {
  await page.getByRole('tab', { name: 'Operasyon Kontrolü' }).click();
  await expect(page.getByText('Mekan / saat planı eksik', { exact: true })).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('mice-readiness.png'), fullPage: true });
  await page.getByRole('button', { name: 'Etkinliği aç' }).click();
  await expect(page.getByRole('dialog')).toBeVisible();
  await page.keyboard.press('Escape');
  await page.getByRole('tab', { name: 'Etkinlikler', exact: true }).click();
  await page.getByRole('combobox', { name: 'Etkinlik durumu filtresi' }).selectOption('lead');
  await page.getByRole('button', { name: 'Filtrele', exact: true }).click();
  expect(await page.evaluate(() => window.__miceCalls.filter(c => c.url === '/mice/events').length)).toBeGreaterThan(1);
});

test('customer approval requires name and consent', async ({ page }, testInfo) => {
  await page.goto('/e2e-local/mice.html?public=1');
  await expect(page.getByRole('heading', { name: 'Etkinlik detayları ve müşteri onayı' })).toBeVisible();
  const action = page.getByRole('button', { name: 'Etkinliği onayla' });
  await expect(action).toBeDisabled();
  await page.getByLabel('Onaylayan ad soyad').fill('Yapay Müşteri');
  await page.getByRole('checkbox').check();
  await page.screenshot({ path: testInfo.outputPath('mice-customer-approval.png'), fullPage: true });
  await action.click();
  await expect(page.getByText('Müşteri onayı kaydedildi. Teşekkür ederiz.')).toBeVisible();
});

test('BEO print isolates the document and hides actions', async ({ page }, testInfo) => {
  await page.getByTitle('BEO', { exact: true }).click();
  const document = page.getByRole('dialog');
  await expect(document).toBeVisible();
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('#root')).not.toBeVisible();
  await expect(document).toBeVisible();
  await expect(document.getByRole('button', { name: 'PDF İndir' })).not.toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('mice-beo-print.png'), fullPage: true });
});

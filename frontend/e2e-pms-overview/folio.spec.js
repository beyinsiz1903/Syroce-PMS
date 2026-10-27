import { expect, test } from '@playwright/test';

test('guest card, service times, payer-safe food print and contextual offer', async ({ page }, testInfo) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
  await page.goto('/e2e-pms-overview/folio.html');
  await expect(page.getByTestId('reservation-workspace-overview')).toBeVisible();
  await expect(page.getByText(/Girişten 7 gün öncesine kadar ücretsiz iptal/)).toBeVisible();
  await page.getByTestId('workspace-folios').click();
  const account = page.getByTestId('window-row-1');
  await expect(account).toBeVisible();
  await expect(account).toContainText('638,80');
  const balance = account.locator('p.tabular-nums');
  expect(await balance.evaluate(node => node.scrollWidth <= node.clientWidth)).toBe(true);
  await account.getByRole('button', { name: 'Bu folyoyu seç' }).click();
  await expect(page.getByTestId('folios-tab').getByText('25.10.2026 · 14:30 (randevu)')).toBeVisible();
  await expect(page.getByTestId('folios-tab').getByText('Hizmet tarihi belirtilmemiş')).toBeVisible();
  await page.screenshot({ path: testInfo.outputPath('folio-workspace.png'), fullPage: true });
  await page.getByTestId('btn-folyo-yazdir').click();
  await page.getByLabel('Hizmet kapsamı').selectOption('food_beverage');
  await page.getByRole('button', { name: 'Çıktıyı önizle' }).click();
  const print = page.getByRole('dialog', { name: 'Folyo yazdırma önizlemesi' });
  await expect(print).toContainText('24.10.2026 · 19:30');
  await expect(print).toContainText('Akşam yemeği');
  await expect(print).not.toContainText(/Gizli acente|Konaklama ·|638,80|9.900|Kalan bakiye|Net tahsilat/);
  await expect(print).toContainText('$16,40');
  expect(await print.evaluate(node => node.parentElement === document.body)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('food-only-preview.png'), fullPage: true });
  if (testInfo.project.name === 'desktop') {
    await page.emulateMedia({ media: 'print' });
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    expect(await print.locator('h1').evaluate(node => getComputedStyle(node).color)).toBe('rgb(15, 23, 42)');
    await expect(print.getByTestId('print-folio')).toBeHidden();
    await page.pdf({ path: testInfo.outputPath('food-only.pdf'), format: 'A4', printBackground: true });
    await page.evaluate(() => document.documentElement.classList.remove('dark'));
    await page.emulateMedia({ media: 'screen' });
  }
  await print.getByRole('button', { name: 'Kapat', exact: true }).click();
  // Close the reservation card via its explicit close control, then inspect 360.
  await page.getByTestId('close-reservation-detail').click();
  await expect(page.getByText('Konaklama tutarı toplamı')).toBeVisible();
  await expect(page.getByText('Yaşam Boyu Değer')).toHaveCount(0);
  await page.getByRole('button', { name: 'Teklif Gönder' }).click();
  await expect(page.getByText('Misafire teklif taslağı')).toBeVisible();
  await expect(page.getByTestId('send-recipient')).toHaveValue('deniz@example.com');
  await expect(page.getByTestId('send-message-btn')).toBeDisabled();
  await expect(page.getByRole('button', { name: /Ön büroya dön/ })).toBeVisible();
  const tabs = await page.getByTestId('messaging-tabs').boundingBox();
  const context = await page.getByTestId('message-guest-context').boundingBox();
  expect(tabs.y + tabs.height).toBeLessThanOrEqual(context.y);
  await page.screenshot({ path: testInfo.outputPath('offer-draft.png'), fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  if (testInfo.project.name === 'desktop') {
    await page.goto('/e2e-pms-overview/folio.html?long=1');
    await page.getByTestId('workspace-folios').click();
    await page.getByTestId('btn-folyo-yazdir').click();
    await page.getByLabel('Hizmet kapsamı').selectOption('food_beverage');
    await page.getByRole('button', { name: 'Çıktıyı önizle' }).click();
    const longPrint = page.getByRole('dialog', { name: 'Folyo yazdırma önizlemesi' });
    await expect(longPrint.locator('tbody tr')).toHaveCount(102);
    await expect(longPrint).toContainText('Yapay yemek kalemi 100');
    await page.emulateMedia({ media: 'print' });
    await expect(page.getByTestId('reservation-detail-modal')).toBeHidden();
    await page.pdf({ path: testInfo.outputPath('long-food-only.pdf'), format: 'A4', printBackground: true });
  }
  expect(errors).toEqual([]);
});

import { expect, test } from '@playwright/test';

test('compact exact monetary cards and selectable stay proximity', async ({ page }, testInfo) => {
  await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
  await page.goto('/e2e-pms-overview/overview.html');
  const revenue = page.getByTestId('booking-revenue-summary');
  const adr = page.getByTestId('booking-adr-summary');
  await expect(revenue).toContainText('₺13.440.337,96');
  await expect(adr).toContainText('₺31.402,66');
  for (const card of [revenue, adr]) {
    const size = await card.boundingBox();
    expect(size.height).toBeLessThan(160);
    expect(await card.locator('dd').evaluateAll(nodes => nodes.every(node => node.scrollWidth <= node.clientWidth))).toBe(true);
    expect(await card.locator('dd').first().evaluate(node => parseFloat(getComputedStyle(node).fontSize))).toBeLessThanOrEqual(14);
  }
  const detailButtons = page.getByRole('button', { name: /detayını aç/ });
  await expect(detailButtons.first()).toHaveAccessibleName('Selin Demir detayını aç');
  await page.getByRole('combobox', { name: 'Sıralama' }).selectOption('farthest');
  await expect(detailButtons.first()).toHaveAccessibleName('Ali Kılıç detayını aç');
  await page.getByRole('button', { name: /Atanmamış/ }).click();
  await expect(detailButtons).toHaveCount(1);
  await expect(detailButtons.first()).toHaveAccessibleName('Selin Demir detayını aç');
  await expect(revenue).toContainText('₺13.440.337,96');
  const dates = await page.getByTestId('stay-dates-today').boundingBox();
  const amount = await page.getByTestId('stay-amount-today').boundingBox();
  expect(dates.x + dates.width <= amount.x || amount.x + amount.width <= dates.x || dates.y + dates.height <= amount.y || amount.y + amount.height <= dates.y).toBe(true);
  await page.getByRole('combobox', { name: 'Sıralama' }).selectOption('nearest');
  await page.getByRole('button', { name: 'Tümü (3)' }).click();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath('overview.png'), fullPage: true });
});

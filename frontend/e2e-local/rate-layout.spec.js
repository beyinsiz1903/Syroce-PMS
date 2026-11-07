/* global window, document, innerWidth, getComputedStyle */
import { URL } from 'node:url';
import { test, expect } from '@playwright/test';

const fields = ['rate', 'availability', 'min_stay', 'min_los_arrival', 'max_stay', 'cta', 'ctd', 'stop_sell'];
const ids = ['rate-input', 'avail-input', 'min-stay-input', 'min-los-arrival-input', 'max-stay-input', 'cta', 'ctd', 'stop-sell'];
const noOverflow = async page => {
  const targets = page.getByTestId('bulk-update-layout').locator('div');
  const overflow = await targets.evaluateAll(elements => elements.filter(element => {
    const rect = element.getBoundingClientRect();
    return rect.width > 0 && element.scrollWidth > element.clientWidth + 1
      && ['auto', 'scroll'].includes(getComputedStyle(element).overflowX);
  }).map(element => ({ testId: element.getAttribute('data-testid'), width: element.clientWidth, scroll: element.scrollWidth })));
  expect(overflow, 'no nested horizontal scroller may hide room fields').toEqual([]);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
};

for (const width of [1024, 1280, 1324, 1440]) {
  test(`all selected rate fields fit the actual page at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    await page.goto('/e2e-local/rate-layout.html');
    await expect(page.getByTestId('room-type-check-STD')).toBeVisible();
    for (let index = 0; index < fields.length; index += 1) {
      await page.getByTestId(`field-${fields[index]}`).click();
      await noOverflow(page);
      for (const id of ids.slice(0, index + 1)) {
        const field = page.getByTestId(`${id}-STD`);
        await expect(field).toBeVisible();
        const inRoom = await field.evaluate(element => {
          const field = element.getBoundingClientRect();
          const room = element.closest('[data-testid="room-type-list"]').getBoundingClientRect();
          return field.left >= room.left && field.right <= room.right + 1;
        });
        expect(inRoom, `${id} must fit without scrolling sideways`).toBe(true);
      }
      if ([1, 3, 7].includes(index)) await page.screenshot({ path: testInfo.outputPath(`${index + 1}-fields-${width}.png`), fullPage: true });
    }
    await page.getByTestId('room-type-check-STD').click();
    await expect(page.getByTestId('rate-plan-row-STD-BASE')).toBeVisible();
    await noOverflow(page);
    await page.getByTestId('occupancy-pricing-STD').getByRole('button', { name: 'Kuralı düzenle' }).click();
    await noOverflow(page);
    await expect(page.getByRole('tab', { name: 'Exely tarifeleri' })).toBeVisible();
    await page.getByTestId('rate-input-STD').fill('125');
    await page.getByTestId('avail-input-STD').fill('0');
    await page.getByTestId('min-stay-input-STD').fill('0');
    await page.getByTestId('cta-STD').check();
    await page.getByTestId('room-type-check-DLX').click();
    await page.getByTestId('room-type-row-STD').getByTestId('apply-all-rate').click();
    await expect(page.getByTestId('rate-input-DLX')).toHaveValue('125');
    await page.getByTestId('field-rate').click();
    await page.getByTestId('field-rate').click();
    await expect(page.getByTestId('rate-input-STD')).toHaveValue('125');
    await expect(page.getByTestId('avail-input-STD')).toHaveValue('0');
    await expect(page.getByTestId('min-stay-input-STD')).toHaveValue('0');
    await expect(page.getByTestId('cta-STD')).toBeChecked();
    await noOverflow(page);
    expect(await page.evaluate(() => window.__rateLayoutWrites)).toEqual([]);
    expect(errors).toEqual([]);
  });
}

for (const width of [320, 390, 820]) {
  test(`mobile wizard keeps all ARI fields in the page at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    await page.goto('/e2e-local/rate-layout.html');
    await page.getByTestId('rate-preset-all_ari').click();
    await page.getByTestId('rate-mobile-next').click();
    for (const id of ids) await expect(page.getByTestId(`${id}-STD`)).toBeVisible();
    await page.getByTestId('room-type-check-STD').click();
    await noOverflow(page);
    await page.getByTestId('occupancy-pricing-STD').getByRole('button', { name: 'Kuralı düzenle' }).click();
    await expect(page.getByRole('tab', { name: 'Exely tarifeleri' })).toBeVisible();
    await noOverflow(page);
    await page.screenshot({ path: testInfo.outputPath(`mobile-all-fields-${width}.png`), fullPage: true });
    expect(await page.evaluate(() => window.__rateLayoutWrites)).toEqual([]);
    expect(errors).toEqual([]);
  });
}

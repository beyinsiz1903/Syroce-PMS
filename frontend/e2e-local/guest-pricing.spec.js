import { test, expect } from '@playwright/test';

for (const width of [320, 390, 1440]) {
  test(`guest pricing fits ${width}px with explicit units and preserved drafts`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // No connection to PMS or Exely may be made by this synthetic fixture.
    await page.route('**/*', route => new URL(route.request().url()).hostname === '127.0.0.1' ? route.continue() : route.abort());
    await page.goto('/e2e-local/guest-pricing.html');
    const editor = page.getByTestId('occupancy-pricing-DEMO');
    await expect(editor.getByRole('heading', { name: /Exely’ye gönderilecek fiyatlar/ })).toBeVisible();
    await expect(page.getByTestId('exely-placement-preview')).toContainText('1 yetişkin: 80 USD');
    await expect(page.getByTestId('exely-placement-preview')).toContainText('7–11 yaş çocuk · ek yatak: 10 USD');
    const fits = () => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth);
    expect(await fits()).toBe(true);
    const overflow = await editor.locator('input, select, button').evaluateAll(elements => elements.filter(element => {
      const rect = element.getBoundingClientRect(); return rect.width > 0 && (rect.left < 0 || rect.right > window.innerWidth + 1);
    }).map(element => element.getAttribute('aria-label') || element.textContent));
    expect(overflow).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath(`exely-${width}.png`), fullPage: true });
    await page.getByLabel('1. yerleşim fiyatı').fill('85');
    await expect(page.getByTestId('exely-placements-reviewed')).not.toBeChecked();
    await page.getByRole('tab', { name: 'PMS ek ücretleri' }).click();
    await expect(page.getByTestId('occupancy-preview-DEMO')).toContainText('110 USD');
    await expect(page.getByRole('spinbutton', { name: 'PMS ek yetişkin ücreti' })).toBeVisible();
    expect(await fits()).toBe(true);
    await page.screenshot({ path: testInfo.outputPath(`pms-${width}.png`), fullPage: true });
    await page.getByRole('tab', { name: 'Exely tarifeleri' }).click();
    await expect(page.getByLabel('1. yerleşim fiyatı')).toHaveValue('85');
    await page.getByTestId('exely-placements-reviewed').check();
    await page.getByTestId('save-occupancy-rule-DEMO').click();
    await expect(page.getByTestId('saved-rule')).toContainText('"value":85');
    expect(errors).toEqual([]);
  });
}

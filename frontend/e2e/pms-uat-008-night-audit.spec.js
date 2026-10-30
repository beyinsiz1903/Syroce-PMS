import { test, expect } from '@playwright/test';
import { loginAsDemo } from './fixtures/auth.js';

test.describe('PMS-UAT-008: Night Audit', () => {
    test('loads the authoritative business date and opens the real run confirmation', async ({ page }) => {
        await loginAsDemo(page);
        const businessDateResponse = page.waitForResponse(response =>
            response.url().includes('/api/night-audit/business-date') && response.request().method() === 'GET');
        await page.goto('/night-audit');
        const response = await businessDateResponse;
        expect(response.ok()).toBeTruthy();
        const { business_date: businessDate } = await response.json();
        expect(businessDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        await expect(page.getByTestId('night-audit-title')).toHaveText('Gece Denetimi');
        const runRequests = [];
        page.on('request', request => {
            if (request.method() === 'POST' && /\/night-audit\/run(?:\?|$)/.test(request.url())) runRequests.push(request.url());
        });
        await page.getByTestId('run-audit-btn').click();
        await expect(page.getByRole('dialog')).toBeVisible();
        // Opening the confirmation is never an implicit financial posting.
        // Full close/date-roll is covered by the replica acceptance suite,
        // not against whichever hotel a smoke-test operator is signed into.
        expect(runRequests).toHaveLength(0);
        await page.keyboard.press('Escape');
        await expect(page.getByRole('dialog')).not.toBeVisible();
    });
});

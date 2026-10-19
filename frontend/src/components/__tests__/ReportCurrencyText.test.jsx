import { describe, expect, it } from 'vitest';
import { costText } from '../MaintenanceReports';
import { revenueText } from '../../pages/SpaWellness';

describe('department reports never add currencies on screen', () => {
  it('maintenance costs list each currency', () => {
    const text = costText({ EUR: 100, USD: 100 }, null);
    expect(text).toContain('100');
    expect(text.split(' · ')).toHaveLength(2);
    expect(text).not.toContain('200');
  });

  it('SPA revenue lists each currency', () => {
    const format = (amount, code = 'TRY') => `${amount} ${code}`;
    expect(revenueText({ revenue: null, revenue_by_currency: { EUR: 100, USD: 100 } }, format)).toBe('100 EUR · 100 USD');
    expect(revenueText({ revenue: 50 }, format)).toBe('50 TRY');
  });
});

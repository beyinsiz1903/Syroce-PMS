import { describe, expect, it } from 'vitest';
import { selectFlashCurrency } from '../FlashReportContent';

describe('FlashReportContent currency selection', () => {
  it('never adds unlike currencies and filters reservation detail to the same currency', () => {
    const report = {
      revenue: { total: null, total_by_currency: { TRY: 1000.49, EUR: 20.25 },
        collected_by_currency: { EUR: 5 }, room_revenue_breakdown: [{ currency: 'TRY', daily_rate: 1000.49 }, { currency: 'EUR', daily_rate: 20.25 }] },
      kpi: { adr_by_currency: { EUR: 10.125 }, revpar_by_currency: { EUR: 5.0625 } },
      departments: [{ name: 'Room', amount: null, amount_by_currency: { TRY: 1000.49, EUR: 20.25 } }],
    };
    const eur = selectFlashCurrency(report, 'EUR');
    expect(eur.revenue.total).toBe(20.25);
    expect(eur.revenue.collected).toBe(5);
    expect(eur.revenue.room_revenue_breakdown).toEqual([{ currency: 'EUR', daily_rate: 20.25 }]);
    expect(eur.departments[0].amount).toBe(20.25);
    expect(selectFlashCurrency(report, 'TRY').revenue.total).toBe(1000.49);
    expect(selectFlashCurrency(report, 'TRY').revenue.collected).toBe(0);
    expect(report.revenue.total).toBeNull();
  });

  it('does not invent a TRY total for a mixed-currency report', () => {
    const report = { revenue: { total_by_currency: { EUR: 50 } }, kpi: {} };
    expect(selectFlashCurrency(report, 'TRY').revenue.total).toBe(0);
    expect(selectFlashCurrency(null, 'TRY')).toBeNull();
  });

  it('keeps legacy single-currency payloads usable without fabricating fresh ledger data', () => {
    expect(selectFlashCurrency({ revenue: { total: 100 }, kpi: { adr: 20 } }, 'TRY')).toMatchObject({ revenue: { total: 100 }, kpi: { adr: 20 } });
  });
});

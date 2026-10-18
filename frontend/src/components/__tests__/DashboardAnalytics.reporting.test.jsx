import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import DashboardAnalytics, { reportChartValues } from '../DashboardAnalytics';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

describe('Dashboard reporting charts', () => {
  it('uses the real revenue field and allows a currency choice without summing currencies', () => {
    render(<DashboardAnalytics occupancyData={[]} revenueData={[{ date: '2026-10-01', revenue: null, revenue_by_currency: { EUR: 40, TRY: 1000.49 } }]}
      trendData={[]} formatMoney={String} currencySymbol="₺" />);
    const selector = screen.getByLabelText('Rapor para birimi');
    expect(selector).toHaveValue('EUR');
    expect(screen.getByText(/kur dönüşümü yapılmaz/)).toBeInTheDocument();
    fireEvent.change(selector, { target: { value: 'TRY' } });
    expect(selector).toHaveValue('TRY');
  });

  it('does not display a different currency scalar on days with no sales in the selected currency', () => {
    const rows = [{ date: '1', revenue: 1000, revenue_by_currency: { TRY: 1000 } }, { date: '2', revenue: 40, revenue_by_currency: { EUR: 40 } }];
    expect(reportChartValues(rows, ['revenue'], 'TRY').map(row => row.revenue)).toEqual([1000, 0]);
    expect(reportChartValues(rows, ['revenue'], 'EUR').map(row => row.revenue)).toEqual([0, 40]);
  });
});

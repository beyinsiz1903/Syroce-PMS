import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import PeriodSection from '../PeriodSection';

describe('PeriodSection', () => {
  it('labels one-day comparisons as days instead of falsely claiming seven or thirty-day totals', () => {
    render(<PeriodSection reportPeriod="daily" data={{}} pc={{}} />);
    expect(screen.getByText('Seçili Gün Geliri')).toBeInTheDocument();
    expect(screen.getByText('Önceki Gün Geliri')).toBeInTheDocument();
    expect(screen.getByText('365 Gün Önceki Gün')).toBeInTheDocument();
    expect(screen.getByText('Rezervasyon değişimi (önceki güne göre)')).toBeInTheDocument();
    expect(screen.queryByText('cm.pages_reports_PeriodSection.son_7_gun_gelir')).not.toBeInTheDocument();
  });
  it('compares mixed-currency revenue per currency instead of calculating a false combined percentage', () => {
    render(<PeriodSection
      data={{ revenue_trend: [] }}
      pc={{
        week_revenue: 0,
        week_revenue_by_currency: {},
        week_bookings: 0,
        month_revenue: 300,
        month_revenue_by_currency: { EUR: 200, TRY: 100 },
        month_bookings: 2,
        prev_month_revenue: 50,
        prev_month_revenue_by_currency: { TRY: 50 },
        prev_month_bookings: 1,
        last_year_revenue: 0,
        last_year_revenue_by_currency: {},
        last_year_bookings: 0,
      }}
    />);

    expect(screen.getByText('EUR')).toBeInTheDocument();
    expect(screen.getByText('TRY')).toBeInTheDocument();
    expect(screen.getByText('Yeni gelir')).toBeInTheDocument();
    expect(screen.getAllByText('+100.0%').length).toBeGreaterThan(0);
    expect(screen.queryByText('+500.0%')).not.toBeInTheDocument();
  });
});

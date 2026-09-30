import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ManagerDailyReports from '../ManagerDailyReports';

describe('ManagerDailyReports', () => {
  it('explains negative daily balance as a prior balance collection and does not show a dollar icon', () => {
    render(<ManagerDailyReports
      section="front_cashier"
      reportDate="2026-09-30"
      data={{
        front_cashier: {
          charge_total_by_currency: { TRY: 0 },
          daily_balance_change_by_currency: { TRY: -10000 },
        },
        payments: { totals_by_currency: { TRY: 10000 } },
      }}
    />);

    const section = screen.getByTestId('section-front-cashier');
    expect(within(section).getByText('Önceki bakiyeden tahsilat')).toBeInTheDocument();
    expect(within(section).getAllByText('₺10.000').length).toBeGreaterThan(0);
    expect(within(section).queryByText('-₺10.000')).not.toBeInTheDocument();
    expect(section.querySelectorAll('[data-lucide="dollar-sign"]')).toHaveLength(0);
  });

  it('uses the same canonical room revenue basis for the daily KPI and detail calculations', () => {
    render(<ManagerDailyReports
      section="daily_analysis"
      reportDate="2026-09-30"
      data={{ daily_analysis: {
        date: '2026-09-30',
        revenue_source: 'accrued',
        room_revenue: 5000,
        room_revenue_by_currency: { TRY: 5000 },
        posted_room_revenue: 15000,
        posted_room_revenue_by_currency: { TRY: 15000 },
        adr: 1000,
        adr_by_currency: { TRY: 1000 },
        revpar: 294.12,
        revpar_by_currency: { TRY: 294.12 },
      } }}
    />);

    const section = screen.getByTestId('section-daily-analysis');
    expect(within(section).getAllByText('₺5.000').length).toBeGreaterThanOrEqual(2);
    expect(within(section).getByText('Folyoya işlenen oda geliri')).toBeInTheDocument();
    expect(within(section).getByText('₺15.000')).toBeInTheDocument();
    expect(within(section).getByText(/Gün sonu oda tahakkukları tamamlanmadığı için/)).toBeInTheDocument();
  });
});

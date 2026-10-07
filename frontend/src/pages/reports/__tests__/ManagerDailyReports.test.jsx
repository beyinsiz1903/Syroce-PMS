import React from 'react';
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
    expect(within(section).queryByText('Folyo işlemleri − tahsilatlar')).not.toBeInTheDocument();
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

  it('keeps each currency separate in the balance explanation', () => {
    render(<ManagerDailyReports
      section="front_cashier"
      reportDate="2026-09-30"
      data={{
        front_cashier: {
          daily_balance_change_by_currency: { TRY: -1000, EUR: 50 },
        },
        payments: {},
      }}
    />);

    expect(screen.getByText('Önceki bakiyeden tahsilat')).toBeInTheDocument();
    expect(screen.getByText('Gün içinde oluşan açık bakiye')).toBeInTheDocument();
    expect(screen.getByText('₺1.000')).toBeInTheDocument();
    expect(screen.getByText((text) => text.replace(/\s/g, '') === '50€')).toBeInTheDocument();
  });

  it('labels a zero-value complimentary night as Comp instead of pending night audit', () => {
    render(<ManagerDailyReports
      section="rate_control"
      reportDate="2026-10-01"
      data={{ room_rate_control: [{
        booking_id: 'booking-comp',
        room_number: '207',
        room_type: 'Standart',
        guest_name: 'Comp Misafir',
        agreed_rate: 0,
        posted_rate: 0,
        variance: 0,
        currency: 'TRY',
        posting_status: 'complimentary',
        complimentary_reason: 'Yönetim ikramı',
      }] }}
    />);

    const section = screen.getByTestId('section-rate-control');
    expect(within(section).getByText('Comp')).toBeInTheDocument();
    expect(within(section).getByText('Neden: Yönetim ikramı')).toBeInTheDocument();
    expect(within(section).queryByText('Gün sonu bekliyor')).not.toBeInTheDocument();
  });

  it('shows one TRY total while keeping the received foreign currency in transaction detail', () => {
    render(<ManagerDailyReports
      section="cash_movements"
      reportDate="2026-10-06"
      data={{
        payments: {
          rows: [{ id: 'wrong-accounting-day-row', processed_at: '2026-09-27T10:00:00Z', reporting_amount: 999999 }],
          total_paid: 999999,
        },
        cash_movements: {
        reporting_currency: 'TRY',
        total_paid: 4000,
        conversion_issue_count: 0,
        rows: [{
          id: 'payment-fx',
          processed_at: '2026-10-06T10:00:00Z',
          amount: 4000,
          currency: 'TRY',
          reporting_amount: 4000,
          reporting_currency: 'TRY',
          received_amount: 100,
          received_currency: 'USD',
          exchange_rate: 0.025,
          exchange_rate_date: '2026-10-06',
          method: 'cash',
        }],
        },
      }}
    />);

    const section = screen.getByTestId('section-cash-movements');
    expect(within(section).getAllByText('₺4.000').length).toBeGreaterThan(0);
    expect(within(section).getByText('Nakit')).toBeInTheDocument();
    expect(within(section).queryByText('cash')).not.toBeInTheDocument();
    expect(within(section).queryByText('₺999.999')).not.toBeInTheDocument();
    expect(within(section).getByText(/Alınan:/)).toHaveTextContent('$100');
    expect(within(section).getByText('Toplam tahsilat (işlem günündeki TL karşılığı)')).toBeInTheDocument();
  });
});

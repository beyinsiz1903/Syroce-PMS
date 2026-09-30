import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ManagerDailyReports from '../ManagerDailyReports';

describe('FrontCashierReport', () => {
  it('explains collections from prior balances without presenting them as a negative loss', () => {
    render(<ManagerDailyReports
      section="front_cashier"
      reportDate="2026-09-30"
      data={{
        front_cashier: {
          charge_total: 0,
          charge_total_by_currency: { TRY: 0 },
          daily_balance_change: -10000,
          daily_balance_change_by_currency: { TRY: -10000 },
          net_cash_movement: 0,
          uncollected_charges: 0,
        },
        payments: {
          totals_by_currency: { TRY: 10000 },
          totals_by_method_currency: { bank_transfer: { TRY: 10000 } },
        },
      }}
    />);

    expect(screen.getByText('Önceki bakiyeden tahsilat')).toBeInTheDocument();
    expect(screen.getAllByText('₺10.000').length).toBeGreaterThan(0);
    expect(screen.queryByText('-₺10.000')).not.toBeInTheDocument();
    expect(screen.queryByText('Folyo işlemleri − tahsilatlar')).not.toBeInTheDocument();
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
});

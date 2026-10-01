import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { FnBSection, PaymentsSection } from '../OperationsSection';

afterEach(() => cleanup());

describe('report currency integrity', () => {
  it('does not compare mixed payment currencies in a single pie chart', () => {
    render(
      <PaymentsSection
        reportDate="2026-10-01"
        payments={{
          total_paid: 300,
          totals_by_currency: { TRY: 10000, EUR: 200 },
          totals_by_method_currency: { cash: { TRY: 10000 }, credit_card: { EUR: 200 } },
          rows: [],
        }}
        paymentData={[
          { name: 'Nakit', value: 10000, currency: 'TRY', totals: { TRY: 10000 } },
          { name: 'Kredi Kartı', value: 200, currency: 'EUR', totals: { EUR: 200 } },
        ]}
      />,
    );

    expect(screen.getByText('Farklı para birimleri tek grafikte karşılaştırılmadı.')).toBeInTheDocument();
    expect(screen.getAllByText(/₺10\.000/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/€200/).length).toBeGreaterThan(0);
  });

  it('calculates food and beverage share independently for each currency', () => {
    render(
      <FnBSection
        reportDate="2026-10-01"
        s={{
          fnb_revenue: 250,
          fnb_revenue_by_currency: { TRY: 1000, EUR: 50 },
          today_revenue: 1000,
          today_revenue_by_currency: { TRY: 4000, EUR: 100 },
          today_room_revenue_by_currency: { TRY: 3000, EUR: 50 },
        }}
      />,
    );

    expect(screen.getAllByText('TRY: %25.0 · EUR: %50.0').length).toBeGreaterThan(0);
  });
});

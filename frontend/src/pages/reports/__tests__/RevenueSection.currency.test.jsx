import React from 'react';
import { render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import RevenueSection from '../RevenueSection';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));

describe('RevenueSection category currency handling', () => {
  beforeEach(() => {
    axios.get.mockResolvedValue({
      data: {
        rows: [
          { category: 'room', count: 1, subtotal: 1000, discount: 0, net: 1000, vat: 0, city_tax: 0, total: 1000, by_currency: { TRY: { subtotal: 1000, discount: 0, net: 1000, vat: 0, city_tax: 0, total: 1000 } } },
          { category: 'beverage', count: 1, subtotal: 200, discount: 0, net: 200, vat: 0, city_tax: 0, total: 200, by_currency: { EUR: { subtotal: 200, discount: 0, net: 200, vat: 0, city_tax: 0, total: 200 } } },
        ],
        totals: { count: 2, subtotal: 1200, discount: 0, net: 1200, vat: 0, city_tax: 0, total: 1200 },
        totals_by_currency: {
          TRY: { subtotal: 1000, discount: 0, net: 1000, vat: 0, city_tax: 0, total: 1000 },
          EUR: { subtotal: 200, discount: 0, net: 200, vat: 0, city_tax: 0, total: 200 },
        },
      },
    });
  });

  it('does not combine TRY and EUR category totals under one currency symbol', async () => {
    render(<RevenueSection
      data={{ revenue_trend: [] }}
      s={{}}
      pc={{}}
      roomTypeData={[]}
      reportPeriod="daily"
      reportDate="2026-10-01"
    />);

    const table = await waitFor(() => screen.getByText('Kategori').closest('table'));
    expect(within(table).getAllByText((text) => text.replace(/\s/g, '') === '₺1.000').length).toBeGreaterThan(0);
    expect(within(table).getAllByText((text) => text.replace(/\s/g, '') === '200€').length).toBeGreaterThan(0);
    expect(within(table).queryByText('₺1.200')).not.toBeInTheDocument();
  });

  it('does not draw one revenue trend when currencies differ between days', () => {
    render(<RevenueSection
      data={{ revenue_trend: [
        { label: '01 Eki', revenue: 10000, revenue_by_currency: { TRY: 10000 } },
        { label: '02 Eki', revenue: 200, revenue_by_currency: { EUR: 200 } },
      ] }}
      s={{}}
      pc={{}}
      roomTypeData={[]}
      reportPeriod="daily"
      reportDate="2026-10-01"
    />);

    expect(screen.getByText('Farklı para birimleri tek gelir eğrisinde toplanmaz. Üstteki kartlarda tutarlar para birimi bazında ayrı gösterilir.')).toBeInTheDocument();
  });

  it('does not draw one room type chart when room types use different currencies', () => {
    render(<RevenueSection
      data={{ revenue_trend: [] }}
      s={{}}
      pc={{}}
      roomTypeData={[
        { id: 'standard', name: 'Standart', revenue: 10000, revenueByCurrency: { TRY: 10000 } },
        { id: 'suite', name: 'Suit', revenue: 200, revenueByCurrency: { EUR: 200 } },
      ]}
      reportPeriod="daily"
      reportDate="2026-10-01"
    />);

    expect(screen.getByText('Farklı para birimleri tek grafikte toplanmaz. Oda tipi analizi tablosunda tutarlar para birimi bazında ayrı gösterilir.')).toBeInTheDocument();
  });
});

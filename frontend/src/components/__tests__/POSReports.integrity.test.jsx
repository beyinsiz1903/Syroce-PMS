import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import POSReports from '../POSReports';

vi.mock('axios', () => ({
  default: { get: vi.fn() },
}));

vi.mock('@/hooks/useBusinessDate', () => ({
  useBusinessDate: () => '2026-09-03',
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn() },
}));

describe('POSReports financial integrity', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.clearAllMocks();
    vi.spyOn(console, 'error').mockImplementation(() => {});
    axios.get.mockImplementation((url) => {
      if (url === '/pos/v2/receipts') return Promise.resolve({ data: { receipts: [] } });
      if (url === '/pos/z-report') {
        return Promise.resolve({
          data: {
            report_date: '2026-09-03',
            gross_sales: 132,
            net_sales: 132,
            transaction_count: 1,
            void_count: 1,
            payment_methods: { cash: 132 },
            category_sales: { food: 120 },
            currency: 'TRY',
          },
        });
      }
      if (url === '/pos/void-transactions') {
        return Promise.reject(new Error('void source unavailable'));
      }
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });
  });

  it('hides the previous outlet totals while loading and ignores late responses', async () => {
    const pending = new Map();
    const report = (total) => ({ data: {
      report_date: '2026-09-03', gross_sales: total, net_sales: total, currency: 'TRY',
    } });
    axios.get.mockImplementation((url, { params } = {}) => {
      if (url === '/pos/v2/receipts') return Promise.resolve({ data: { receipts: [] } });
      if (url === '/pos/void-transactions') return Promise.resolve({ data: [] });
      if (url === '/pos/z-report') {
        if (params.outlet_id === 'outlet-a') return Promise.resolve(report(132));
        return new Promise((resolve) => pending.set(params.outlet_id, resolve));
      }
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });

    const { rerender } = render(<POSReports outletId="outlet-a" />);
    expect(await screen.findAllByText('₺132,00')).not.toHaveLength(0);

    rerender(<POSReports outletId="outlet-b" />);
    expect(screen.queryAllByText('₺132,00')).toHaveLength(0);
    rerender(<POSReports outletId="outlet-c" />);
    await act(async () => pending.get('outlet-c')(report(87)));
    expect(await screen.findAllByText('₺87,00')).not.toHaveLength(0);

    await act(async () => pending.get('outlet-b')(report(44)));
    expect(screen.queryAllByText('₺44,00')).toHaveLength(0);
    expect(screen.getAllByText('₺87,00')).not.toHaveLength(0);
  });

  it('does not describe a failed void query as an empty result', async () => {
    render(<POSReports outletId="outlet-a" />);

    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(3));
    expect((await screen.findAllByText('₺132,00')).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('tab', { name: /İptaller \(1\)/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'İptal ayrıntıları yüklenemedi. Bu durum, iptal olmadığı anlamına gelmez.',
    );
    expect(screen.queryByText(/iptal edilmiş işlem yok/i)).not.toBeInTheDocument();
  });

  it('keeps unpaid voids and sale refunds separate on the report business date', async () => {
    axios.get.mockImplementation((url) => {
      if (url === '/pos/v2/receipts') return Promise.resolve({ data: { receipts: [] } });
      if (url === '/pos/z-report') return Promise.resolve({ data: {
        report_date: '2026-09-03', gross_sales: 836, net_sales: 792,
        void_count: 1, void_amount: 100, refunds: 44, currency: 'TRY',
      } });
      if (url === '/pos/void-transactions') return Promise.resolve({ data: { void_transactions: [{
        id: 'voided-check', business_date: '2026-09-03', voided_at: '2026-09-03T22:30:00Z',
        grand_total: 100, total_amount: 90, currency: 'TRY',
      }] } });
      return Promise.reject(new Error(`unexpected request: ${url}`));
    });

    render(<POSReports outletId="outlet-a" />);
    const voids = (await screen.findByText('İptal edilen adisyonlar')).parentElement;
    expect(within(voids).getByText('1')).toBeInTheDocument();
    expect(within(voids).getByText('₺100,00')).toBeInTheDocument();
    expect(within(voids).queryByText('₺44,00')).not.toBeInTheDocument();
    expect(within(screen.getByText('Satış iadeleri').parentElement).getByText('₺44,00')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('tab', { name: /İptaller \(1\)/i }));
    const details = within(await screen.findByRole('tabpanel', { name: /İptaller \(1\)/i }));
    expect(details.getByText('₺100,00')).toBeInTheDocument();
    expect(details.getByText('İş günü · 3 Eylül 2026')).toBeInTheDocument();
    expect(details.getByText('İptal tarihi · 4 Eylül 2026')).toBeInTheDocument();
  });
});

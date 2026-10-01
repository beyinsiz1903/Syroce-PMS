import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
    vi.spyOn(console, 'error').mockImplementation(() => {});
    axios.get.mockImplementation((url) => {
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

  it('does not describe a failed void query as an empty result', async () => {
    render(<POSReports outletId="outlet-a" />);

    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    expect((await screen.findAllByText('₺132,00')).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole('tab', { name: /İptaller \(1\)/i }));

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'İptal ayrıntıları yüklenemedi. Bu durum, iptal olmadığı anlamına gelmez.',
    );
    expect(screen.queryByText(/iptal edilmiş işlem yok/i)).not.toBeInTheDocument();
  });
});

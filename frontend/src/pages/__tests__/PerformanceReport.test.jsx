import { cleanup, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

import PerformanceReport from '@/components/statements/PerformanceReport';

const section = (extra = {}) => ({
  performance: { bookings: 2, cancelled: 1, room_nights: 4, gross: 16000, commission: 2400, net_to_hotel: 13600, cancel_rate: 0.3333 },
  receivables: { agency_owes_hotel: 500, hotel_owes_agency: 1200, awaiting_agreement: 500, open_statements: 2,
    aging: { not_due: 0, overdue_1_30: 0, overdue_31_60: 1200, overdue_61_90: 0, overdue_90_plus: 0 },
    pending_notices: { agency_to_hotel: 0, hotel_to_agency: 1200, count: 1 } },
  unbilled: { bookings: 2, agency_owes_hotel: 10800, hotel_owes_agency: 0 },
  forward: { 30: { bookings: 1, room_nights: 2, gross: 8000 }, 60: { bookings: 1, room_nights: 2, gross: 8000 }, 90: { bookings: 2, room_nights: 5, gross: 16000 } },
  pickup_7d: { bookings: 1, gross: 8000, cancelled: 1 },
  ...extra,
});

describe('PerformanceReport', () => {
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('shows each agency per currency with overdue and unbilled amounts, totals never mixed', async () => {
    const report = {
      period_start: '2026-12-01', period_end: '2026-12-31', as_of: '2026-12-15',
      rows: [{ party_id: 'a1', party_name: 'Acente Bir', currency: 'TRY', ...section() },
        { party_id: 'a2', party_name: 'Acente İki', currency: 'EUR', ...section() }],
      totals: [{ currency: 'TRY', ...section() }, { currency: 'EUR', ...section() }],
    };
    const api = { get: vi.fn(() => Promise.resolve({ data: report })) };
    render(<PerformanceReport side="hotel" api={api} path="/marketplace/hotel/reports/agency-performance" />);
    const row = await screen.findByTestId('performance-row-a1-TRY');
    expect(within(row).getByText('Acente Bir')).toBeTruthy();
    expect(within(row).getByText('2 rez. · 10.800,00')).toBeTruthy(); // unbilled
    expect(within(row).getByText('+1 / −1')).toBeTruthy();
    expect(screen.getByTestId('performance-totals-TRY')).toBeTruthy();
    expect(screen.getByTestId('performance-totals-EUR')).toBeTruthy();
    const overdue = within(screen.getByTestId('performance-totals-EUR')).getByText('Vadesi geçen').parentElement;
    expect(overdue.textContent).toContain('1.200,00 EUR');
    expect(api.get).toHaveBeenCalledWith('/marketplace/hotel/reports/agency-performance', expect.objectContaining({ params: expect.any(Object) }));
  });

  it('survives an unexpected response', async () => {
    const api = { get: vi.fn(() => Promise.resolve({ data: { detail: 'x' } })) };
    render(<PerformanceReport side="agency" api={api} path="/r" />);
    await waitFor(() => expect(screen.getByText('Henüz satış yok.')).toBeTruthy());
  });
});

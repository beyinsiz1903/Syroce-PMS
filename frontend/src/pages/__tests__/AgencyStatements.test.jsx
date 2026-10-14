import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiGet, apiPost, toastSuccess } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), toastSuccess: vi.fn() }));

vi.mock('axios', () => ({ default: { get: (...a) => apiGet(...a), post: (...a) => apiPost(...a) } }));
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: vi.fn() } }));

import AgencyStatements from '@/pages/AgencyStatements';

const statement = {
  id: 's1', number: 'EKS-2026-0001', agency_name: 'Syroce Travel', period_start: '2026-11-01', period_end: '2026-11-30',
  currency: 'TRY', status: 'disputed', outstanding: -150,
  totals: { bookings: 1, cancelled: 1, no_show: 0 },
  lines: [{ booking_id: 'b1', confirmation_code: 'MKT-1', check_in: '2026-11-20', guest_name: 'Test', status: 'checked_out', payment_terms: 'on_arrival', gross: 1000, commission: 150, hotel_owes_agency: 150, agency_owes_hotel: 0 }],
  dispute: { reason: 'Komisyon oranı hatalı', booking_ids: ['b1'] }, payments: [],
};

describe('AgencyStatements', () => {
  beforeEach(() => {
    apiGet.mockImplementation(url => {
      if (url === '/marketplace/hotel/statements') return Promise.resolve({ data: { items: [statement] } });
      if (url === '/marketplace/hotel/statements/agencies') return Promise.resolve({ data: { agencies: [{ id: 'a1', name: 'Syroce Travel' }] } });
      return Promise.resolve({ data: statement });
    });
    apiPost.mockResolvedValue({ data: { ...statement, status: 'resolved' } });
  });
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('shows who owes whom and answers a dispute', async () => {
    render(<AgencyStatements />);
    expect(await screen.findByText('Otel ödeyecek: 150,00 TRY')).toBeTruthy();
    await userEvent.click(screen.getByText('EKS-2026-0001 · Syroce Travel'));
    expect(await screen.findByText(/Komisyon oranı hatalı/)).toBeTruthy();
    await userEvent.type(screen.getByPlaceholderText('İtiraza yanıtınız (en az 5 karakter)'), 'Sözleşmede %15 tanımlı');
    await userEvent.click(screen.getByText('İtirazı yanıtla'));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/marketplace/hotel/statements/s1/resolve', { note: 'Sözleşmede %15 tanımlı' }));
    expect(toastSuccess).toHaveBeenCalledWith('İtiraz yanıtlandı.');
  });
});

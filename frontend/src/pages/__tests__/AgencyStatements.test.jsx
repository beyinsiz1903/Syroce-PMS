import { cleanup, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { apiGet, apiPost, toastSuccess } = vi.hoisted(() => ({ apiGet: vi.fn(), apiPost: vi.fn(), toastSuccess: vi.fn() }));

vi.mock('axios', () => ({ default: { get: (...a) => apiGet(...a), post: (...a) => apiPost(...a) } }));
vi.mock('sonner', () => ({ toast: { success: toastSuccess, error: vi.fn() } }));

import AgencyStatements, { monthEnd, monthStart } from '@/pages/AgencyStatements';

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

  it('verifies or rejects an agency payment notice', async () => {
    const withNotice = { ...statement, status: 'agreed', outstanding: 6800, dispute: null,
      payment_notices: [{ id: 'n1', amount: 6800, paid_at: '2026-10-15', reference: 'EFT-1', reported_by: 'acente@example.com', status: 'pending', has_proof: true }] };
    apiGet.mockImplementation(url => {
      if (url === '/marketplace/hotel/statements') return Promise.resolve({ data: { items: [withNotice] } });
      if (url === '/marketplace/hotel/statements/agencies') return Promise.resolve({ data: { agencies: [] } });
      return Promise.resolve({ data: withNotice });
    });
    apiPost.mockResolvedValue({ data: { ...withNotice, status: 'settled', outstanding: 0, payment_notices: [{ ...withNotice.payment_notices[0], status: 'verified' }] } });
    render(<AgencyStatements />);
    expect(await screen.findByText('1 ödeme bildirimi')).toBeTruthy();
    await userEvent.click(screen.getByText('EKS-2026-0001 · Syroce Travel'));
    expect(await screen.findByText(/ref EFT-1/)).toBeTruthy();
    expect(screen.getByText('Reddet').closest('button').disabled).toBe(true); // a rejection needs a reason
    await userEvent.click(screen.getByText('Doğrula'));
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/marketplace/hotel/statements/s1/payment-notices/n1/verify', { note: '' }));
    expect(toastSuccess).toHaveBeenCalledWith('Ödeme doğrulandı ve ekstreye işlendi.');
  });
});

describe('AgencyStatements preview and line corrections', () => {
  const line = { booking_id: 'b1', confirmation_code: 'MKT-1', check_in: '2026-11-20', guest_name: 'Test', status: 'confirmed', payment_terms: 'prepaid', gross: 8000, commission: 1200, hotel_owes_agency: 0, agency_owes_hotel: 6800 };
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('previews before sending, corrects one line with a reason, then sends', async () => {
    apiGet.mockImplementation(url => Promise.resolve({ data: url.endsWith('/agencies') ? { agencies: [{ id: 'a1', name: 'Syroce Travel' }] } : { items: [] } }));
    apiPost.mockImplementation((url, body) => {
      if (url.endsWith('/preview')) {
        const adjusted = body.adjustments?.length ? { ...line, agency_owes_hotel: 6500, adjustment: { amount: -300, reason: body.adjustments[0].reason } } : line;
        return Promise.resolve({ data: { agency_name: 'Syroce Travel', period_start: '2026-11-01', period_end: '2026-11-30', currency: 'TRY', lines: [adjusted], totals: {}, outstanding: adjusted.agency_owes_hotel } });
      }
      return Promise.resolve({ data: { number: 'EKS-2026-0002' } });
    });
    render(<AgencyStatements />);
    await userEvent.selectOptions(await screen.findByLabelText('Acente'), 'a1');
    await userEvent.click(screen.getByText('Ekstreyi önizle'));
    expect(await screen.findByText('Acente ödeyecek: 6.800,00 TRY', { exact: false })).toBeTruthy();
    expect(screen.getByText('Ön ödemeli')).toBeTruthy();
    expect(apiPost).toHaveBeenCalledTimes(1); // nothing issued yet

    await userEvent.click(screen.getByLabelText('MKT-1 satırını düzelt'));
    await userEvent.type(screen.getByLabelText('Düzeltme tutarı'), '-300');
    await userEvent.type(screen.getByLabelText('Düzeltme gerekçesi'), 'Erken çıkış indirimi');
    await userEvent.click(screen.getByText('Yeniden hesapla'));
    expect(await screen.findByText('Acente ödeyecek: 6.500,00 TRY', { exact: false })).toBeTruthy();
    await userEvent.click(screen.getByText('Acenteye gönder'));
    await waitFor(() => expect(apiPost).toHaveBeenLastCalledWith('/marketplace/hotel/statements', expect.objectContaining({
      agency_id: 'a1', adjustments: [{ booking_id: 'b1', amount: -300, reason: 'Erken çıkış indirimi' }] })));
    expect(toastSuccess).toHaveBeenCalledWith('EKS-2026-0002 düzenlendi ve acenteye iletildi.');
  });

  it('corrects a line of an issued statement', async () => {
    const issued = { id: 's2', number: 'EKS-2026-0003', agency_name: 'Syroce Travel', period_start: '2026-11-01', period_end: '2026-11-30', currency: 'TRY', status: 'issued', outstanding: 6800, totals: { bookings: 1, cancelled: 0, no_show: 0 }, lines: [line], payments: [] };
    apiGet.mockImplementation(url => Promise.resolve({ data: url.endsWith('/agencies') ? { agencies: [] } : url.endsWith('/statements') ? { items: [issued] } : issued }));
    apiPost.mockResolvedValue({ data: { ...issued, outstanding: 6500, lines: [{ ...line, agency_owes_hotel: 6500, adjustment: { amount: -300, reason: 'Erken çıkış indirimi' } }] } });
    render(<AgencyStatements />);
    await userEvent.click(await screen.findByText('EKS-2026-0003 · Syroce Travel'));
    await userEvent.click(await screen.findByLabelText('MKT-1 satırını düzelt'));
    await userEvent.type(screen.getByLabelText('Düzeltme tutarı'), '-300');
    const save = screen.getByText('Düzeltmeyi kaydet ve acenteye bildir');
    await userEvent.click(save);
    expect(apiPost).not.toHaveBeenCalled(); // reason is mandatory
    await userEvent.type(screen.getByLabelText('Düzeltme gerekçesi'), 'Erken çıkış indirimi');
    await userEvent.click(save);
    await waitFor(() => expect(apiPost).toHaveBeenCalledWith('/marketplace/hotel/statements/s2/adjust', { booking_id: 'b1', amount: -300, reason: 'Erken çıkış indirimi' }));
    expect(await screen.findByTestId('adjustment-b1')).toBeTruthy();
  });
});

describe('default statement period', () => {
  it('is the previous calendar month in local time, not shifted to UTC', () => {
    const tz = process.env.TZ;
    process.env.TZ = 'Europe/Istanbul';
    try {
      const now = new Date(2026, 9, 14, 1, 30);
      expect(monthStart(now)).toBe('2026-09-01');
      expect(monthEnd(now)).toBe('2026-09-30');
      expect(monthStart(new Date(2026, 0, 5))).toBe('2025-12-01');
      expect(monthEnd(new Date(2026, 2, 5))).toBe('2026-02-28');
    } finally {
      process.env.TZ = tz;
    }
  });
});

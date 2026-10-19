import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { toast } from 'sonner';
import ReservationReportsTab from '../ReservationReportsTab';

const context = vi.hoisted(() => ({ businessDate: '2026-09-15' }));
vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('@/hooks/useBusinessDate', () => ({ useBusinessDate: () => context.businessDate }));

const payload = (extra = {}) => ({
  start_date: '2026-09-01', end_date: '2026-09-15', currency: 'EUR',
  summary: { total_bookings: 2, commercial_bookings: 2, booked_revenue_by_currency: { EUR: 1234.56, USD: 22.33 }, total_room_nights: 4 },
  rows: [{ booking_id: 'b', guest_name: 'Ada', total_amount: 1234.56, currency: 'EUR' }],
  daily_arrivals: [], channel_breakdown: [], status_breakdown: [], lead_time_breakdown: [], ...extra,
});

const changeStart = value => fireEvent.change(screen.getByLabelText('Rezervasyon raporu başlangıç tarihi'), { target: { value } });

describe('ReservationReportsTab data and lifecycle integrity', () => {
  beforeEach(() => { vi.clearAllMocks(); context.businessDate = '2026-09-15'; });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it('defaults to the PMS business month, preserves cents and explains booked rather than posted revenue', async () => {
    axios.get.mockResolvedValue({ data: payload() });
    render(<ReservationReportsTab />);
    await screen.findByText('Ada');
    expect(axios.get).toHaveBeenCalledWith('/reports/reservation-performance', { params: { start_date: '2026-09-01', end_date: '2026-09-15' } });
    expect(screen.getByText('Geçerli rezervasyon bedeli')).toBeInTheDocument();
    expect(screen.getAllByText(/1\.234,56/).length).toBeGreaterThan(0);
    expect(screen.getByText(/22,33/)).toBeInTheDocument();
    expect(screen.getByText(/tahsilat veya muhasebeleşmiş gelir değildir/)).toBeInTheDocument();
  });

  it('does not show a failed request as a zero or empty report', async () => {
    axios.get.mockRejectedValue(new Error('offline'));
    render(<ReservationReportsTab />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Rezervasyon raporu yüklenemedi');
    expect(screen.queryByText('Toplam rezervasyon')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Excel paketi' })).toBeDisabled();
  });

  it('rejects malformed successful payloads instead of displaying zero', async () => {
    axios.get.mockResolvedValue({ data: { detail: 'broken' } });
    render(<ReservationReportsTab />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Rapor yanıtı eksik');
    expect(screen.queryByText('Toplam rezervasyon')).not.toBeInTheDocument();
  });

  it('an older request cannot overwrite the newly selected period', async () => {
    let resolveOld;
    axios.get.mockImplementation((_url, { params }) => params.start_date === '2026-08-01'
      ? Promise.resolve({ data: payload({ start_date: '2026-08-01', rows: [{ booking_id: 'new', guest_name: 'Güncel dönem' }] }) })
      : new Promise(resolve => { resolveOld = resolve; }));
    render(<ReservationReportsTab />);
    changeStart('2026-08-01');
    await screen.findByText('Güncel dönem');
    await act(async () => resolveOld({ data: payload() }));
    expect(screen.queryByText('Ada')).not.toBeInTheDocument();
    expect(screen.getByText('Güncel dönem')).toBeInTheDocument();
  });

  it('clears old amounts immediately while another period loads or fails', async () => {
    let rejectNew;
    axios.get.mockResolvedValueOnce({ data: payload() }).mockImplementationOnce(() => new Promise((_resolve, reject) => { rejectNew = reject; }));
    render(<ReservationReportsTab />);
    await screen.findByText('Ada');
    changeStart('2026-08-01');
    expect(screen.queryByText('Ada')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Excel paketi' })).toBeDisabled();
    await act(async () => rejectNew(new Error('offline')));
    expect(await screen.findByRole('alert')).toBeInTheDocument();
    expect(screen.queryByText('Ada')).not.toBeInTheDocument();
  });

  it.each(['', '2026-10-01', '2020-01-01'])('does not request or export an invalid period %s', async value => {
    axios.get.mockResolvedValue({ data: payload() });
    render(<ReservationReportsTab />);
    await screen.findByText('Ada');
    changeStart(value);
    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('button', { name: 'Excel paketi' })).toBeDisabled();
    expect(screen.queryByText('Ada')).not.toBeInTheDocument();
  });

  it('shows data-quality issues and missing money as unavailable rather than zero TRY', async () => {
    axios.get.mockResolvedValue({ data: payload({ data_quality: { invalid_amounts: 1, invalid_stays: 2, invalid_lead_times: 3 },
      rows: [{ booking_id: 'bad', guest_name: 'Bozuk tutar', total_amount: null, currency: 'EUR' }] }) });
    render(<ReservationReportsTab />);
    const row = (await screen.findByText('Bozuk tutar')).closest('tr');
    expect(within(row).getAllByText('—').length).toBeGreaterThan(0);
    expect(screen.getByRole('alert')).toHaveTextContent('1 tutar');
    expect(screen.getByRole('alert')).toHaveTextContent('2 konaklama');
  });

  it('manual refresh bypasses the cache without changing the selected dates', async () => {
    axios.get.mockResolvedValue({ data: payload() });
    render(<ReservationReportsTab />);
    await screen.findByText('Ada');
    fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
    await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith('/reports/reservation-performance', {
      params: { start_date: '2026-09-01', end_date: '2026-09-15', nocache: 1 },
    }));
  });

  it('rejects a response for a different period instead of mislabelling its totals', async () => {
    axios.get.mockResolvedValue({ data: payload({ start_date: '2026-08-01' }) });
    render(<ReservationReportsTab />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Rapor yanıtı eksik');
    expect(screen.queryByText('Ada')).not.toBeInTheDocument();
  });

  it('does not overwrite a user-selected period when the business day changes', async () => {
    axios.get.mockImplementation((_url, { params }) => Promise.resolve({ data: payload({ start_date: params.start_date, end_date: params.end_date }) }));
    const { rerender } = render(<ReservationReportsTab />);
    await screen.findByText('Ada');
    changeStart('2026-08-01');
    await screen.findByText('Ada');
    context.businessDate = '2026-10-01';
    rerender(<ReservationReportsTab />);
    expect(screen.getByLabelText('Rezervasyon raporu başlangıç tarihi')).toHaveValue('2026-08-01');
    expect(screen.getByLabelText('Rezervasyon raporu bitiş tarihi')).toHaveValue('2026-09-15');
  });

  it('uses the displayed period for Excel and releases its download URL', async () => {
    const create = vi.fn().mockReturnValue('blob:test-report');
    const revoke = vi.fn();
    class DownloadURL extends URL {}
    DownloadURL.createObjectURL = create;
    DownloadURL.revokeObjectURL = revoke;
    vi.stubGlobal('URL', DownloadURL);
    vi.spyOn(window.HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    const file = new Blob(['test xlsx']);
    axios.get.mockResolvedValueOnce({ data: payload() }).mockResolvedValueOnce({ data: file });
    render(<ReservationReportsTab />);
    await screen.findByText('Ada');
    fireEvent.click(screen.getByRole('button', { name: 'Excel paketi' }));
    await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith('/reports/reservation-performance/excel', {
      params: { start_date: '2026-09-01', end_date: '2026-09-15' }, responseType: 'blob',
    }));
    expect(create).toHaveBeenCalledWith(file);
    expect(revoke).toHaveBeenCalledWith('blob:test-report');
  });

  it('decodes Excel blob errors rather than toasting an object or claiming a download', async () => {
    axios.get.mockResolvedValueOnce({ data: payload() }).mockRejectedValueOnce({ response: { data: {
      text: async () => JSON.stringify({ detail: 'Rapor yetkisi kaldırıldı.' }),
    } } });
    render(<ReservationReportsTab />);
    await screen.findByText('Ada');
    fireEvent.click(screen.getByRole('button', { name: 'Excel paketi' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith('Rapor yetkisi kaldırıldı.'));
  });
});

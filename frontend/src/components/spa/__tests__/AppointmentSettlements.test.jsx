import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { confirmDialog } from '@/lib/dialogs';
import AppointmentSettlements from '../AppointmentSettlements';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn() }));
const result = extra => ({ currency: 'TRY', guest_name: 'Selin Kaya', service_name: 'Bakım',
  payments: [], bank_accounts: [], totals: { service_total: 1500, net_collected: 0, outstanding: 1500 },
  notice: 'Manuel defter kaydıdır; mali fatura değildir.', ...extra });
beforeEach(() => { vi.resetAllMocks(); confirmDialog.mockResolvedValue(true); axios.get.mockResolvedValue({ data: result() }); });
async function fill() {
  await screen.findByRole('heading', { name: 'Dış misafir · Ödeme ve makbuz' });
  fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '100' } });
  fireEvent.change(screen.getByLabelText('Makbuz / banka referansı'), { target: { value: 'SPA-001' } });
  fireEvent.change(screen.getByLabelText('Açıklama / iade gerekçesi'), { target: { value: 'Synthetic receipt only' } });
}
describe('Independent SPA settlements', () => {
  it('sends one confirmed manual payment without a booking or folio', async () => {
    axios.post.mockResolvedValue({ data: {} });
    const changed = vi.fn();
    render(<AppointmentSettlements appointmentId="appt" onRecorded={changed} />);
    await fill();
    fireEvent.click(screen.getByRole('button', { name: 'Hareketi kaydet' }));
    await waitFor(() => expect(changed).toHaveBeenCalledOnce());
    expect(axios.post).toHaveBeenCalledExactlyOnceWith('/spa/appointments/appt/settlements', expect.objectContaining({ amount: 100, method: 'cash', exchange_rate: null }));
    expect(axios.post.mock.calls[0][1]).not.toHaveProperty('folio_id');
  });
  it('does not submit when confirmation is declined', async () => {
    confirmDialog.mockResolvedValue(false);
    render(<AppointmentSettlements appointmentId="appt" />);
    await fill();
    fireEvent.click(screen.getByRole('button', { name: 'Hareketi kaydet' }));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledOnce());
    expect(axios.post).not.toHaveBeenCalled();
  });
  it('blocks new writes after an uncertain result and retries the identical request after reconciliation', async () => {
    axios.post.mockRejectedValueOnce(new Error('Response lost')).mockResolvedValueOnce({ data: {} });
    render(<AppointmentSettlements appointmentId="appt" />);
    await fill();
    fireEvent.click(screen.getByRole('button', { name: 'Hareketi kaydet' }));
    const refresh = await screen.findByRole('button', { name: 'Durumu yenile' });
    expect(screen.getByLabelText('Tutar (TRY)')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Hareketi kaydet' })).toBeDisabled();
    fireEvent.click(refresh);
    await waitFor(() => expect(screen.getByRole('button', { name: 'Hareketi kaydet' })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: 'Hareketi kaydet' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    expect(axios.post.mock.calls[1]).toEqual(axios.post.mock.calls[0]);
  });
  it('restores a persisted pending request as read-only and preserves its key', async () => {
    const request = { request_id: 'persisted-spa-request', kind: 'collection', amount: 100, method: 'cash',
      bank_account_id: null, original_payment_id: null, exchange_rate: null, reference: 'SPA-001', reason: 'Synthetic receipt only' };
    axios.get.mockResolvedValue({ data: result({ pending: { request } }) });
    axios.post.mockResolvedValue({ data: {} });
    render(<AppointmentSettlements appointmentId="appt" />);
    fireEvent.click(await screen.findByRole('button', { name: 'Bekleyen işlemi aç' }));
    expect(screen.getByLabelText('Tutar (TRY)')).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Aynı işlemi tamamla' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledExactlyOnceWith('/spa/appointments/appt/settlements', request));
  });
  it('shows a source-bound receipt and uses the original method and rate for refund', async () => {
    axios.get.mockResolvedValue({ data: result({ currency: 'EUR', bank_accounts: [{ id: 'bank', name: 'EUR hesabı', currency: 'EUR' }],
      payments: [{ id: 'p', receipt_number: 'SPA-P', amount: 100, method: 'bank_transfer', payment_type: 'payment',
        bank_account_id: 'bank', gl_exchange_rate: 40, reference: 'SPA-001', business_date: '2026-11-08', processed_by: 'Operator', gl_journal_entry_id: 'journal' }] }) });
    axios.post.mockResolvedValue({ data: {} });
    render(<AppointmentSettlements appointmentId="appt" />);
    fireEvent.click(await screen.findByText('Makbuz ayrıntıları'));
    expect(screen.getByText('SPA-P')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'İade kaydet' }));
    expect(screen.getByLabelText('Ödeme yöntemi')).toBeDisabled();
    expect(screen.getByLabelText('TRY muhasebe kuru')).toHaveValue(40);
    expect(screen.getByLabelText('TRY muhasebe kuru')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Tutar (EUR)'), { target: { value: '25' } });
    fireEvent.change(screen.getByLabelText('Makbuz / banka referansı'), { target: { value: 'REF-001' } });
    fireEvent.change(screen.getByLabelText('Açıklama / iade gerekçesi'), { target: { value: 'Synthetic refund only' } });
    fireEvent.click(screen.getByRole('button', { name: 'Hareketi kaydet' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/spa/appointments/appt/settlements', expect.objectContaining({
      kind: 'refund', amount: 25, original_payment_id: 'p', method: 'bank_transfer', bank_account_id: 'bank', exchange_rate: 40,
    })));
  });
});

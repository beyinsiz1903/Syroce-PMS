import { beforeEach, describe, expect, it, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import { confirmDialog } from '@/lib/dialogs';
import AppointmentSettlements, { refundableMinor } from '../AppointmentSettlements';

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
  it('keeps fractional-cent conservation and fails closed on inconsistent refund data', () => {
    const original = { id: 'p', amount: 0.30 };
    const refunds = [0.1, 0.2].map((amount, index) => ({ id: String(index), amount: -amount, original_payment_id: 'p', payment_type: 'refund', status: 'refunded' }));
    expect(refundableMinor(original, refunds)).toBe(0);
    expect(refundableMinor(original, [...refunds, { ...refunds[0], id: 'extra' }])).toBeNull();
    expect(refundableMinor({ ...original, amount: 'invalid' }, [])).toBeNull();
  });

  it('disables repeat refunds after the original receipt has been fully refunded', async () => {
    axios.get.mockResolvedValue({ data: result({ payments: [
      { id: 'original', amount: 100, method: 'bank_transfer', payment_type: 'payment', status: 'paid' },
      { id: 'refund1', amount: -40, original_payment_id: 'original', payment_type: 'refund', status: 'refunded' },
      { id: 'refund2', amount: -60, original_payment_id: 'original', payment_type: 'refund', status: 'refunded' },
    ] }) });
    render(<AppointmentSettlements appointmentId="appt" />);
    expect(await screen.findByRole('button', { name: 'İade tamamlandı' })).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('caps a partial refund at its original remaining amount and ignores voided or unrelated refunds', async () => {
    axios.get.mockResolvedValue({ data: result({ payments: [
      { id: 'original', amount: 100, method: 'cash', payment_type: 'payment', status: 'paid' },
      { id: 'refund1', amount: -30, original_payment_id: 'original', payment_type: 'refund', status: 'refunded' },
      { id: 'voided', amount: -80, original_payment_id: 'original', payment_type: 'refund', status: 'refunded', voided: true },
      { id: 'other', amount: -100, original_payment_id: 'elsewhere', payment_type: 'refund', status: 'refunded' },
    ] }) });
    render(<AppointmentSettlements appointmentId="appt" />);
    fireEvent.click(await screen.findByRole('button', { name: 'İade kaydet' }));
    expect(screen.getByLabelText('Tutar (TRY)')).toHaveAttribute('max', '70');
    fireEvent.change(screen.getByLabelText('Tutar (TRY)'), { target: { value: '71' } });
    fireEvent.submit(screen.getByRole('button', { name: 'Hareketi kaydet' }).closest('form'));
    await screen.findByText(/kalan iade edilebilir tutarını aşamaz/);
    expect(confirmDialog).not.toHaveBeenCalled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('keeps a server rejection visible after the payment list has been reconciled', async () => {
    const reason = 'Geçerli iş gününde kasa vardiyasını açın';
    axios.post.mockRejectedValue({ response: { status: 409, data: { detail: reason } } });
    render(<AppointmentSettlements appointmentId="appt" />);
    await fill();
    fireEvent.click(screen.getByRole('button', { name: 'Hareketi kaydet' }));
    expect(await screen.findByText(reason)).toBeInTheDocument();
    fireEvent.click(await screen.findByRole('button', { name: 'Durumu yenile' }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Hareketi kaydet' })).toBeEnabled());
    expect(screen.getByText(reason)).toBeInTheDocument();
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(screen.getByLabelText('Makbuz / banka referansı')).toHaveValue('SPA-001');
  });
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

it('blocks new foreign receipts before source valuation without blocking original refunds', async () => {
  axios.get.mockResolvedValue({ data: result({ currency: 'USD', valuation: { ready: false, rate_to_try: null, business_date: '2026-11-12', reason: 'Kaynak değerlemesi gerekli' }, payments: [{ id: 'p', amount: 30, status: 'paid', method: 'cash', gl_exchange_rate: 40 }] }) });
  render(<AppointmentSettlements appointmentId="usd" />);
  await screen.findByText(/2026-11-12 satış değerlemesi tamamlanmadı/);
  expect(screen.getByRole('button', { name: 'Hareketi kaydet' })).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: 'İade kaydet' }));
  expect(screen.getByRole('button', { name: 'Hareketi kaydet' })).not.toBeDisabled();
  expect(screen.getByLabelText('TRY muhasebe kuru')).toHaveValue(40);
  expect(screen.getByLabelText('TRY muhasebe kuru')).toBeDisabled();
  expect(axios.post).not.toHaveBeenCalled();
});

it('uses the sealed sales rate rather than a new receipt rate', async () => {
  axios.get.mockResolvedValue({ data: result({ currency: 'USD', valuation: { ready: true, rate_to_try: 40, business_date: '2026-11-12' } }) });
  render(<AppointmentSettlements appointmentId="usd" />);
  await screen.findByText(/1 USD = 40 TRY/);
  expect(screen.getByLabelText('TRY muhasebe kuru')).toBeDisabled();
  expect(screen.getByLabelText('TRY muhasebe kuru')).toHaveValue(40);
  fireEvent.change(screen.getByLabelText('Tutar (USD)'), { target: { value: '30' } });
  fireEvent.change(screen.getByLabelText('Makbuz / banka referansı'), { target: { value: 'USD-001' } });
  fireEvent.change(screen.getByLabelText('Açıklama / iade gerekçesi'), { target: { value: 'Synthetic receipt only' } });
  axios.post.mockResolvedValue({ data: {} });
  fireEvent.click(screen.getByRole('button', { name: 'Hareketi kaydet' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/spa/appointments/usd/settlements', expect.objectContaining({ exchange_rate: 40, amount: 30 })));
});

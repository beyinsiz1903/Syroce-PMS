import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import SettlementInstrumentsPanel from '../SettlementInstrumentsPanel';
import { collectionPayment, folioPaymentLabel } from '@/lib/folioPayments';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const props = { bookingId: 'b', currency: 'TRY', folios: [{ id: 'f', folio_number: 'F1', currency: 'TRY', status: 'open' }] };
const data = () => ({ items: [{ id: 'credit', kind: 'barter', status: 'active', currency: 'TRY', remaining_minor: 12345, reference: 'Sözleşme 10' }],
  operations: [], accounts: [{ code: '136', name: 'Barter hesabı', type: 'asset' }],
  kinds: { barter: 'Barter', cheque_pending_clearance: 'Çek' }, can_issue: true, can_apply: true, can_reverse: true, reconciliation: { healthy: true } });
beforeEach(() => { vi.clearAllMocks(); axios.get.mockResolvedValue({ data: data() }); axios.post.mockImplementation(async (_url, body) => ({ data: { id: body.request_id } })); });
afterEach(cleanup);
async function fill() {
  fireEvent.change(screen.getByLabelText('Kullanılacak kaynak'), { target: { value: 'credit' } });
  fireEvent.change(screen.getByLabelText('Mahsup hedef folyo'), { target: { value: 'f' } });
  fireEvent.change(screen.getByLabelText('Mahsup tutarı'), { target: { value: '123,45' } });
  fireEvent.change(screen.getByLabelText('Mahsup belge referansı'), { target: { value: 'Mahsup belge 20' } });
  fireEvent.change(screen.getByLabelText('Mahsup gerekçesi'), { target: { value: 'Sözleşmeye bağlı mahsup' } });
}
it('records decimal-comma minor units without calling a collection endpoint', async () => {
  const changed = vi.fn(); render(<SettlementInstrumentsPanel {...props} onChanged={changed} />);
  await screen.findByText('Kaynak ve işlem geçmişi'); await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Kaynaklı mahsubu uygula' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
  expect(axios.post.mock.calls[0][0]).toBe('/enterprise-billing/instruments/credit/apply');
  expect(axios.post.mock.calls[0][1]).toMatchObject({ booking_id: 'b', folio_id: 'f', amount_minor: 12345, rate_to_try: '1' });
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
});
it('freezes and retries the identical immutable request after an uncertain result', async () => {
  axios.post.mockRejectedValueOnce(new Error('timeout'));
  const locked = vi.fn(); render(<SettlementInstrumentsPanel {...props} onLockChange={locked} />);
  await screen.findByText('Kaynak ve işlem geçmişi'); await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Kaynaklı mahsubu uygula' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Aynı mahsup talebinin sonucunu doğrula' }));
  await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
  expect(axios.post.mock.calls[0]).toEqual(axios.post.mock.calls[1]);
  expect(locked).toHaveBeenCalledWith(true);
});
it('does not expose mutations to read-only users', async () => {
  render(<SettlementInstrumentsPanel {...props} readOnly />);
  await screen.findByText('Kaynak ve işlem geçmişi');
  expect(screen.queryByRole('button', { name: 'Kaynaklı mahsubu uygula' })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Kaynağı / limiti kaydet' })).not.toBeInTheDocument();
});
it('rejects an amount above the source before sending a mutation', async () => {
  render(<SettlementInstrumentsPanel {...props} />); await screen.findByText('Kaynak ve işlem geçmişi'); await fill();
  fireEvent.change(screen.getByLabelText('Mahsup tutarı'), { target: { value: '124' } });
  fireEvent.click(screen.getByRole('button', { name: 'Kaynaklı mahsubu uygula' }));
  await screen.findByText('Tutarı, kalan hakkı ve kuru kontrol edin.'); expect(axios.post).not.toHaveBeenCalled();
});
it.each(['wallet', 'gift_card_redemption', 'loyalty_redemption', 'barter', 'write_off'])('never labels %s as cash collection', method => {
  expect(collectionPayment({ method, amount: 100, status: 'paid' })).toBe(0);
  expect(folioPaymentLabel({ method })).not.toBe(method);
});

import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import SecurityFundsPanel from '../SecurityFundsPanel';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const props = { bookingId: 'booking', currency: 'TRY', folios: [{ id: 'guest', status: 'open', folio_number: 'F-1' }] };
beforeEach(() => {
  vi.clearAllMocks();
  axios.get.mockResolvedValue({ data: { items: [] } });
  axios.post.mockResolvedValue({ data: { id: 'fund', remaining_minor: 100000 } });
});
afterEach(cleanup);
async function fill() {
  await waitFor(() => expect(screen.getByLabelText('Güvence tutarı')).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText('Güvence tutarı'), { target: { value: '1000,00' } });
  fireEvent.change(screen.getByLabelText('Güvence referansı'), { target: { value: 'bank-001' } });
  fireEvent.change(screen.getByLabelText('Güvence gerekçesi'), { target: { value: 'Hasar güvencesi' } });
}

it('records a verified external security receipt without posting a room payment', async () => {
  render(<SecurityFundsPanel {...props} />);
  await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Güvence işlemini kaydet' }));
  await screen.findByText(/Harici güvence hareketi kaydedildi/);
  expect(axios.post.mock.calls[0][0]).toBe('/enterprise-billing/security-funds');
  expect(axios.post.mock.calls[0][1]).toMatchObject({ amount_minor: 100000, currency: 'TRY', method: 'bank_transfer', reference: 'bank-001' });
});

it('preserves the same request after timeout', async () => {
  axios.post.mockRejectedValueOnce(new Error('timeout'));
  render(<SecurityFundsPanel {...props} />);
  await fill();
  fireEvent.click(screen.getByRole('button', { name: 'Güvence işlemini kaydet' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Aynı güvence işlemini doğrula' }));
  await screen.findByText(/Harici güvence hareketi kaydedildi/);
  expect(axios.post.mock.calls[0]).toEqual(axios.post.mock.calls[1]);
});

it('requires an explicit target for applying held security', async () => {
  axios.get.mockResolvedValue({ data: { items: [{ id: 'fund', remaining_minor: 100000, received_minor: 100000,
    refunded_minor: 0, applied_minor: 0, reference: 'bank-001', currency: 'TRY' }] } });
  render(<SecurityFundsPanel {...props} />);
  await fill();
  fireEvent.change(screen.getByLabelText('Güvence işlemi'), { target: { value: 'apply' } });
  fireEvent.change(screen.getByLabelText('Güvence kaydı'), { target: { value: 'fund' } });
  expect(screen.getByRole('button', { name: 'Güvence işlemini kaydet' })).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Güvence hedef folyo'), { target: { value: 'guest' } });
  fireEvent.click(screen.getByRole('button', { name: 'Güvence işlemini kaydet' }));
  await screen.findByText(/Güvence folyoya mahsup edildi/);
  expect(axios.post.mock.calls[0][1]).toMatchObject({ action: 'apply', folio_id: 'guest', amount_minor: 100000 });
});

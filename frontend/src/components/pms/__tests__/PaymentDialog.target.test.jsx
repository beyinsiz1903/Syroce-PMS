import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import PaymentDialog from '../PaymentDialog';

const { get, post } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }));
vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const rows = [{ id: 'first', status: 'open', folio_type: 'company', balance: 6000, currency: 'TRY' },
  { id: 'second', status: 'open', folio_type: 'guest', balance: 4000, currency: 'TRY' }];
const show = () => render(<PaymentDialog open onClose={vi.fn()} selectedBooking={{ id: 'booking', total_amount: 10000, currency: 'TRY' }}
  paymentForm={{ amount: 4000, method: 'card', payment_type: 'final' }} setPaymentForm={vi.fn()} onPaymentDone={vi.fn()} />);
beforeEach(() => { get.mockReset().mockResolvedValue({ data: rows }); post.mockReset().mockResolvedValue({ data: {} }); });

describe('explicit payment destination', () => {
  it('requires a choice for multiple windows and writes to the selected ID even if order changes', async () => {
    show();
    await screen.findByRole('option', { name: /second/ });
    expect(screen.getByTestId('payment-submit-btn')).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Ödeme hedef folyo'), { target: { value: 'second' } });
    get.mockResolvedValueOnce({ data: [...rows].reverse() });
    fireEvent.click(screen.getByTestId('payment-submit-btn'));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/folio/second/payment', expect.objectContaining({ amount: 4000, method: 'card' }), expect.anything()));
  });

  it('does not fall back to another folio when the selected one closes', async () => {
    show();
    await screen.findByRole('option', { name: /second/ });
    fireEvent.change(screen.getByLabelText('Ödeme hedef folyo'), { target: { value: 'second' } });
    get.mockResolvedValueOnce({ data: [rows[0], { ...rows[1], status: 'closed' }] });
    fireEvent.click(screen.getByTestId('payment-submit-btn'));
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2));
    expect(post).not.toHaveBeenCalled();
  });

  it('fails closed when the folio list cannot be loaded', async () => {
    get.mockRejectedValue(new Error('Offline'));
    show();
    expect(await screen.findByRole('alert')).toHaveTextContent('Folyolar yüklenemedi');
    expect(screen.getByTestId('payment-submit-btn')).toBeDisabled();
  });

  it.each(['closed', undefined])('does not treat a %s status as an open financial target', async status => {
    get.mockResolvedValue({ data: [{ ...rows[0], status }] });
    show();
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(screen.getByTestId('payment-submit-btn')).toBeDisabled();
    expect(post).not.toHaveBeenCalled();
  });
});

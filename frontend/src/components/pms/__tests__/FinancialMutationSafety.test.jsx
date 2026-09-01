import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import BulkDeleteRoomsDialog from '@/components/pms/BulkDeleteRoomsDialog';
import CashierTab from '@/components/pms/CashierTab';
import PaymentDialog from '@/components/pms/PaymentDialog';
import { DepositsTab, InvoiceTab } from '@/pages/reservation-detail/DocumentTabs';

const { get, post } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('axios', () => ({ default: { get, post } }));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key, fallback) => fallback || _key,
  }),
}));

afterEach(() => cleanup());

beforeEach(() => {
  get.mockReset();
  post.mockReset();
  post.mockResolvedValue({ data: { deleted: 1, blocked: 0 } });
});

describe('financial and destructive mutation safety', () => {
  it('prefills the agency reservation number in the editable invoice note', async () => {
    get.mockResolvedValue({
      data: {
        charges: [{ id: 'accommodation', amount: 8500, category: 'room', description: 'Konaklama', date: '2026-08-29' }],
        agency_reservation_number: '5939348',
      },
    });
    post.mockResolvedValue({ data: { invoice_html: '<html>invoice</html>' } });

    render(<InvoiceTab booking={{ id: 'booking-test' }} bookingId="booking-test" />);

    expect(await screen.findByDisplayValue('Acente rezervasyon no: 5939348')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('generate-invoice-btn'));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/pms/reservations/booking-test/generate-invoice',
      expect.objectContaining({ invoice_note: 'Acente rezervasyon no: 5939348' }),
    ));
  });

  it('keeps a partially refunded deposit available through an accessible refund action', () => {
    render(
      <DepositsTab
        booking={{ id: 'booking-test' }}
        deposits={[{
          id: 'deposit-test',
          amount: 100,
          refunded_amount: 40,
          status: 'partially_refunded',
          method: 'cash',
        }]}
      />,
    );

    const refundButton = screen.getByRole('button', {
      name: 'Depozito iade işlemini aç - 60 TL',
    });
    fireEvent.click(refundButton);

    expect(screen.getByText('Depozito Iade')).toBeInTheDocument();
  });

  it('disables new deposits for terminal reservations while keeping refunds available', () => {
    render(
      <DepositsTab
        booking={{ id: 'booking-test', status: 'checked_out' }}
        deposits={[{
          id: 'deposit-test',
          amount: 100,
          refunded_amount: 40,
          status: 'partially_refunded',
          method: 'cash',
        }]}
      />,
    );

    expect(screen.getByRole('button', { name: 'Depozito Al' })).toBeDisabled();
    expect(screen.getByRole('button', {
      name: 'Depozito iade işlemini aç - 60 TL',
    })).toBeEnabled();
  });

  it('requires the exact room deletion phrase and suppresses rapid duplicate submissions', async () => {
    let resolveDelete;
    const onDeleted = vi.fn();
    const onClose = vi.fn();
    post.mockImplementation(() => new Promise((resolve) => { resolveDelete = resolve; }));

    render(
      <BulkDeleteRoomsDialog
        open
        onClose={onClose}
        selectedRooms={['room-test']}
        rooms={[{ id: 'room-test', room_number: 'T-101' }]}
        onDeleted={onDeleted}
      />,
    );

    const deleteButton = screen.getByRole('button', { name: 'Delete' });
    expect(deleteButton).toBeDisabled();

    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'wrong' } });
    expect(deleteButton).toBeDisabled();
    expect(post).not.toHaveBeenCalled();

    fireEvent.change(screen.getByPlaceholderText('DELETE'), { target: { value: 'DELETE' } });
    fireEvent.click(deleteButton);
    fireEvent.click(deleteButton);

    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith('/pms/rooms/bulk/delete', {
      ids: ['room-test'],
      confirm_text: 'DELETE',
    });

    resolveDelete({ data: { deleted: 1, blocked: 0 } });
    await waitFor(() => expect(onDeleted).toHaveBeenCalledTimes(1));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it('blocks zero payments and posts a positive payment at most once with an idempotency key', async () => {
    const setPaymentForm = vi.fn();
    const props = {
      open: true,
      onClose: vi.fn(),
      selectedBooking: { id: 'booking-test', total_amount: 100, paid_amount: 0 },
      paymentForm: { amount: 0, method: 'card', payment_type: 'interim', reference: '', notes: '' },
      setPaymentForm,
      onPaymentDone: vi.fn(),
    };
    const { rerender } = render(<PaymentDialog {...props} />);

    expect(screen.getByTestId('payment-submit-btn')).toBeDisabled();
    expect(get).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();

    let resolvePayment;
    get.mockResolvedValue({ data: [{ id: 'folio-test' }] });
    post.mockImplementation(() => new Promise((resolve) => { resolvePayment = resolve; }));
    const positiveProps = {
      ...props,
      paymentForm: { ...props.paymentForm, amount: 25 },
    };
    rerender(<PaymentDialog {...positiveProps} />);

    const submit = screen.getByTestId('payment-submit-btn');
    fireEvent.click(submit);
    fireEvent.click(submit);

    await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
    expect(post).toHaveBeenCalledWith(
      '/folio/folio-test/payment',
      { ...positiveProps.paymentForm, payment_type: 'interim' },
      expect.objectContaining({
        headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }),
      }),
    );
    expect(screen.queryByTestId('payment-type-select')).not.toBeInTheDocument();

    resolvePayment({ data: {} });
    await waitFor(() => expect(positiveProps.onPaymentDone).toHaveBeenCalledTimes(1));
  });

  it('keeps bank deposits behind one successful peer PIN verification', async () => {
    get.mockImplementation((url) => {
      if (url === '/cashier/current-shift') {
        return Promise.resolve({
          data: {
            shift: { id: 'shift-test', status: 'open', opening_amount: 0 },
            transactions: [],
          },
        });
      }
      if (url === '/cashier/shift-history?limit=20') {
        return Promise.resolve({ data: { shifts: [] } });
      }
      return Promise.resolve({ data: {} });
    });
    post.mockResolvedValue({ data: {} });

    render(
      <MemoryRouter>
        <CashierTab />
      </MemoryRouter>,
    );

    await screen.findByRole('button', { name: /Banka Yat/i });
    fireEvent.click(screen.getByRole('button', { name: /Banka Yat/i }));
    fireEvent.change(screen.getByPlaceholderText('0.00'), { target: { value: '25' } });
    fireEvent.change(
      screen.getByPlaceholderText('cm.components_pms_CashierTab.orn_garanti_bbva'),
      { target: { value: 'TEST BANK' } },
    );
    fireEvent.click(screen.getByRole('button', {
      name: 'cm.components_pms_CashierTab.yatirmayi_kaydet',
    }));

    expect(await screen.findByText('Banka yatırma işleminden önce PIN doğrulayın')).toBeInTheDocument();
    expect(post).not.toHaveBeenCalledWith('/cashier/bank-deposit', expect.anything(), expect.anything());

    fireEvent.change(screen.getByPlaceholderText('PIN / şifre'), { target: { value: 'TEST-PIN' } });
    const verifyButton = screen.getByRole('button', { name: 'Doğrula' });
    fireEvent.click(verifyButton);
    fireEvent.click(verifyButton);

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/cashier/peer-verify',
      { pin: 'TEST-PIN' },
      { _skipAuthRetry: true },
    ));
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/cashier/bank-deposit',
      expect.objectContaining({ amount: 25, bank_name: 'TEST BANK' }),
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-Idempotency-Key': expect.any(String) }),
      }),
    ));
    expect(post.mock.calls.filter(([url]) => url === '/cashier/peer-verify')).toHaveLength(1);
    expect(post.mock.calls.filter(([url]) => url === '/cashier/bank-deposit')).toHaveLength(1);
  });

  it('explains the audited cash-shift flow without duplicating the open-shift action', async () => {
    get.mockImplementation((url) => {
      if (url === '/cashier/current-shift') {
        return Promise.resolve({ data: { shift: null, transactions: [] } });
      }
      if (url === '/cashier/shift-history?limit=20') {
        return Promise.resolve({ data: { shifts: [] } });
      }
      return Promise.resolve({ data: {} });
    });

    render(
      <MemoryRouter>
        <CashierTab />
      </MemoryRouter>,
    );

    expect(await screen.findByText(/nakit tahsilat, iade ve kasa hareketlerini/i)).toBeInTheDocument();
    expect(screen.getByText('1. Açılış tutarı')).toBeInTheDocument();
    expect(screen.getByText('3. Sayım ve fark')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /vardiya_ac/i })).toHaveLength(1);
  });
});

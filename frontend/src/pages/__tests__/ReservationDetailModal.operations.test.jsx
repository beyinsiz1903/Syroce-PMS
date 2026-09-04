import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';

import ReservationDetailModal from '@/pages/ReservationDetailModal';

const { get, post, confirmDialog, axiosMock } = vi.hoisted(() => {
  const get = vi.fn();
  const post = vi.fn();
  return {
    get,
    post,
    confirmDialog: vi.fn(),
    axiosMock: Object.assign(vi.fn(), {
      get,
      post,
      put: vi.fn(),
      defaults: { headers: { common: {} } },
      interceptors: {
        request: { use: vi.fn() },
        response: { use: vi.fn() },
      },
    }),
  };
});
vi.mock('axios', () => ({ default: axiosMock }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() } }));
vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (_key, fallback) => fallback || _key }),
}));
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));
vi.mock('@/components/GuestAlertModal', () => ({
  default: ({ open, onConfirm }) => (
    open ? <button type="button" onClick={onConfirm}>Girişi onayla</button> : null
  ),
}));

const detail = {
  booking: {
    id: 'booking-test', status: 'confirmed', room_id: 'room-test', room_number: '106',
    guest_name: 'TEST GUEST', check_in: '2026-08-13', check_out: '2026-08-14',
    created_at: '2026-08-13T12:00:00Z', channel: 'direct', adults: 1, children: 0,
  },
  guest: { id: 'guest-test', name: 'TEST GUEST' },
  room: { id: 'room-test', room_number: '106', room_type: 'Standard', status: 'available' },
  folios: [], charges: [], payments: [], extra_charges: [], notes: [], history: [],
  room_moves: [], daily_rates: [], guests: [], communication_logs: [], deposits: [],
  summary: { balance: 0, total_amount: 0, total_payments: 0 },
};

describe('ReservationDetailModal operation URLs', () => {
  beforeEach(() => {
    get.mockReset();
    get.mockResolvedValue({ data: detail });
    post.mockReset();
    post.mockResolvedValue({ data: { success: true } });
    axiosMock.put.mockReset();
    axiosMock.put.mockResolvedValue({ data: { success: true } });
    confirmDialog.mockReset();
    confirmDialog.mockResolvedValue(true);
  });

  afterEach(() => cleanup());

  it('sends no-show to the single /api-prefixed axios base path', async () => {
    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    fireEvent.click(await screen.findByRole('button', { name: 'No-Show' }));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledOnce());
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/pms/reservations/booking-test/mark-noshow',
      {},
    ));
    expect(post).not.toHaveBeenCalledWith(expect.stringContaining('/api/api/'), expect.anything());
  });

  it('notifies an inline parent after completing a no-show operation', async () => {
    const onOperationComplete = vi.fn();
    render(
      <ReservationDetailModal
        bookingId="booking-test"
        onClose={() => {}}
        onOperationComplete={onOperationComplete}
        allBookings={[]}
      />,
    );

    fireEvent.click(await screen.findByRole('button', { name: 'No-Show' }));

    await waitFor(() => expect(onOperationComplete).toHaveBeenCalledWith({
      bookingId: 'booking-test',
      operation: 'no_show',
    }));
  });

  it('notifies an inline parent after a successful check-in', async () => {
    const onOperationComplete = vi.fn();
    render(
      <ReservationDetailModal
        bookingId="booking-test"
        onClose={() => {}}
        onOperationComplete={onOperationComplete}
        allBookings={[]}
      />,
    );

    fireEvent.click(await screen.findByTestId('btn-checkin'));
    fireEvent.click(await screen.findByRole('button', { name: 'Girişi onayla' }));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/frontdesk/checkin/booking-test?create_folio=true&force_clean=true',
    ));
    await waitFor(() => expect(onOperationComplete).toHaveBeenCalledWith({
      bookingId: 'booking-test',
      operation: 'checked_in',
    }));
  });

  it('shows only lifecycle-eligible mutation buttons for a confirmed booking', async () => {
    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    expect(await screen.findByTestId('btn-early-checkin')).toBeInTheDocument();
    expect(screen.getByTestId('btn-mark-noshow')).toBeInTheDocument();
    expect(screen.getByTestId('btn-cancel-reservation')).toBeInTheDocument();
    expect(screen.queryByTestId('btn-late-checkout')).not.toBeInTheDocument();
  });

  it('updates stay dates with an idempotent booking write and complete daily-rate plan', async () => {
    get.mockImplementation((url) => {
      if (url.includes('/unified-rate-manager/grid')) {
        return Promise.resolve({
          data: {
            grid: [{
              pms_room_type: 'Standard',
              dates: [
                { date: '2026-08-13', rate: 200 },
                { date: '2026-08-14', rate: 250 },
              ],
            }],
          },
        });
      }
      return Promise.resolve({
        data: {
          ...detail,
          booking: { ...detail.booking, total_amount: 200 },
          daily_rates: [{ date: '2026-08-13', rate: 200 }],
        },
      });
    });

    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    fireEvent.click(await screen.findByTestId('edit-stay-dates'));
    fireEvent.change(screen.getByLabelText('Çıkış tarihi'), { target: { value: '2026-08-15' } });
    fireEvent.click(screen.getByTestId('save-stay-dates'));

    await waitFor(() => expect(axiosMock.put).toHaveBeenNthCalledWith(
      1,
      '/pms/bookings/booking-test',
      {
        check_in: '2026-08-13',
        check_out: '2026-08-15',
        total_amount: 450,
      },
      { headers: { 'Idempotency-Key': expect.any(String) } },
    ));
    await waitFor(() => expect(axiosMock.put).toHaveBeenNthCalledWith(
      2,
      '/pms/reservations/booking-test/daily-rates',
      {
        rates: [
          { date: '2026-08-13', rate: 200 },
          { date: '2026-08-14', rate: 250 },
        ],
      },
    ));
  });

  it('shows late checkout but hides arrival and cancellation actions after check-in', async () => {
    get.mockResolvedValueOnce({
      data: { ...detail, booking: { ...detail.booking, status: 'checked_in' } },
    });

    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    expect(await screen.findByTestId('btn-late-checkout')).toBeInTheDocument();
    expect(screen.queryByTestId('btn-early-checkin')).not.toBeInTheDocument();
    expect(screen.queryByTestId('btn-mark-noshow')).not.toBeInTheDocument();
    expect(screen.queryByTestId('btn-cancel-reservation')).not.toBeInTheDocument();
  });

  it('notifies an inline parent after a successful check-out', async () => {
    const onOperationComplete = vi.fn();
    get.mockResolvedValueOnce({
      data: { ...detail, booking: { ...detail.booking, status: 'checked_in' } },
    });

    render(
      <ReservationDetailModal
        bookingId="booking-test"
        onClose={() => {}}
        onOperationComplete={onOperationComplete}
        allBookings={[]}
      />,
    );

    fireEvent.click(await screen.findByTestId('btn-checkout'));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/frontdesk/checkout/booking-test?auto_close_folios=true',
    ));
    await waitFor(() => expect(onOperationComplete).toHaveBeenCalledWith({
      bookingId: 'booking-test',
      operation: 'checked_out',
    }));
  });

  it('routes an open-balance checkout to folios without opening a hidden confirmation', async () => {
    get.mockResolvedValueOnce({
      data: {
        ...detail,
        booking: { ...detail.booking, status: 'checked_in' },
        summary: { ...detail.summary, balance: 4760 },
      },
    });

    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    const paymentButton = await screen.findByTestId('btn-checkout');
    expect(paymentButton).toHaveTextContent('Önce folio bakiyesini tamamlayın');
    fireEvent.click(paymentButton);

    expect(confirmDialog).not.toHaveBeenCalled();
    expect(post).not.toHaveBeenCalled();
    expect(screen.getByRole('tab', { name: 'Folyolar' })).toHaveAttribute('data-state', 'active');
  });

  it('distinguishes the full reservation balance from a partially posted folio', async () => {
    get.mockResolvedValueOnce({
      data: {
        ...detail,
        booking: { ...detail.booking, status: 'checked_in', check_in: '2026-09-01T14:00:00+03:00', check_out: '2026-09-04T12:00:00+03:00' },
        summary: {
          ...detail.summary,
          balance: 5833.34,
          total_amount: 7500,
          reservation_total_due: 7500,
          unposted_room_amount: 1666.66,
        },
      },
    });

    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    expect(await screen.findByTestId('financial-summary-card')).toHaveTextContent('7.500 TL');
    expect(screen.getByTestId('unposted-room-amount')).toHaveTextContent('1.666,66 TL');
    expect(screen.getAllByText('3 gece')).toHaveLength(2);
  });

  it('does not present a system pricing difference as remaining collection', async () => {
    get.mockResolvedValueOnce({
      data: {
        ...detail,
        booking: { ...detail.booking, status: 'checked_in', total_amount: 7500 },
        summary: {
          ...detail.summary,
          total_amount: 7500,
          total_payments: 7500,
          balance: 15.03,
          reservation_total_due: 15.03,
          pricing_reconciliation_required: true,
          pricing_reconciliation_difference: 15.03,
        },
      },
    });

    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    expect(await screen.findByTestId('pricing-reconciliation-alert')).toHaveTextContent('15,03 TL');
    expect(screen.getByTestId('financial-summary-card')).toHaveTextContent('Fiyat / tahakkuk farkı');
    expect(screen.queryByText('Rezervasyon toplamından kalan')).not.toBeInTheDocument();
  });

  it('repairs an unpaid double-taxed channel charge without cancelling the booking', async () => {
    get.mockResolvedValue({
      data: {
        ...detail,
        booking: { ...detail.booking, status: 'checked_in', channel: 'Etstur' },
        summary: {
          ...detail.summary,
          balance: 5320,
          total_amount: 4750,
          channel_pricing_issue: {
            code: 'CHANNEL_TOTAL_TAXED_TWICE',
            observed_total: 5320,
            expected_total: 4750,
            overcharge: 570,
            repairable: true,
          },
        },
      },
    });
    post.mockResolvedValueOnce({ data: { success: true, total_reduction: 570 } });

    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    fireEvent.click(await screen.findByTestId('repair-channel-pricing'));

    await waitFor(() => expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({
      title: 'Rezervasyon fiyatını düzelt',
    })));
    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/pms/reservations/booking-test/repair-channel-pricing',
      { reason: 'Vergi dahil nihai rezervasyon tutarına mükerrer vergi eklenmesinin düzeltilmesi' },
    ));
    expect(post).not.toHaveBeenCalledWith(expect.stringContaining('cancel'), expect.anything());
  });

  it('hides all lifecycle mutations for a checked-out booking', async () => {
    get.mockResolvedValueOnce({
      data: { ...detail, booking: { ...detail.booking, status: 'checked_out' } },
    });

    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    await screen.findByRole('button', { name: 'Not Ekle' });
    expect(screen.queryByTestId('btn-early-checkin')).not.toBeInTheDocument();
    expect(screen.queryByTestId('btn-late-checkout')).not.toBeInTheDocument();
    expect(screen.queryByTestId('btn-room-change')).not.toBeInTheDocument();
    expect(screen.queryByTestId('btn-mark-noshow')).not.toBeInTheDocument();
    expect(screen.queryByTestId('btn-cancel-reservation')).not.toBeInTheDocument();
  });

  it('keeps a historical legacy reservation read-only but allows resolving pending status', async () => {
    get.mockResolvedValueOnce({
      data: { ...detail, read_only: true },
    });

    render(<ReservationDetailModal bookingId="booking-test" onClose={() => {}} allBookings={[]} />);

    expect(await screen.findByText('Salt okunur')).toBeInTheDocument();
    expect(screen.queryByTestId('btn-checkin')).not.toBeInTheDocument();
    expect(screen.queryByTestId('btn-early-checkin')).not.toBeInTheDocument();
    expect(screen.queryByTestId('btn-room-change')).not.toBeInTheDocument();
    expect(screen.getByTestId('btn-mark-noshow')).toBeInTheDocument();
    expect(screen.getByTestId('btn-cancel-reservation')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Not Ekle' })).toBeDisabled();
  });

  it('retries transient detail failures and keeps a safe calendar summary visible', async () => {
    get.mockRejectedValue({ response: { status: 503 } });
    const calendarBooking = {
      id: 'booking-test', guest_name: 'TEST GUEST', room_number: '106',
      check_in: '2026-08-13', check_out: '2026-08-14', status: 'confirmed',
    };

    render(
      <ReservationDetailModal
        bookingId="booking-test"
        onClose={() => {}}
        allBookings={[calendarBooking]}
      />,
    );

    expect(await screen.findByText('Rezervasyon özeti')).toBeInTheDocument();
    expect(screen.getByText(/HTTP 503/)).toBeInTheDocument();
    expect(screen.getByText('TEST GUEST')).toBeInTheDocument();
    expect(screen.getByTestId('retry-reservation-detail')).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(3);
    expect(screen.queryByTestId('btn-checkin')).not.toBeInTheDocument();
  });

  it('does not retry a missing reservation and offers an explicit retry action', async () => {
    get.mockRejectedValue({ response: { status: 404 } });

    render(
      <ReservationDetailModal
        bookingId="missing-booking"
        onClose={() => {}}
        allBookings={[]}
      />,
    );

    expect(await screen.findByTestId('reservation-detail-load-error')).toBeInTheDocument();
    expect(screen.getByText(/HTTP 404/)).toBeInTheDocument();
    expect(screen.getByText(/herhangi bir değişiklik yapılmadı/i)).toBeInTheDocument();
    expect(get).toHaveBeenCalledTimes(1);
  });
});

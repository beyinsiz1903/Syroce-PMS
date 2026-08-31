import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import BookingDialog from '@/components/pms/BookingDialog';
import FolioDialog from '@/components/pms/FolioDialog';
import FrontdeskTab from '@/components/pms/FrontdeskTab';
import { normalizeSearchResults } from '@/components/GlobalSearch';
import { Tabs } from '@/components/ui/tabs';

const { post, confirmDialog } = vi.hoisted(() => ({
  post: vi.fn(),
  confirmDialog: vi.fn(),
}));

vi.mock('axios', () => ({
  default: { get: vi.fn(), post },
}));

vi.mock('@/lib/dialogs', () => ({ confirmDialog }));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), warning: vi.fn() },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (_key, fallback) => {
      if (typeof fallback === 'string') return fallback;
      if (fallback?.defaultValue) return fallback.defaultValue;
      return _key;
    },
  }),
}));

afterEach(() => cleanup());

describe('PMS manually discovered operation regressions', () => {
  beforeEach(() => {
    post.mockReset();
    post.mockResolvedValue({ data: {} });
    confirmDialog.mockReset();
    confirmDialog.mockResolvedValue(true);
  });

  it('preserves both booking dates when the fields are changed back-to-back', () => {
    const booking = {
      guest_id: '', check_in: '', check_out: '', adults: 1, children: 0,
      children_ages: [], guests_count: 1, channel: 'direct', company_id: '',
      rate_type: '', market_segment: '', cancellation_policy: '',
      billing_address: '', billing_tax_number: '', billing_contact_person: '',
      override_reason: '',
    };
    const setNewBooking = vi.fn((updater) => {
      Object.assign(booking, typeof updater === 'function' ? updater(booking) : updater);
    });

    render(
      <BookingDialog
        open
        onClose={() => {}}
        guests={[]}
        rooms={[]}
        companies={[]}
        ratePlans={[]}
        packages={[]}
        newBooking={booking}
        setNewBooking={setNewBooking}
        multiRoomBooking={[]}
        handleCreateBooking={() => {}}
        handleCompanySelect={() => {}}
        handleContractedRateSelect={() => {}}
        handleChildrenChange={() => {}}
        handleChildAgeChange={() => {}}
        addRoomToMultiBooking={() => {}}
        removeRoomFromMultiBooking={() => {}}
        updateMultiRoomField={() => {}}
        updateMultiRoomChildrenAges={() => {}}
        updateMultiRoomChildAge={() => {}}
        setOpenDialog={() => {}}
      />,
    );

    const [checkIn, checkOut] = document.body.querySelectorAll('input[type="date"]');
    fireEvent.change(checkIn, { target: { value: '2026-08-13' } });
    fireEvent.change(checkOut, { target: { value: '2026-08-14' } });

    expect(booking.check_in).toBe('2026-08-13');
    expect(booking.check_out).toBe('2026-08-14');
  });

  it('renders one age input per child without dereferencing placeholder values', () => {
    const booking = {
      guest_id: '', check_in: '', check_out: '', adults: 1, children: 2,
      children_ages: [7, 10], guests_count: 3, channel: 'direct', company_id: '',
      rate_type: '', market_segment: '', cancellation_policy: '',
      billing_address: '', billing_tax_number: '', billing_contact_person: '',
      override_reason: '',
    };

    render(
      <BookingDialog
        open
        onClose={() => {}}
        guests={[]}
        rooms={[]}
        companies={[]}
        ratePlans={[]}
        packages={[]}
        newBooking={booking}
        setNewBooking={() => {}}
        multiRoomBooking={[]}
        handleCreateBooking={() => {}}
        handleCompanySelect={() => {}}
        handleContractedRateSelect={() => {}}
        handleChildrenChange={() => {}}
        handleChildAgeChange={() => {}}
        addRoomToMultiBooking={() => {}}
        removeRoomFromMultiBooking={() => {}}
        updateMultiRoomField={() => {}}
        updateMultiRoomChildrenAges={() => {}}
        updateMultiRoomChildAge={() => {}}
        setOpenDialog={() => {}}
      />,
    );

    expect(screen.getByPlaceholderText('Child 1 age')).toHaveValue(7);
    expect(screen.getByPlaceholderText('Child 2 age')).toHaveValue(10);
  });

  it('posts charge and payment JSON to the active frontdesk contract', async () => {
    const onFolioUpdated = vi.fn();
    render(
      <FolioDialog
        open
        onClose={() => {}}
        bookingId="booking-test"
        onFolioUpdated={onFolioUpdated}
        folio={{ charges: [], payments: [], total_charges: 0, total_paid: 0, balance: 0 }}
      />,
    );

    fireEvent.change(screen.getByPlaceholderText('common.description'), {
      target: { value: 'TEST CHARGE' },
    });
    fireEvent.change(screen.getAllByRole('spinbutton')[0], { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: 'Add Charge' }));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/frontdesk/folio/booking-test/charge',
      expect.objectContaining({ description: 'TEST CHARGE', amount: 25 }),
      expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }),
    ));

    fireEvent.change(screen.getAllByRole('spinbutton')[1], { target: { value: '25' } });
    fireEvent.click(screen.getByRole('button', { name: 'Process Payment' }));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/frontdesk/folio/booking-test/payment',
      expect.objectContaining({ amount: 25, method: 'card' }),
      expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }),
    ));
    expect(onFolioUpdated).toHaveBeenCalledTimes(2);
  });

  it('forwards the dirty-room confirmation as force_clean', async () => {
    const handleCheckIn = vi.fn();
    render(
      <MemoryRouter>
        <Tabs defaultValue="frontdesk">
          <FrontdeskTab
            arrivals={[{
              id: 'booking-dirty', status: 'confirmed', balance: 0,
              check_in: '2026-08-13', check_out: '2026-08-14',
              guest: { name: 'TEST GUEST' },
              room: { room_number: '105', room_type: 'Standard', status: 'dirty' },
            }]}
            departures={[]}
            inhouse={[]}
            bookings={[]}
            rooms={[]}
            guests={[]}
            handleCheckIn={handleCheckIn}
            handleCheckOut={() => {}}
            loadFolio={() => {}}
            loading={false}
          />
        </Tabs>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('checkin-booking-dirty'));
    await waitFor(() => expect(handleCheckIn).toHaveBeenCalledWith('booking-dirty', true));
  });

  it('renders a localized close action for the expanded no-show list', () => {
    render(
      <MemoryRouter>
        <Tabs defaultValue="frontdesk">
          <FrontdeskTab
            arrivals={[]}
            departures={[]}
            inhouse={[]}
            bookings={[{
              id: 'booking-noshow', status: 'confirmed',
              check_in: '2026-08-12', check_out: '2026-08-13',
              guest: { name: 'TEST GUEST' },
              room: { room_number: '105', room_type: 'Standard' },
            }]}
            rooms={[]}
            guests={[]}
            handleCheckIn={() => {}}
            handleCheckOut={() => {}}
            loadFolio={() => {}}
            loading={false}
          />
        </Tabs>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('kpi-noshow'));
    expect(screen.getByRole('button', { name: 'Kapat' })).toBeInTheDocument();
  });

  it('guards overstay checkout, confirms once and locks the destructive action while pending', async () => {
    let resolveCheckout;
    const handleCheckOut = vi.fn(() => new Promise((resolve) => { resolveCheckout = resolve; }));
    render(
      <MemoryRouter>
        <Tabs defaultValue="frontdesk">
          <FrontdeskTab
            arrivals={[]}
            departures={[]}
            inhouse={[]}
            bookings={[{
              id: 'booking-overstay', status: 'checked_in', balance: 0,
              check_in: '2026-08-10', check_out: '2026-08-11',
              guest_name: 'TEST GUEST', room_number: '105',
            }]}
            rooms={[]}
            guests={[]}
            handleCheckIn={() => {}}
            handleCheckOut={handleCheckOut}
            loadFolio={() => {}}
            loading={false}
          />
        </Tabs>
      </MemoryRouter>,
    );

    const button = screen.getByTestId('overstay-checkout-booking-overstay');
    fireEvent.click(button);
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(handleCheckOut).toHaveBeenCalledWith('booking-overstay'));
    expect(button).toBeDisabled();

    fireEvent.click(button);
    expect(handleCheckOut).toHaveBeenCalledTimes(1);
    resolveCheckout(true);
    await waitFor(() => expect(button).not.toBeDisabled());
  });

  it('opens the reservation instead of checking out an overstay with an open balance', async () => {
    const handleCheckOut = vi.fn();
    const setReservationDetailId = vi.fn();
    render(
      <MemoryRouter>
        <Tabs defaultValue="frontdesk">
          <FrontdeskTab
            arrivals={[]}
            departures={[]}
            inhouse={[]}
            bookings={[{
              id: 'booking-balance', status: 'checked_in', balance: 125,
              check_in: '2026-08-10', check_out: '2026-08-11',
              guest_name: 'BALANCE GUEST', room_number: '105',
            }]}
            rooms={[]}
            guests={[]}
            handleCheckIn={() => {}}
            handleCheckOut={handleCheckOut}
            loadFolio={() => {}}
            setReservationDetailId={setReservationDetailId}
            loading={false}
          />
        </Tabs>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('overstay-checkout-booking-balance'));
    expect(setReservationDetailId).toHaveBeenCalledWith('booking-balance');
    expect(handleCheckOut).not.toHaveBeenCalled();
    expect(confirmDialog).not.toHaveBeenCalled();
  });

  it('normalizes both list and paginated search response shapes', () => {
    expect(normalizeSearchResults([{ id: 'g1' }], 'guests')).toEqual([{ id: 'g1' }]);
    expect(normalizeSearchResults({ bookings: [{ id: 'b1' }], total: 1 }, 'bookings')).toEqual([{ id: 'b1' }]);
    expect(normalizeSearchResults({ rooms: [{ id: 'r1' }] }, 'rooms')).toEqual([{ id: 'r1' }]);
    expect(normalizeSearchResults({ unexpected: [] }, 'bookings')).toEqual([]);
  });
});

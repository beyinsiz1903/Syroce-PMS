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

  it('normalizes both list and paginated search response shapes', () => {
    expect(normalizeSearchResults([{ id: 'g1' }], 'guests')).toEqual([{ id: 'g1' }]);
    expect(normalizeSearchResults({ bookings: [{ id: 'b1' }], total: 1 }, 'bookings')).toEqual([{ id: 'b1' }]);
    expect(normalizeSearchResults({ rooms: [{ id: 'r1' }] }, 'rooms')).toEqual([{ id: 'r1' }]);
    expect(normalizeSearchResults({ unexpected: [] }, 'bookings')).toEqual([]);
  });
});

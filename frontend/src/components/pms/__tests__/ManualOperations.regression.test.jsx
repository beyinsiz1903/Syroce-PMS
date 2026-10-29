import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';

import BookingDialog from '@/components/pms/BookingDialog';
import FolioDialog from '@/components/pms/FolioDialog';
import FrontdeskTab from '@/components/pms/FrontdeskTab';
import { normalizeSearchResults } from '@/components/GlobalSearch';
import { Tabs } from '@/components/ui/tabs';

const { get, post, confirmDialog } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  confirmDialog: vi.fn(),
}));

vi.mock('axios', () => ({
  default: { get, post },
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
  const mountFrontdesk = (props) => render(<MemoryRouter><Tabs defaultValue="frontdesk"><FrontdeskTab
    arrivals={[]} departures={[]} inhouse={[]} bookings={[]} rooms={[]} guests={[]}
    handleCheckIn={vi.fn()} handleCheckOut={vi.fn()} loadFolio={vi.fn()} loading={false} {...props}
  /></Tabs></MemoryRouter>);

  it('keeps TRY, EUR and USD amounts separate in every financial pulse card', () => {
    const rows = [{ id: 'try', currency: 'TL', total_amount: 1000.25, balance: 900.25 },
      { id: 'usd', currency: 'USD', total_amount: 560, balance: 638.8 },
      { id: 'eur', currency: 'EUR', total_amount: 200, balance: 150 }];
    mountFrontdesk({ arrivals: rows, departures: rows, inhouse: rows, tenant: { currency: 'TRY' } });
    expect(screen.getByTestId('frontdesk-expected-revenue')).toHaveTextContent(/EUR.*200,00.*TRY.*1.000,25.*USD.*560,00/);
    expect(screen.getByTestId('frontdesk-inhouse-outstanding')).toHaveTextContent(/EUR.*150,00.*TRY.*900,25.*USD.*638,80/);
    expect(screen.getByTestId('frontdesk-expected-collections')).not.toHaveTextContent('1.689,05');
  });

  it('labels quick payment in the booking currency and prevents even a one-cent overcollection', async () => {
    mountFrontdesk({ departures: [{ id: 'usd', currency: 'USD', balance: 638.8, status: 'checked_in', guest_name: 'Synthetic USD', check_out: '2026-10-26' }], tenant: { currency: 'TRY' } });
    fireEvent.click(screen.getByTestId('departure-payment-usd'));
    expect(screen.getByTestId('frontdesk-quick-payment-amount')).toHaveValue('638.80');
    expect(screen.getByText('Tutar (USD)')).toBeInTheDocument();
    expect(screen.getByRole('dialog')).not.toHaveTextContent('₺638');
    expect(screen.getByTestId('frontdesk-quick-payment-submit')).toBeDisabled();
    fireEvent.change(screen.getByTestId('frontdesk-quick-payment-cashier-rate'), { target: { value: '40,123456' } });
    expect(screen.getByTestId('frontdesk-quick-payment-submit')).toBeEnabled();
    fireEvent.change(screen.getByTestId('frontdesk-quick-payment-amount'), { target: { value: '638.81' } });
    expect(screen.getByTestId('frontdesk-quick-payment-submit')).toBeDisabled();
    fireEvent.click(screen.getByTestId('frontdesk-quick-payment-submit'));
    expect(post).not.toHaveBeenCalled();
  });

  it('sends an explicit booking currency and operator-entered cashier rate, never an invented 1:1 rate', async () => {
    mountFrontdesk({ departures: [{ id: 'fx', currency: 'USD', balance: 56, status: 'checked_in', guest_name: 'Synthetic FX', check_out: '2026-10-26' }], tenant: { currency: 'TRY' } });
    fireEvent.click(screen.getByTestId('departure-payment-fx'));
    expect(screen.getByTestId('frontdesk-quick-payment-submit')).toBeDisabled();
    fireEvent.change(screen.getByTestId('frontdesk-quick-payment-cashier-rate'), { target: { value: '40,123456' } });
    fireEvent.click(screen.getByTestId('frontdesk-quick-payment-submit'));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/frontdesk/folio/fx/payment', expect.objectContaining({ amount: 56, currency: 'USD', received_to_try_rate: 40.123456 }), expect.any(Object)));
  });

  it('does not mark a same-business-day stay overdue just because the browser date is later', () => {
    mountFrontdesk({ businessDate: '2026-10-26', inhouse: [{ id: 'same-day', check_out: '2026-10-26', status: 'checked_in' }], bookings: [{ id: 'arrival', check_in: '2026-10-26', status: 'confirmed' }] });
    expect(screen.queryByText('Overstay')).not.toBeInTheDocument();
  });

  beforeEach(() => {
    get.mockReset();
    get.mockResolvedValue({ data: {} });
    post.mockReset();
    post.mockResolvedValue({ data: {} });
    confirmDialog.mockReset();
    confirmDialog.mockResolvedValue(true);
  });

  it('uses the canonical room inventory for current occupancy instead of a conflicting AI value', () => {
    render(
      <MemoryRouter>
        <Tabs defaultValue="frontdesk">
          <FrontdeskTab
            arrivals={[]}
            departures={[]}
            inhouse={[]}
            bookings={[]}
            rooms={[{ id: '1', status: 'occupied' }, { id: '2', status: 'available' }]}
            guests={[]}
            aiPrediction={{ current_occupancy: 99, upcoming_bookings: 0 }}
            handleCheckIn={() => {}}
            handleCheckOut={() => {}}
            loadFolio={() => {}}
            loading={false}
          />
        </Tabs>
      </MemoryRouter>,
    );

    expect(screen.getAllByText('50.0%').length).toBeGreaterThan(0);
    expect(screen.queryByText('99.0%')).not.toBeInTheDocument();
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

  it('shows the reservation currency instead of silently forcing tenant currency', () => {
    const booking = {
      guest_id: '', check_in: '', check_out: '', adults: 1, children: 0,
      children_ages: [], guests_count: 1, channel: 'direct', company_id: '',
      currency: 'USD', rate_type: '', market_segment: '', cancellation_policy: '',
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

    expect(screen.getByTestId('booking-dialog-currency')).toHaveTextContent('USD');
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

    const ages = screen.getAllByLabelText('Çocuk yaşı');
    expect(ages).toHaveLength(2);
    expect(ages[0]).toHaveValue(7);
    expect(ages[1]).toHaveValue(10);
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
            inhouse={[{
              id: 'booking-overstay', status: 'checked_in', balance: 0,
              check_in: '2026-08-10', check_out: '2026-08-11',
              guest_name: 'TEST GUEST', room_number: '105',
            }]}
            bookings={[]}
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
            inhouse={[{
              id: 'booking-balance', status: 'checked_in', balance: 125,
              check_in: '2026-08-10', check_out: '2026-08-11',
              guest_name: 'BALANCE GUEST', room_number: '105',
            }]}
            bookings={[]}
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

    expect(screen.getByTestId('overstay-payment-booking-balance')).toBeInTheDocument();
    fireEvent.click(screen.getByTestId('overstay-checkout-booking-balance'));
    expect(setReservationDetailId).toHaveBeenCalledWith('booking-balance');
    expect(handleCheckOut).not.toHaveBeenCalled();
    expect(confirmDialog).not.toHaveBeenCalled();
  });

  it('posts a simple quick payment to the guest folio and refreshes the front desk', async () => {
    const loadFrontDeskData = vi.fn().mockResolvedValue(undefined);
    const loadData = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <Tabs defaultValue="frontdesk">
          <FrontdeskTab
            arrivals={[]}
            departures={[{
              id: 'booking-payment', status: 'checked_in', balance: 125,
              check_in: '2026-08-30', check_out: '2026-08-31',
              guest_name: 'PAYMENT GUEST', room_number: '105',
            }]}
            inhouse={[]}
            bookings={[]}
            rooms={[]}
            guests={[]}
            handleCheckIn={() => {}}
            handleCheckOut={() => {}}
            loadFolio={() => {}}
            loadFrontDeskData={loadFrontDeskData}
            loadData={loadData}
            loading={false}
          />
        </Tabs>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('departure-payment-booking-payment'));
    expect(screen.getByRole('heading', { name: 'Hızlı Ödeme Al' })).toBeInTheDocument();
    expect(screen.getByTestId('frontdesk-quick-payment-amount')).toHaveValue('125.00');
    expect(screen.queryByText('Ara Ödeme')).not.toBeInTheDocument();
    expect(screen.queryByText('Final Ödeme')).not.toBeInTheDocument();

    fireEvent.click(screen.getByTestId('frontdesk-quick-payment-submit'));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/frontdesk/folio/booking-payment/payment',
      {
        amount: 125,
        currency: 'TRY',
        method: 'card',
        payment_type: 'final',
        reference: null,
        notes: 'Ön büro hızlı tahsilat',
      },
      expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }),
    ));
    await waitFor(() => expect(loadFrontDeskData).toHaveBeenCalledTimes(1));
    expect(loadData).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(screen.queryByTestId('departure-payment-booking-payment')).not.toBeInTheDocument();
    });
  });

  it('transfers the quick-payment balance to the selected existing cari account', async () => {
    get.mockResolvedValue({
      data: { accounts: [{ id: 'legacy-cari-1', transfer_id: 'mongo-cari-1', name: 'Kurumsal Cari' }] },
    });
    const loadFrontDeskData = vi.fn().mockResolvedValue(undefined);
    const loadData = vi.fn().mockResolvedValue(undefined);
    render(
      <MemoryRouter>
        <Tabs defaultValue="frontdesk">
          <FrontdeskTab
            arrivals={[]}
            departures={[{
              id: 'booking-cari', status: 'checked_in', balance: 250,
              check_in: '2026-08-30', check_out: '2026-08-31',
              guest_name: 'CARI GUEST', room_number: '107', channel: 'expedia',
            }]}
            inhouse={[]}
            bookings={[]}
            rooms={[]}
            guests={[]}
            handleCheckIn={() => {}}
            handleCheckOut={() => {}}
            loadFolio={() => {}}
            loadFrontDeskData={loadFrontDeskData}
            loadData={loadData}
            loading={false}
          />
        </Tabs>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('departure-payment-booking-cari'));
    expect(screen.getByTestId('frontdesk-quick-payment-channel')).toHaveTextContent('Expedia');
    fireEvent.click(screen.getByTestId('frontdesk-quick-payment-method'));
    fireEvent.click(screen.getByText('Cari Hesaba Aktar'));

    await waitFor(() => expect(get).toHaveBeenCalledWith('/pms/cari-accounts'));
    await waitFor(() => expect(screen.getByTestId('frontdesk-quick-payment-cari-account')).toBeEnabled());
    fireEvent.click(screen.getByTestId('frontdesk-quick-payment-cari-account'));
    fireEvent.click(screen.getAllByText('Kurumsal Cari').at(-1));
    fireEvent.click(screen.getByTestId('frontdesk-quick-payment-submit'));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/pms/reservations/booking-cari/transfer-to-cari',
      {
        amount: 250,
        cari_account_id: 'mongo-cari-1',
        cari_account_name: 'Kurumsal Cari',
        description: 'Ön büro hızlı cari aktarım',
      },
      expect.objectContaining({ headers: expect.objectContaining({ 'Idempotency-Key': expect.any(String) }) }),
    ));
    await waitFor(() => expect(loadFrontDeskData).toHaveBeenCalledTimes(1));
    expect(loadData).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(screen.queryByTestId('departure-payment-booking-cari')).not.toBeInTheDocument();
    });
  });

  it('opens the full walk-in workflow from the front desk quick action', () => {
    render(
      <MemoryRouter initialEntries={['/pms']}>
        <Routes>
          <Route path="/pms" element={(
            <Tabs defaultValue="frontdesk">
              <FrontdeskTab
                arrivals={[]}
                departures={[]}
                inhouse={[]}
                bookings={[]}
                rooms={[]}
                guests={[]}
                handleCheckIn={() => {}}
                handleCheckOut={() => {}}
                loadFolio={() => {}}
                loading={false}
              />
            </Tabs>
          )} />
          <Route path="/walkin" element={<div>walk-in-workflow</div>} />
        </Routes>
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByTestId('open-walkin-workflow'));
    expect(screen.getByText('walk-in-workflow')).toBeInTheDocument();
  });

  it('normalizes both list and paginated search response shapes', () => {
    expect(normalizeSearchResults([{ id: 'g1' }], 'guests')).toEqual([{ id: 'g1' }]);
    expect(normalizeSearchResults({ bookings: [{ id: 'b1' }], total: 1 }, 'bookings')).toEqual([{ id: 'b1' }]);
    expect(normalizeSearchResults({ rooms: [{ id: 'r1' }] }, 'rooms')).toEqual([{ id: 'r1' }]);
    expect(normalizeSearchResults({ unexpected: [] }, 'bookings')).toEqual([]);
  });
});

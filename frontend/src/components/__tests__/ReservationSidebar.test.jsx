import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import ReservationSidebar, { reservationQuickPanelSummary } from '../ReservationSidebar';
import { confirmDialog } from '@/lib/dialogs';

vi.mock('axios', () => ({ default: { post: vi.fn(), put: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() } }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn() }));
vi.mock('@/components/GuestAlertModal', () => ({
  default: ({ open, onConfirm }) => open ? <button type="button" onClick={onConfirm}>Girişi Onayla</button> : null,
}));

vi.mock('@/components/contact-center/CallButton', () => ({
  default: ({ number }) => <button type="button">Ara {number}</button>,
}));

const booking = {
  id: 'booking-1',
  guest_name: 'Ada Lovelace',
  guest_email: 'ada@example.com',
  guest_phone: '+905551112233',
  check_in: '2026-09-27',
  check_out: '2026-09-29',
  adults: 2,
  children: 1,
  total_amount: 360,
  currency: 'EUR',
  status: 'confirmed',
  channel: 'Booking.com',
};

describe('ReservationSidebar quick panel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.post.mockResolvedValue({ data: {} });
    axios.put.mockResolvedValue({ data: {} });
    confirmDialog.mockResolvedValue(true);
  });

  it('derives currency-safe operational summary values', () => {
    expect(reservationQuickPanelSummary(booking, { balance: 120, currency: 'EUR' })).toEqual({
      nights: 2,
      total: 360,
      balance: 120,
      guestCount: 3,
      currency: 'EUR',
    });
  });

  it('falls back to the tenant currency when legacy booking data has no currency', () => {
    localStorage.setItem('user', JSON.stringify({ tenant_id: 'tenant-eur' }));
    localStorage.setItem('tenant_currency:tenant-eur', JSON.stringify({ code: 'EUR' }));

    expect(reservationQuickPanelSummary({ ...booking, currency: undefined }, null).currency).toBe('EUR');
  });

  it('opens the full workspace without removing quick actions', () => {
    const onOpenWorkspace = vi.fn();
    const onViewFolio = vi.fn();
    render(
      <ReservationSidebar
        booking={booking}
        folio={{ balance: 120, currency: 'EUR' }}
        room={{ room_number: '201', room_type: 'Deluxe' }}
        onClose={() => {}}
        getStatusLabel={() => 'Onaylandı'}
        onOpenWorkspace={onOpenWorkspace}
        onViewFolio={onViewFolio}
      />,
    );

    expect(screen.getByTestId('reservation-quick-panel')).toHaveTextContent('€120');
    fireEvent.click(screen.getByTestId('view-folio-btn'));
    expect(onViewFolio).toHaveBeenCalledWith('booking-1');
    fireEvent.click(screen.getByTestId('open-reservation-workspace'));
    expect(onOpenWorkspace).toHaveBeenCalledWith(booking);
  });

  it('never exposes masked contact payloads while detail data is loading', () => {
    render(
      <ReservationSidebar
        booking={{ ...booking, guest_email: 'SYR1:encrypted-email', guest_phone: 'SYR1:encrypted-phone' }}
        folio={null}
        room={{ room_number: '201', room_type: 'Deluxe' }}
        onClose={() => {}}
        getStatusLabel={() => 'Onaylandı'}
      />,
    );

    expect(screen.queryByText(/SYR1:/)).not.toBeInTheDocument();
    expect(screen.getByText('E-posta bilgisi yok')).toBeInTheDocument();
    expect(screen.getByText('Telefon bilgisi yok')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /Ara/ })).not.toBeInTheDocument();
  });

  it('shows a friendly agency name instead of the technical channel code', () => {
    render(
      <ReservationSidebar
        booking={{ ...booking, channel: 'agodaycs5' }}
        folio={null}
        room={{ room_number: '201', room_type: 'Deluxe' }}
        onClose={() => {}}
        getStatusLabel={() => 'Onaylandı'}
      />,
    );

    expect(screen.getByText('Agoda · 3 misafir')).toBeInTheDocument();
    expect(screen.queryByText(/agodaycs5/i)).not.toBeInTheDocument();
  });

  it('records a guarded quick payment in the reservation currency', async () => {
    const onDataRefresh = vi.fn();
    render(
      <ReservationSidebar
        booking={booking}
        folio={{ balance: 120, currency: 'EUR' }}
        room={{ id: 'room-1', room_number: '201', room_type: 'Deluxe' }}
        onClose={() => {}}
        getStatusLabel={() => 'Onaylandı'}
        onDataRefresh={onDataRefresh}
      />,
    );

    fireEvent.click(screen.getByTestId('quick-payment-btn'));
    const form = screen.getByTestId('quick-payment-form');
    expect(form).toHaveTextContent('Kalan: €120');
    fireEvent.click(screen.getByRole('button', { name: 'Ödemeyi kaydet' }));

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      '/pms/reservations/booking-1/record-payment',
      expect.objectContaining({
        amount: 120,
        method: 'cash',
        currency: 'EUR',
        received_currency: 'EUR',
        received_amount: 120,
        exchange_rate: 1,
        payment_type: 'final',
      }),
    ));
    expect(onDataRefresh).toHaveBeenCalled();
  });

  it('updates basic guest contact details without opening the full workspace', async () => {
    const onDataRefresh = vi.fn();
    render(
      <ReservationSidebar
        booking={booking}
        folio={{ balance: 0, currency: 'EUR' }}
        room={{ id: 'room-1', room_number: '201', room_type: 'Deluxe' }}
        onClose={() => {}}
        getStatusLabel={() => 'Onaylandı'}
        onDataRefresh={onDataRefresh}
      />,
    );

    fireEvent.click(screen.getByTestId('quick-edit-guest-btn'));
    const form = screen.getByTestId('quick-guest-form');
    fireEvent.change(form.querySelector('input[type="email"]'), { target: { value: 'new@example.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    await waitFor(() => expect(axios.put).toHaveBeenCalledWith(
      '/pms/reservations/booking-1/update-guest',
      { name: 'Ada Lovelace', email: 'new@example.com', phone: '+905551112233' },
    ));
    expect(onDataRefresh).toHaveBeenCalled();
  });

  it('checks in an assigned confirmed reservation after confirmation', async () => {
    const onClose = vi.fn();
    const onDataRefresh = vi.fn();
    render(
      <ReservationSidebar
        booking={{ ...booking, room_id: 'room-1' }}
        folio={{ balance: 0, currency: 'EUR' }}
        room={{ id: 'room-1', room_number: '201', room_type: 'Deluxe' }}
        onClose={onClose}
        getStatusLabel={() => 'Onaylandı'}
        onDataRefresh={onDataRefresh}
      />,
    );

    fireEvent.click(screen.getByTestId('quick-checkin-btn'));
    fireEvent.click(screen.getByRole('button', { name: 'Girişi Onayla' }));

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      '/frontdesk/checkin/booking-1?create_folio=true',
    ));
    expect(onDataRefresh).toHaveBeenCalled();
    expect(onClose).toHaveBeenCalled();
  });

  it('routes a checked-in reservation with an open balance to quick payment', () => {
    render(
      <ReservationSidebar
        booking={{ ...booking, status: 'checked_in' }}
        folio={{ balance: 80, currency: 'EUR' }}
        room={{ id: 'room-1', room_number: '201', room_type: 'Deluxe' }}
        onClose={() => {}}
        getStatusLabel={() => 'İçeride'}
      />,
    );

    fireEvent.click(screen.getByTestId('quick-checkout-btn'));
    expect(screen.getByTestId('quick-payment-form')).toBeInTheDocument();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('checks out only after a zero balance is confirmed', async () => {
    const onClose = vi.fn();
    render(
      <ReservationSidebar
        booking={{ ...booking, status: 'checked_in' }}
        folio={{ balance: 0, currency: 'EUR' }}
        room={{ id: 'room-1', room_number: '201', room_type: 'Deluxe' }}
        onClose={onClose}
        getStatusLabel={() => 'İçeride'}
      />,
    );

    fireEvent.click(screen.getByTestId('quick-checkout-btn'));

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith(
      '/pms/reservations/booking-1/checkout?auto_close_folios=true',
    ));
    expect(onClose).toHaveBeenCalled();
  });

  it('blocks quick checkout while price and accrual reconciliation is required', () => {
    render(
      <ReservationSidebar
        booking={{ ...booking, status: 'checked_in', pricing_reconciliation_required: true }}
        folio={{ balance: 0, currency: 'EUR' }}
        room={{ id: 'room-1', room_number: '201', room_type: 'Deluxe' }}
        onClose={() => {}}
        getStatusLabel={() => 'İçeride'}
      />,
    );

    fireEvent.click(screen.getByTestId('quick-checkout-btn'));
    expect(axios.post).not.toHaveBeenCalled();
  });
});

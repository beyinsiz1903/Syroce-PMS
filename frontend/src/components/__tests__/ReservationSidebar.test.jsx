import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import ReservationSidebar, { reservationQuickPanelSummary } from '../ReservationSidebar';

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
  it('derives currency-safe operational summary values', () => {
    expect(reservationQuickPanelSummary(booking, { balance: 120, currency: 'EUR' })).toEqual({
      nights: 2,
      total: 360,
      balance: 120,
      guestCount: 3,
      currency: 'EUR',
    });
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
});

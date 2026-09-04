import React, { useState } from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { NewBookingDialog } from '../CalendarDialogs';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

const room = { id: 'room-205', room_number: '205', room_type: 'standard', floor: 1, base_price: 1000 };

const initialDraft = {
  guest_id: '', guest_name: '', guest_email: '', guest_phone: '', guest_id_number: '',
  room_id: room.id, check_in: '2026-09-05', check_out: '2026-09-08',
  adults: 2, children: 0, children_ages: [], guests_count: 2,
  base_rate: 0, total_amount: 0, price_input_mode: 'nightly',
  prepayment_enabled: false, prepayment_amount: '', prepayment_method: 'cash', prepayment_reference: '',
  status: 'confirmed', apply_occupancy_pricing: false,
};

const DialogHarness = () => {
  const [draft, setDraft] = useState(initialDraft);
  return (
    <NewBookingDialog
      open
      onOpenChange={vi.fn()}
      newBooking={draft}
      setNewBooking={setDraft}
      selectedRoom={room}
      guests={[]}
      rooms={[room]}
      minDate="2026-09-01"
      onSubmit={(event) => event.preventDefault()}
    />
  );
};

describe('NewBookingDialog pricing and prepayment', () => {
  it('allows a zero-valued nightly field to be cleared and typed again', () => {
    render(<DialogHarness />);
    const price = screen.getByTestId('new-booking-price-input');

    fireEvent.change(price, { target: { value: '' } });
    expect(price).toHaveValue(null);

    fireEvent.change(price, { target: { value: '1250' } });
    expect(price).toHaveValue(1250);
  });

  it('supports a total-stay price and exposes prepayment details on demand', () => {
    render(<DialogHarness />);

    fireEvent.change(screen.getByTestId('new-booking-price-input-mode'), { target: { value: 'total' } });
    const total = screen.getByTestId('new-booking-price-input');
    fireEvent.change(total, { target: { value: '7500' } });
    expect(total).toHaveValue(7500);

    expect(screen.queryByTestId('new-booking-prepayment-amount')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('new-booking-prepayment-toggle'));
    fireEvent.change(screen.getByTestId('new-booking-prepayment-amount'), { target: { value: '2500' } });
    fireEvent.change(screen.getByTestId('new-booking-prepayment-method'), { target: { value: 'bank_transfer' } });

    expect(screen.getByTestId('new-booking-prepayment-amount')).toHaveValue(2500);
    expect(screen.getByTestId('new-booking-prepayment-method')).toHaveValue('bank_transfer');
  });
});

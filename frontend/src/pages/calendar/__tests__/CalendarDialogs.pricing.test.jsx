import React, { useState } from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
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
  manual_price_override: true,
  prepayment_enabled: false, prepayment_amount: '', prepayment_method: 'cash', prepayment_reference: '',
  status: 'confirmed', apply_occupancy_pricing: false,
};

const DialogHarness = ({
  initial = initialDraft,
  occupancyPricingRules = {},
  canRecordPrepayment = true,
}) => {
  const [draft, setDraft] = useState(initial);
  return (
    <>
      <NewBookingDialog
        open
        onOpenChange={vi.fn()}
        newBooking={draft}
        setNewBooking={setDraft}
        selectedRoom={room}
        guests={[]}
        rooms={[room]}
        minDate="2026-09-01"
        occupancyPricingRules={occupancyPricingRules}
        canRecordPrepayment={canRecordPrepayment}
        onSubmit={(event) => event.preventDefault()}
      />
      <output data-testid="booking-draft">{JSON.stringify(draft)}</output>
    </>
  );
};

const percentageRule = {
  standard: {
    pricing_type: 'per_person',
    base_occupancy: 2,
    extra_adult_rate_type: 'percentage',
    extra_adult_rate: 20,
    max_occupancy: 4,
    child_age_bands: [{ min_age: 0, max_age: 17, pricing_mode: 'free', value: 0 }],
    pricing_version: 'occupancy-v2',
  },
};

describe('NewBookingDialog pricing and prepayment', () => {
  it('does not offer a payment promise to users without payment permission', () => {
    render(<DialogHarness canRecordPrepayment={false} />);

    expect(screen.getByTestId('new-booking-prepayment-toggle')).toBeDisabled();
    expect(screen.getByText(/Ödeme al.*yetkisi gerekir/)).toBeInTheDocument();
  });

  it('allows a zero-valued nightly field to be cleared and typed again', () => {
    render(<DialogHarness />);
    const price = screen.getByTestId('new-booking-price-input');

    fireEvent.change(price, { target: { value: '' } });
    expect(price).toHaveValue('');

    fireEvent.change(price, { target: { value: '1250' } });
    expect(price).toHaveValue('1250');
  });

  it('supports a total-stay price and exposes prepayment details on demand', () => {
    render(<DialogHarness />);

    fireEvent.change(screen.getByTestId('new-booking-price-input-mode'), { target: { value: 'total' } });
    const total = screen.getByTestId('new-booking-price-input');
    fireEvent.change(total, { target: { value: '7500' } });
    expect(total).toHaveValue('7500');

    expect(screen.queryByTestId('new-booking-prepayment-amount')).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('new-booking-prepayment-toggle'));
    fireEvent.change(screen.getByTestId('new-booking-prepayment-amount'), { target: { value: '2500' } });
    fireEvent.change(screen.getByTestId('new-booking-prepayment-method'), { target: { value: 'bank_transfer' } });

    expect(screen.getByTestId('new-booking-prepayment-amount')).toHaveValue('2500');
    expect(screen.getByTestId('new-booking-prepayment-method')).toHaveValue('bank_transfer');
  });

  it('supports professional comp scopes and disables prepayment', () => {
    render(<DialogHarness />);

    fireEvent.click(screen.getByTestId('new-booking-complimentary-toggle'));

    expect(screen.getByTestId('new-booking-complimentary-scope')).toHaveValue('accommodation_only');
    fireEvent.change(screen.getByTestId('new-booking-complimentary-scope'), { target: { value: 'full' } });
    fireEvent.change(screen.getByTestId('new-booking-complimentary-reason'), { target: { value: 'VIP ağırlama' } });

    expect(screen.getByTestId('new-booking-complimentary-scope')).toHaveValue('full');
    expect(screen.getByText(/sonradan eklenen tüm ekstra hizmetler/i)).toBeInTheDocument();
    expect(screen.getByTestId('new-booking-prepayment-toggle')).toBeDisabled();
  });

  it('shows percentage supplements as percentages, not currency', () => {
    render(<DialogHarness
      initial={{ ...initialDraft, adults: 3, guests_count: 3, base_rate: 7000, total_amount: 7000, manual_price_override: true }}
      occupancyPricingRules={percentageRule}
    />);

    const breakdown = screen.getByTestId('occupancy-price-breakdown');
    expect(breakdown).toHaveTextContent('1 ek yetişkin × %20');
    expect(breakdown).not.toHaveTextContent('₺20');
    expect(breakdown).toHaveTextContent('Kural önerisi ₺8.400');
  });

  it('keeps an entered nightly price final until the operator applies the occupancy rule', async () => {
    render(<DialogHarness
      initial={{ ...initialDraft, adults: 3, guests_count: 3, base_rate: 7000, total_amount: 21000, manual_price_override: true }}
      occupancyPricingRules={percentageRule}
    />);

    fireEvent.change(screen.getByTestId('new-booking-price-input'), { target: { value: '7000' } });
    let draft = JSON.parse(screen.getByTestId('booking-draft').textContent);
    expect(draft.total_amount).toBe(21000);
    expect(draft.apply_occupancy_pricing).toBe(false);
    expect(draft.manual_price_override).toBe(true);

    fireEvent.click(screen.getByTestId('apply-occupancy-price-rule'));
    await waitFor(() => {
      draft = JSON.parse(screen.getByTestId('booking-draft').textContent);
      expect(draft.total_amount).toBe(25200);
      expect(draft.apply_occupancy_pricing).toBe(true);
      expect(draft.manual_price_override).toBe(false);
    });
  });
});

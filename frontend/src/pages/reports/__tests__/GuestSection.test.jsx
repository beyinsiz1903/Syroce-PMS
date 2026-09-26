import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { convertToTry, GuestTable } from '../GuestSection';

afterEach(() => cleanup());

const guests = [{
  id: 'booking-1:guest-1',
  guest_name: 'Çok Uzun İsimli Test Misafiri',
  guest_email: 'guest@example.com',
  room_number: '205',
  check_in: '2026-09-21',
  check_out: '2026-09-25',
  status: 'checked_in',
  nightly_rate: 2500,
  total_amount: 10000,
  currency: 'EUR',
  received_payments: [{ amount: 165.71, currency: 'USD' }],
  is_primary: true,
}];

describe('GuestTable in-house pricing', () => {
  it('converts foreign-currency prices to current TRY and preserves the source amount', () => {
    render(
      <GuestTable
        guests={guests}
        title="Konaklayanlar (In-House)"
        showNightlyRate
        exchangeRates={{ EUR: 50, TRY: 1 }}
        searchGuest=""
        setSearchGuest={vi.fn()}
      />,
    );

    expect(screen.getByText(/₺125\.000/)).toBeInTheDocument();
    expect(screen.getByText(/2\.500.*€/)).toBeInTheDocument();
    expect(screen.getByText(/₺500\.000/)).toBeInTheDocument();
    expect(screen.getByText(/10\.000.*€/)).toBeInTheDocument();
    expect(convertToTry(145.45, 'EUR', { EUR: 50 })).toBe(7272.5);
  });

  it('shows the selected night and whole-stay amounts as separate, explicit columns', () => {
    render(
      <GuestTable
        guests={guests}
        title="Konaklayanlar (In-House)"
        showNightlyRate
        searchGuest=""
        setSearchGuest={vi.fn()}
      />,
    );

    expect(screen.getByRole('columnheader', { name: 'Gece Ücreti' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Tahsilat' })).toBeInTheDocument();
    expect(screen.getByRole('columnheader', { name: 'Konaklama Toplamı' })).toBeInTheDocument();
    expect(screen.getByText(/2\.500.*€/)).toBeInTheDocument();
    expect(screen.getByText(/10\.000.*€/)).toBeInTheDocument();
    expect(screen.getByText(/\$165,71/)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Konaklayanlar (In-House) tablosu' })).toHaveAttribute('tabindex', '0');
  });

  it('does not repeat room revenue on an additional guest row', () => {
    render(
      <GuestTable
        guests={[{ ...guests[0], id: 'booking-1:guest-2', is_primary: false, nightly_rate: null, total_amount: 0, received_payments: [] }]}
        title="Konaklayanlar (In-House)"
        showNightlyRate
        searchGuest=""
        setSearchGuest={vi.fn()}
      />,
    );

    const cells = screen.getAllByRole('cell');
    expect(cells.at(-3)).toHaveTextContent('-');
    expect(cells.at(-2)).toHaveTextContent('-');
    expect(cells.at(-1)).toHaveTextContent('-');
  });
});

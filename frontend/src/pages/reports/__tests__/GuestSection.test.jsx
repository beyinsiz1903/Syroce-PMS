import { afterEach, describe, expect, it, vi } from 'vitest';
import { cleanup, render, screen } from '@testing-library/react';
import { GuestTable } from '../GuestSection';

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
  is_primary: true,
}];

describe('GuestTable in-house pricing', () => {
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
    expect(screen.getByRole('columnheader', { name: 'Konaklama Toplamı' })).toBeInTheDocument();
    expect(screen.getByText(/2\.500.*€/)).toBeInTheDocument();
    expect(screen.getByText(/10\.000.*€/)).toBeInTheDocument();
    expect(screen.getByRole('region', { name: 'Konaklayanlar (In-House) tablosu' })).toHaveAttribute('tabindex', '0');
  });

  it('does not repeat room revenue on an additional guest row', () => {
    render(
      <GuestTable
        guests={[{ ...guests[0], id: 'booking-1:guest-2', is_primary: false, nightly_rate: null, total_amount: 0 }]}
        title="Konaklayanlar (In-House)"
        showNightlyRate
        searchGuest=""
        setSearchGuest={vi.fn()}
      />,
    );

    const cells = screen.getAllByRole('cell');
    expect(cells.at(-2)).toHaveTextContent('-');
    expect(cells.at(-1)).toHaveTextContent('-');
  });
});

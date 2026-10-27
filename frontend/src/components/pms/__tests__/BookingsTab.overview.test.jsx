import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { calculateBookingStats } from '@/lib/bookingStats';
import BookingsTab from '../BookingsTab';

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/components/ui/tabs', () => ({ TabsContent: ({ children }) => <div>{children}</div> }));
vi.mock('@/components/VirtualizedBookingList', () => ({ default: ({ bookings, onSelectBooking }) => <ol data-testid="bookings-list">{bookings.map(row => <li key={row.id}><button onClick={() => onSelectBooking(row)}>{row.id}</button></li>)}</ol> }));
const rows = [
  { id: 'far', check_in: '2042-09-27', check_out: '2042-09-29', currency: 'EUR', total_amount: 10996 },
  { id: 'near', check_in: '2026-10-27', check_out: '2026-10-28', currency: 'TRY', total_amount: 13440337.96, room_id: '101' },
  { id: 'today', check_in: '2026-10-26', check_out: '2026-10-27', currency: 'USD', total_amount: 10606 },
];
const mount = (props = {}) => render(<MemoryRouter><BookingsTab bookings={rows} bookingStats={calculateBookingStats(rows)} businessDate="2026-10-26" {...props} /></MemoryRouter>);
const order = () => within(screen.getByTestId('bookings-list')).getAllByRole('button').map(button => button.textContent);

describe('reservation overview', () => {
  it('renders exact separate currency rows with compact typography, not a giant joined string', () => {
    mount();
    const revenue = within(screen.getByTestId('booking-revenue-summary'));
    expect(revenue.getAllByRole('term').map(term => term.textContent)).toEqual(['EUR', 'TRY', 'USD']);
    expect(revenue.getByText('₺13.440.337,96').closest('dl')).toHaveClass('text-sm');
  });

  it('preserves the original totals and ADR calculation and both decimal places', () => {
    mount();
    for (const id of ['booking-revenue-summary', 'booking-adr-summary']) {
      const summary = within(screen.getByTestId(id));
      expect(summary.getByText('€10.996,00')).toBeInTheDocument();
      expect(summary.getByText('₺13.440.337,96')).toBeInTheDocument();
      expect(summary.getByText('$10.606,00')).toBeInTheDocument();
    }
  });

  it('sorts full history by proximity and preserves the unassigned filter and detail ID', () => {
    const openDetail = vi.fn();
    mount({ setReservationDetailId: openDetail });
    expect(order()).toEqual(['today', 'near', 'far']);
    fireEvent.change(screen.getByRole('combobox', { name: 'Sıralama' }), { target: { value: 'farthest' } });
    expect(order()).toEqual(['far', 'near', 'today']);
    fireEvent.click(screen.getByRole('button', { name: /Atanmamış/ }));
    expect(order()).toEqual(['far', 'today']);
    fireEvent.click(screen.getByRole('button', { name: 'far' }));
    expect(openDetail).toHaveBeenCalledWith('far');
    expect(screen.getByTestId('booking-revenue-summary')).toHaveTextContent('₺13.440.337,96');
  });

  it('reorders the mounted list when the hotel business day advances', () => {
    const { rerender } = mount();
    rerender(<MemoryRouter><BookingsTab bookings={rows} businessDate="2042-09-27" /></MemoryRouter>);
    expect(order()[0]).toBe('far');
  });

  it('handles a zero-only or missing currency summary without hiding it', () => {
    mount({ bookingStats: { revenueByCurrency: { EUR: 0 }, adrByCurrency: {} } });
    expect(screen.getByTestId('booking-revenue-summary')).toHaveTextContent('€0,00');
    expect(screen.getByTestId('booking-adr-summary')).toHaveTextContent('₺0,00');
  });
});

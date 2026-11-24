import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import GroupFolioPage from '../GroupFolioPage';

vi.mock('@/pages/ReservationDetailModal', () => ({ default: ({ bookingId, onClose }) => <div role="dialog">Guest card {bookingId}<button onClick={onClose}>Close guest card</button></div> }));

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/lib/idle', () => ({ runIdle: () => () => {} }));

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

const groups = [
  { id: 'a', group_name: 'Group A', booking_ids: ['a1', 'a2'] },
  { id: 'b', group_name: 'Group B', booking_ids: ['b1', 'b2'] },
];
const detail = (prefix, currency) => ({ currency, bookings: [1, 2].map(i => ({
  booking_id: `${prefix}${i}`, guest_name: `Guest ${prefix}${i}`, balance: 20, currency,
})) });


it('uses member guest cards instead of legacy copies when the group has account windows', async () => {
  const modern = detail('a', 'TRY');
  modern.bookings[1].uses_account_windows = true;
  axios.get.mockImplementation(url => Promise.resolve({ data: url === '/pms/group-bookings'
    ? { groups } : url === '/pms/group-folio-summary' ? {} : modern }));
  render(<GroupFolioPage />);
  fireEvent.click(await screen.findByTestId('group-card-a'));
  expect(await screen.findByTestId('merge-btn')).toBeDisabled();
  expect(screen.getByRole('note')).toHaveTextContent('Misafir kartı');
  fireEvent.click(screen.getByTestId('guest-card-a2'));
  expect(await screen.findByRole('dialog')).toHaveTextContent('Guest card a2');
  expect(axios.post).not.toHaveBeenCalled();
});

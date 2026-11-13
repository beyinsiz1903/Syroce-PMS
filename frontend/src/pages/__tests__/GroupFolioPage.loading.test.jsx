import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import axios from 'axios';
import GroupFolioPage from '../GroupFolioPage';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }));
vi.mock('@/lib/idle', () => ({ runIdle: () => () => {} }));

beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);

it('renders the group workspace while the first request is pending, without a selected currency', () => {
  axios.get.mockReturnValue(new Promise(() => {}));
  render(<GroupFolioPage />);
  expect(screen.getByTestId('group-folio-page')).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();
});

it('keeps an empty group list usable without mounting payment or merge dialogs', async () => {
  axios.get.mockResolvedValue({ data: { groups: [] } });
  render(<GroupFolioPage />);
  expect(await screen.findByText('cm.pages_GroupFolioPage.soldaki_listeden_bir_grup_secin')).toBeInTheDocument();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();
});

const groups = [
  { id: 'a', group_name: 'Group A', booking_ids: ['a1', 'a2'] },
  { id: 'b', group_name: 'Group B', booking_ids: ['b1', 'b2'] },
];
const detail = (prefix, currency) => ({ currency, bookings: [1, 2].map(i => ({
  booking_id: `${prefix}${i}`, guest_name: `Guest ${prefix}${i}`, balance: 20, currency,
})) });

it('ignores a late previous-group response and retains the current payment currency', async () => {
  let resolveA, resolveB;
  axios.get.mockImplementation(url => url === '/pms/group-bookings'
    ? Promise.resolve({ data: { groups } })
    : new Promise(resolve => { if (url.endsWith('/a')) resolveA = resolve; else resolveB = resolve; }));
  render(<GroupFolioPage />);
  fireEvent.click(await screen.findByTestId('group-card-a'));
  fireEvent.click(screen.getByTestId('group-card-b'));
  await act(async () => resolveB({ data: detail('b', 'EUR') }));
  await act(async () => resolveA({ data: detail('a', 'USD') }));
  expect(screen.getByText('Guest b1')).toBeInTheDocument();
  expect(screen.queryByText('Guest a1')).not.toBeInTheDocument();
  fireEvent.click(screen.getByTestId('add-payment-btn'));
  expect(screen.getByRole('dialog')).toHaveTextContent('common.amount (EUR)');
  expect(screen.getByRole('dialog')).not.toHaveTextContent('USD');
  expect(axios.post).not.toHaveBeenCalled();
});

it('unmounts financial dialogs while changing groups and keeps them closed after a failed load', async () => {
  axios.get.mockImplementation(url => url === '/pms/group-bookings'
    ? Promise.resolve({ data: { groups } })
    : url.endsWith('/a') ? Promise.resolve({ data: detail('a', 'USD') }) : Promise.reject(new Error('offline')));
  render(<GroupFolioPage />);
  fireEvent.click(await screen.findByTestId('group-card-a'));
  fireEvent.click(await screen.findByTestId('add-payment-btn'));
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  fireEvent.click(screen.getByTestId('group-card-b'));
  await act(async () => {});
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  expect(screen.queryByTestId('add-payment-btn')).not.toBeInTheDocument();
  expect(axios.post).not.toHaveBeenCalled();
});

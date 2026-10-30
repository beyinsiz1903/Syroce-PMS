import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, post, translate } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), translate: key => key }));
vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate, i18n: { language: 'tr' } }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', formatCurrency: (n, c) => `${n} ${c}` }));
import AllotmentGrid from '@/components/AllotmentGrid';
const key = suffix => `pmsComponents.allotment.${suffix}`;
const rooms = [{ id: 'r1', room_type: 'Junior Suite' }, { id: 'virtual', room_type: 'King', is_virtual: true }];
beforeEach(() => { get.mockReset(); post.mockReset(); get.mockResolvedValue({ data: { contracts: [], total: 0 } }); post.mockResolvedValue({ data: {} }); });
afterEach(cleanup);

it('uses canonical physical room types, preserves release zero, currency and prevents fractional rooms', async () => {
  render(<AllotmentGrid rooms={rooms} />);
  await waitFor(() => expect(screen.getByRole('button', { name: key('newContract') })).toBeEnabled());
  fireEvent.click(screen.getByRole('button', { name: key('newContract') }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByRole('combobox')).toHaveTextContent('Junior Suite');
  fireEvent.change(within(dialog).getByLabelText(key('tourOperator')), { target: { value: 'Synthetic QA' } });
  const dates = dialog.querySelectorAll('input[type="date"]');
  fireEvent.change(dates[0], { target: { value: '2026-11-10' } });
  fireEvent.change(dates[1], { target: { value: '2026-11-12' } });
  const numbers = within(dialog).getAllByRole('spinbutton');
  fireEvent.change(numbers[0], { target: { value: '1.5' } });
  fireEvent.change(numbers[1], { target: { value: '100' } });
  fireEvent.change(numbers[2], { target: { value: '0' } });
  fireEvent.click(within(dialog).getByRole('button', { name: key('createContract') }));
  expect(post).not.toHaveBeenCalled();
  fireEvent.change(numbers[0], { target: { value: '2' } });
  fireEvent.click(within(dialog).getByRole('button', { name: key('createContract') }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/pms/allotment-contracts', expect.objectContaining({ room_type: 'Junior Suite', release_days: 0, allocated_rooms: 2, rate: 100, currency: 'TRY' })));
});

it('does not invent room types when inventory is missing', async () => {
  render(<AllotmentGrid />);
  expect(screen.getByRole('alert')).toHaveTextContent('Fiziksel oda');
  expect(screen.getByRole('button', { name: key('newContract') })).toBeDisabled();
});

it('shows released capacity as unavailable and keeps currency totals separate', async () => {
  get.mockResolvedValue({ data: { total: 1, contracts: [{ id: 'c1', tour_operator: 'QA', room_type: 'Junior Suite', allocated_rooms: 3, used_rooms: 1, released_rooms: 2, available_rooms: 0, bookings_count: 2, total_revenue_by_currency: { TRY: 200, USD: 300 }, rate: 100, currency: 'TRY' }] } });
  render(<AllotmentGrid rooms={rooms} />);
  expect(await screen.findByText('QA')).toBeInTheDocument();
  expect(screen.getByText('200 TRY')).toBeInTheDocument();
  expect(screen.getByText('300 USD')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: key('releaseRooms') })).toBeDisabled();
});

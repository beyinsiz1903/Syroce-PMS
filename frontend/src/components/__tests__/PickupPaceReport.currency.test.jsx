import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { expect, it, vi } from 'vitest';
import axios from 'axios';
import PickupPaceReport from '../PickupPaceReport';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

it('displays original currencies without toFixed(null) and keeps group filtering outside the dropdown', async () => {
  localStorage.removeItem('pickup_group_only');
  axios.get.mockResolvedValue({ data: {
    summary: { total_bookings: 2, total_revenue: null, total_revenue_by_currency: { EUR: 100, USD: 200 }, velocity_7day: 0, velocity_14day: 0, velocity_30day: 0 },
    chart_data: [{ days_before: 1, date: '2026-10-17', daily_pickup: 2, cumulative_bookings: 2, cumulative_revenue: null, cumulative_revenue_by_currency: { EUR: 100, USD: 200 } }],
  } });
  render(<PickupPaceReport />);
  await waitFor(() => expect(screen.getAllByText(/EUR:/)).toHaveLength(2));
  expect(screen.getAllByText(/USD:/)).toHaveLength(2);
  const group = screen.getByRole('checkbox', { name: 'Only group bookings' });
  expect(group).toBeVisible();
  fireEvent.click(group);
  fireEvent.click(screen.getByRole('button', { name: 'Refresh Pickup' }));
  await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
  expect(axios.get.mock.calls[1][1].params.group_only).toBe(true);
});

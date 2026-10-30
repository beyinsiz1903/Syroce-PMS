import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, put, post, toast, translate } = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn(), toast: { error: vi.fn(), success: vi.fn() }, translate: (key, options) => options?.defaultValue || key }));
vi.mock('axios', () => ({ default: { get, put, post } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate }) }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY' }));
import RevenueControls from '@/components/pms/RevenueControls';
const key = suffix => `pmsComponents.revenue.${suffix}`;
const rooms = [{ id: 'r1', room_type: 'Junior Suite' }, { id: 'virtual', room_type: 'Virtual', is_virtual: true }, { id: 'inactive', room_type: 'Inactive', is_active: false }];
const data = () => ({ hurdle_rates: {}, day_pricing: {}, overbooking: { enabled: false, max_percentage: 5, walk_amount: 0, walk_compensation: 'upgrade_nearby' }, section_revisions: { hurdle_rates: 'h'.repeat(64), day_pricing: 'd'.repeat(64), overbooking: 'o'.repeat(64) } });
beforeEach(() => { get.mockReset(); put.mockReset(); post.mockReset(); toast.error.mockReset(); toast.success.mockReset(); get.mockResolvedValue({ data: data() }); put.mockResolvedValue({ data: { section_revisions: { hurdle_rates: 'n'.repeat(64) } } }); });
afterEach(cleanup);
const saveButton = (tab = 'hurdleTab') => within(screen.getByRole('tabpanel', { name: key(tab) })).getByRole('button', { name: key('save'), exact: true });
const ready = async () => { await waitFor(() => expect(saveButton()).toBeEnabled()); };

it('saves only one versioned section, preserves zero/decimal money and uses physical types', async () => {
  render(<RevenueControls rooms={rooms} />); await ready();
  expect(screen.getByRole('note')).toHaveTextContent('Planning only');
  expect(screen.queryByText('Virtual')).not.toBeInTheDocument();
  expect(screen.queryByText('Inactive')).not.toBeInTheDocument();
  fireEvent.change(screen.getByRole('spinbutton', { name: `Junior Suite ${key('barPrice')}` }), { target: { value: '12.34' } });
  fireEvent.click(saveButton());
  await waitFor(() => expect(put).toHaveBeenCalledWith('/revenue/settings', { hurdle_rates: { 'Junior Suite': { min_rate: 0, bar: 12.34, active: false } }, expected_revisions: { hurdle_rates: 'h'.repeat(64) } }));
});

it('rejects negative and blank prices without silently changing them to zero', async () => {
  render(<RevenueControls rooms={rooms} />); await ready();
  const input = screen.getByRole('spinbutton', { name: `Junior Suite ${key('minPrice')}` });
  for (const value of ['-1', '']) {
    fireEvent.change(input, { target: { value } });
    fireEvent.click(saveButton());
  }
  expect(put).not.toHaveBeenCalled(); expect(toast.error).toHaveBeenCalledTimes(2);
});

it('preserves and rejects fractional minimum stays instead of truncating', async () => {
  render(<RevenueControls rooms={rooms} />); await ready();
  fireEvent.click(screen.getByRole('tab', { name: key('dayPricingTab') }));
  fireEvent.change(screen.getByRole('spinbutton', { name: `mon ${key('minStayLabel')}` }), { target: { value: '1.5' } });
  fireEvent.click(saveButton('dayPricingTab'));
  expect(put).not.toHaveBeenCalled();
  fireEvent.change(screen.getByRole('spinbutton', { name: `mon ${key('minStayLabel')}` }), { target: { value: '2' } });
  fireEvent.change(screen.getByRole('spinbutton', { name: `Junior Suite mon ${key('barPrice')}` }), { target: { value: '12.34' } });
  fireEvent.click(saveButton('dayPricingTab'));
  await waitFor(() => expect(put).toHaveBeenCalled());
  const body = put.mock.calls[0][1]; expect(Object.keys(body).sort()).toEqual(['day_pricing', 'expected_revisions']);
  expect(body.day_pricing['Junior Suite'].mon).toEqual({ rate: 12.34, min_stay: 2 });
});

it('shows no fabricated live overbook count and excludes virtual/inactive capacity', async () => {
  render(<RevenueControls rooms={rooms} />); await ready();
  fireEvent.click(screen.getByRole('tab', { name: key('overbookingTab') }));
  expect(screen.getByText('—')).toBeInTheDocument();
  expect(screen.getByText(/Planned capacity/)).toHaveTextContent('1 + 0 = 1');
  fireEvent.change(screen.getByRole('spinbutton', { name: key('maxOverbooking') }), { target: { value: '2.5' } });
  fireEvent.click(screen.getByRole('button', { name: key('saveSettings') }));
  expect(put).not.toHaveBeenCalled();
});

it('blocks stale saves until explicit reload and resets empty server sections', async () => {
  get.mockResolvedValueOnce({ data: { ...data(), hurdle_rates: { 'Junior Suite': { min_rate: 50, bar: 60, active: true } } } });
  put.mockRejectedValueOnce({ response: { status: 409 } });
  render(<RevenueControls rooms={rooms} />); await ready();
  fireEvent.click(saveButton());
  expect(await screen.findByRole('alert')).toHaveTextContent('another session');
  expect(saveButton()).toBeDisabled();
  fireEvent.click(screen.getByRole('button', { name: key('retry') })); await ready();
  expect(screen.getByRole('spinbutton', { name: `Junior Suite ${key('minPrice')}` })).toHaveValue(0);
});

it('does not allow saving without inventory or after a failed settings read', async () => {
  const view = render(<RevenueControls />);
  await act(async () => {});
  expect(screen.getByRole('alert')).toHaveTextContent('Physical room inventory');
  expect(saveButton()).toBeDisabled();
  view.unmount(); get.mockRejectedValue(new Error('read failed'));
  render(<RevenueControls rooms={rooms} />);
  await waitFor(() => expect(screen.getByText(key('loadError'))).toBeInTheDocument());
  expect(saveButton()).toBeDisabled();
});

it('uses one stable walk-note request ID on retry, preserves cents and never claims payment', async () => {
  post.mockRejectedValueOnce(new Error('uncertain connection')).mockResolvedValueOnce({ data: { record_only: true } });
  render(<RevenueControls rooms={rooms} />); await ready();
  fireEvent.click(screen.getByRole('tab', { name: key('overbookingTab') }));
  fireEvent.click(screen.getByRole('button', { name: key('startWalkOut') }));
  const dialog = screen.getByRole('dialog');
  expect(within(dialog).getByRole('note')).toHaveTextContent('Does not cancel');
  fireEvent.change(within(dialog).getByLabelText(key('guestName')), { target: { value: 'Synthetic QA' } });
  fireEvent.change(within(dialog).getByLabelText(`${key('compensationAmount')} (TRY)`), { target: { value: '12.34' } });
  fireEvent.click(within(dialog).getByRole('combobox', { name: key('roomTypeLabel') }));
  fireEvent.click(screen.getByRole('option', { name: 'Junior Suite' }));
  const save = within(dialog).getByRole('button', { name: 'Save administrative note' });
  fireEvent.click(save); await waitFor(() => expect(save).toBeEnabled());
  expect(post).toHaveBeenCalledTimes(1);
  fireEvent.click(save);
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0][1]).toEqual(post.mock.calls[1][1]);
  expect(post.mock.calls[0][1].request_id).toMatch(/^[a-f0-9-]{36}$/);
  expect(post.mock.calls[0][1].compensation_amount).toBe(12.34);
  await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
  expect(toast.success).toHaveBeenCalledWith('Administrative record saved; no payment or reservation change.');
});

it('retains unmatched legacy configuration instead of deleting it on save', async () => {
  get.mockResolvedValue({ data: { ...data(), hurdle_rates: { Retired: { min_rate: 50, bar: 60, active: true } } } });
  render(<RevenueControls rooms={rooms} />);
  expect(await screen.findByRole('alert')).toHaveTextContent('existing values are retained');
  expect(saveButton()).toBeDisabled();
  fireEvent.click(screen.getByRole('tab', { name: key('dayPricingTab') }));
  expect(saveButton('dayPricingTab')).toBeEnabled();
  expect(put).not.toHaveBeenCalled();
});

it('fails closed when section versions are unavailable', async () => {
  get.mockResolvedValue({ data: { hurdle_rates: {}, day_pricing: {}, overbooking: {} } });
  render(<RevenueControls rooms={rooms} />);
  expect(await screen.findByText(key('loadError'))).toBeInTheDocument();
  expect(saveButton()).toBeDisabled();
});

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, post, patch, toast, translate } = vi.hoisted(() => ({
  get: vi.fn(), post: vi.fn(), patch: vi.fn(), toast: { error: vi.fn(), success: vi.fn() },
  translate: (key, options) => options?.defaultValue || key,
}));
vi.mock('axios', () => ({ default: { get, post, patch } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: translate }) }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', formatCurrency: value => String(value) }));
import ConciergeDesk from '@/components/pms/ConciergeDesk';

const key = suffix => `pmsComponents.concierge.${suffix}`;
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const response = (name, booking, folio, extra = {}) => ({ data: { found: true, guest_name: name, booking_id: booking, folio_id: folio, ...extra } });
beforeEach(() => {
  get.mockReset(); post.mockReset(); patch.mockReset(); toast.error.mockReset();
  get.mockResolvedValue({ data: { requests: [], total: 0, counts: {} } });
});
afterEach(() => { cleanup(); vi.useRealTimers(); });
const open = async () => {
  render(<ConciergeDesk />);
  fireEvent.click(screen.getByRole('button', { name: key('newRequest'), exact: true }));
  const dialog = screen.getByRole('dialog');
  fireEvent.click(within(dialog).getAllByRole('combobox')[0]);
  fireEvent.click(screen.getByRole('option', { name: key('restaurant'), exact: true }));
  vi.useFakeTimers();
  return dialog;
};
const changeRoom = async (value, advance = true) => {
  fireEvent.change(screen.getByLabelText(`${key('roomNo')} *`), { target: { value } });
  if (advance) await act(async () => { await vi.advanceTimersByTimeAsync(500); });
};
const create = () => screen.getByRole('button', { name: key('createRequest'), exact: true });

it('clears the previous guest/folio immediately and ignores an older room response', async () => {
  await open();
  const old = deferred(); const current = deferred();
  get.mockImplementation(url => url.endsWith('/101') ? old.promise : current.promise);
  await changeRoom('101');
  await changeRoom('102');
  expect(create()).toBeDisabled();
  await act(async () => current.resolve(response('Nazlı Demir', 'b102', 'f102')));
  expect(screen.getByLabelText(key('guestName'))).toHaveValue('Nazlı Demir');
  await act(async () => old.resolve(response('Wrong guest', 'b101', 'f101')));
  expect(screen.getByLabelText(key('guestName'))).toHaveValue('Nazlı Demir');
  vi.useRealTimers(); post.mockResolvedValue({ data: { id: 'new' } });
  fireEvent.click(create());
  await waitFor(() => expect(post).toHaveBeenCalledWith('/concierge/requests', expect.objectContaining({ room_number: '102', guest_name: 'Nazlı Demir', booking_id: 'b102', folio_id: 'f102' })));
});

it('drops a matched guest and fee flag during debounce and on a no-match response', async () => {
  await open(); get.mockResolvedValue(response('Nazlı Demir', 'b102', 'f102'));
  await changeRoom('102');
  const charge = screen.getByRole('checkbox', { name: new RegExp(key('chargeToFolio')) });
  fireEvent.click(charge); expect(charge).toBeChecked();
  get.mockResolvedValue({ data: { found: false } });
  await changeRoom('999', false);
  expect(create()).toBeDisabled(); expect(charge).not.toBeChecked(); expect(charge).toBeDisabled();
  expect(screen.getByLabelText(key('guestName'))).toHaveValue('');
  await act(async () => { await vi.advanceTimersByTimeAsync(500); });
  expect(create()).toBeEnabled(); expect(screen.getByText(key('roomNotFound'))).toBeInTheDocument();
});

it('invalidates pending reads when the dialog closes and a new form opens', async () => {
  await open(); const pending = deferred(); get.mockReturnValue(pending.promise);
  await changeRoom('102');
  fireEvent.click(screen.getByRole('button', { name: key('cancelBtn'), exact: true }));
  fireEvent.click(screen.getByRole('button', { name: key('newRequest'), exact: true }));
  await act(async () => pending.resolve(response('Stale guest', 'b102', 'f102')));
  expect(screen.getByLabelText(key('guestName'))).toHaveValue(''); expect(create()).toBeEnabled();
});

it('does not let a failed read or ambiguous folio silently enable charging', async () => {
  await open(); get.mockRejectedValue(new Error('read failed'));
  await changeRoom('102'); expect(create()).toBeDisabled();
  get.mockResolvedValue(response('Nazlı Demir', 'b102', '', { folio_selection_required: true }));
  await changeRoom('103');
  expect(screen.getByText(/Birden fazla açık folyo/)).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: new RegExp(key('chargeToFolio')) })).toBeDisabled();
});

it('rejects fractional or oversized party sizes without silently changing them', async () => {
  await open(); get.mockResolvedValue(response('Nazlı Demir', 'b102', 'f102')); await changeRoom('102');
  const pax = screen.getByLabelText(key('paxLabel'));
  for (const value of ['1.5', '0', '100', '']) {
    fireEvent.change(pax, { target: { value } }); fireEvent.click(create());
  }
  expect(post).not.toHaveBeenCalled(); expect(toast.error).toHaveBeenCalledTimes(4);
});

it('keeps action buttons below the text column on narrow screens', async () => {
  get.mockResolvedValue({ data: { requests: [{ id: 'r', guest_name: 'Nazlı Demir', room_number: '102', type: 'restaurant', status: 'pending', details: 'Akşam yemeği talebi' }], total: 1, counts: {} } });
  render(<ConciergeDesk />);
  expect(await screen.findByText('Nazlı Demir')).toBeInTheDocument();
  const row = screen.getByTestId('concierge-request-row');
  expect(row).toHaveClass('flex-col', 'lg:flex-row');
  expect(within(row).getByText('Nazlı Demir').parentElement.parentElement).toHaveClass('flex-1', 'min-w-0');
});

import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, post, toast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key.split('.').pop() }) }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', formatCurrency: value => String(value) }));
import LaundryTab from '@/components/pms/LaundryTab';
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const found = (name, booking, folio) => ({ data: { found: true, guest_name: name, booking_id: booking, folio_id: folio } });
beforeEach(() => {
  get.mockReset(); post.mockReset(); toast.error.mockReset();
  get.mockImplementation(url => Promise.resolve({ data: url === '/laundry/items' ? { items: [{ id: 'shirt', code: 'shirt', name: 'Gömlek', price: 30 }] } : { orders: [] } }));
});
afterEach(cleanup);
const open = async () => {
  render(<LaundryTab />);
  await waitFor(() => expect(get).toHaveBeenCalledWith('/laundry/items'));
  fireEvent.click(screen.getByRole('button', { name: 'yeni_siparis', exact: true }));
  return screen.getByRole('dialog');
};
const room = () => screen.getByPlaceholderText('101');
const guest = () => within(screen.getByRole('dialog')).getAllByRole('textbox')[1];
const submit = () => screen.getByRole('button', { name: /siparis_olustur/ });
const lookup = async value => { fireEvent.change(room(), { target: { value } }); fireEvent.blur(room()); await act(async () => {}); };

it('clears guest binding immediately on room change and blocks a missing active stay', async () => {
  await open(); get.mockResolvedValue(found('Elif', 'b105', 'f105')); await lookup('105');
  expect(guest()).toHaveValue('Elif');
  get.mockResolvedValue({ data: { found: false } });
  fireEvent.change(room(), { target: { value: '999' } });
  expect(guest()).toHaveValue(''); expect(submit()).toBeDisabled();
  fireEvent.blur(room()); await act(async () => {});
  expect(guest()).toHaveValue(''); expect(submit()).toBeDisabled();
});

it('ignores older lookup responses and responses from a closed form', async () => {
  await open(); const older = deferred(); const newer = deferred();
  get.mockImplementation(url => url.endsWith('/105') ? older.promise : newer.promise);
  await lookup('105'); await lookup('102');
  await act(async () => newer.resolve(found('Nazlı', 'b102', 'f102')));
  await act(async () => older.resolve(found('Wrong guest', 'b105', 'f105')));
  expect(guest()).toHaveValue('Nazlı');
  fireEvent.click(screen.getByRole('button', { name: 'close', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'yeni_siparis', exact: true }));
  expect(room()).toHaveValue(''); expect(guest()).toHaveValue('');
});

it('recalculates existing lines when service type changes, rejects fractional quantity, and retries one durable key', async () => {
  const dialog = await open(); get.mockResolvedValue(found('Elif', 'b105', 'f105')); await lookup('105');
  const quantity = within(dialog).getByRole('spinbutton');
  fireEvent.change(quantity, { target: { value: '1.5' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  expect(screen.queryByText('Gömlek x1')).not.toBeInTheDocument();
  expect(toast.error).toHaveBeenCalled();
  fireEvent.change(quantity, { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  expect(submit()).toHaveTextContent('60');
  fireEvent.click(within(dialog).getAllByRole('combobox')[0]);
  fireEvent.click(screen.getByRole('option', { name: 'Kuru Temizleme', exact: true }));
  expect(submit()).toHaveTextContent('90');
  await waitFor(() => expect(submit()).toBeEnabled());
  post.mockRejectedValue(new Error('lost response'));
  fireEvent.click(submit()); await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  await waitFor(() => expect(submit()).toBeEnabled());
  fireEvent.click(submit()); await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
  expect(post.mock.calls[0][2].headers['Idempotency-Key']).toBeTruthy();
  expect(post.mock.calls[1][2]).toEqual(post.mock.calls[0][2]);
  expect(post.mock.calls[0][1]).toEqual(expect.objectContaining({ room_number: '105', booking_id: 'b105', folio_id: 'f105', items: [expect.objectContaining({ quantity: 2, total: 90 })] }));
});

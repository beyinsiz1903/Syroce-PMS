import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
const { get, post, patch, toast } = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn(), toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() } }));
vi.mock('axios', () => ({ default: { get, post, patch } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key.split('.').pop() }) }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', formatCurrency: value => String(value) }));
import LaundryTab from '@/components/pms/LaundryTab';
const originalScrollIntoView = Element.prototype.scrollIntoView;
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const found = (name, booking, folio, currency = 'TRY') => ({ data: { found: true, guest_name: name, booking_id: booking, folio_id: folio, folio_currency: currency, booking_currency: currency } });
beforeEach(() => {
  Element.prototype.scrollIntoView = vi.fn();
  get.mockReset(); post.mockReset(); patch.mockReset(); toast.error.mockReset();
  get.mockImplementation(url => Promise.resolve({ data: url === '/laundry/items' ? { items: [{ id: 'shirt', code: 'shirt', name: 'Gömlek', price: 30 }] } : { orders: [] } }));
});

it('requires an explicit open same-currency target when the stay has multiple folios', async () => {
  await open();
  get.mockImplementation(url => Promise.resolve({ data: url.startsWith('/bookings/active-by-room/') ? { found: true, guest_name: 'Elif', booking_id: 'b105', booking_currency: 'TRY', folio_id: null, folio_selection_required: true } : [
    { folio_id: 'guest', folio_number: 'F-1', status: 'open', folio_type: 'guest', currency: 'TRY' },
    { folio_id: 'agency', folio_number: 'F-2', status: 'open', folio_type: 'agency', currency: 'TRY' },
    { folio_id: 'closed', folio_number: 'F-CLOSED', status: 'closed', currency: 'TRY' },
    { folio_id: 'fx', folio_number: 'F-USD', status: 'open', currency: 'USD' },
  ] }));
  await lookup('105');
  fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  expect(submit()).toBeDisabled();
  const target = screen.getByRole('combobox', { name: 'Ücretin işleneceği folyo' });
  await waitFor(() => expect(target).toBeEnabled());
  await screen.findByRole('option', { name: /F-2/ });
  expect(screen.queryByRole('option', { name: /F-CLOSED|F-USD/ })).not.toBeInTheDocument();
  fireEvent.change(target, { target: { value: 'agency' } });
  expect(target).toHaveValue('agency');
  expect(submit()).toBeEnabled();
  post.mockResolvedValue({ data: {} });
  fireEvent.click(submit());
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post.mock.calls[0][1]).toEqual(expect.objectContaining({ booking_id: 'b105', folio_id: 'agency' }));
});

it('requires an explicit FX rate and previews the folio amount without relabelling catalogue prices', async () => {
  await open(); get.mockResolvedValue(found('Emre', 'b104', 'usd-folio', 'USD')); await lookup('104');
  fireEvent.change(screen.getByLabelText('Ürün miktarı'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  expect(submit()).toBeDisabled();
  expect(screen.getByRole('alert')).toHaveTextContent('geçerli kuru');
  fireEvent.change(screen.getByLabelText('Folyo dönüşüm kuru'), { target: { value: '0.025' } });
  expect(screen.getByRole('status')).toHaveTextContent('Folyoya yazılacak: 1.5');
  expect(submit()).toHaveTextContent('60');
  post.mockResolvedValue({ data: {} }); fireEvent.click(submit());
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post.mock.calls[0][1]).toMatchObject({ input_currency: 'TRY', exchange_rate: 0.025,
    folio_id: 'usd-folio', items: [{ price: 30, currency: 'TRY', quantity: 2, total: 60 }] });
});

it('shows backend rejection persistently inside the form instead of only in a disappearing toast', async () => {
  await open(); get.mockResolvedValue(found('Elif', 'b105', 'f105')); await lookup('105');
  fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  post.mockRejectedValue({ response: { status: 409, data: { detail: 'Folyo para birimi değişmiş; yenileyin.' } } });
  fireEvent.click(submit());
  expect(await screen.findByRole('alert')).toHaveTextContent('Folyo para birimi değişmiş; yenileyin.');
  expect(screen.getByRole('dialog')).toBeInTheDocument();
  expect(post).toHaveBeenCalledTimes(1);
});

it('selects a separately priced foreign-currency catalogue product, never the same numeric TRY price', async () => {
  get.mockImplementation(url => Promise.resolve({ data: url === '/laundry/items' ? { items: [
    { id: 'try-shirt', code: 'try-shirt', name: 'Gömlek TL', price: 30, currency: 'TRY' },
    { id: 'usd-shirt', code: 'usd-shirt', name: 'Gömlek USD', price: 5, currency: 'USD' },
  ] } : { orders: [] } }));
  await open(); get.mockResolvedValue(found('Emre', 'b104', 'usd-folio', 'USD')); await lookup('104');
  fireEvent.change(screen.getByLabelText('Hizmet para birimi'), { target: { value: 'USD' } });
  fireEvent.change(screen.getByLabelText('Ürün miktarı'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  expect(submit()).toHaveTextContent('10');
  expect(screen.getByLabelText('Hizmet para birimi')).toBeDisabled();
  expect(screen.queryByLabelText('Folyo dönüşüm kuru')).not.toBeInTheDocument();
  post.mockResolvedValue({ data: {} }); fireEvent.click(submit());
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  expect(post.mock.calls[0][1]).toMatchObject({ input_currency: 'USD', exchange_rate: 1,
    items: [{ code: 'usd-shirt', currency: 'USD', price: 5, quantity: 2, total: 10 }] });
});

it('does not enable submission when the target currency could not be verified', async () => {
  await open(); get.mockResolvedValue({ data: { found: true, guest_name: 'Emre', booking_id: 'b104', folio_id: 'f104' } });
  await lookup('104'); fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  expect(submit()).toBeDisabled();
  expect(screen.getAllByRole('alert').some(node => node.textContent.includes('para birimi doğrulanamadı'))).toBe(true);
});

it('lets an operator price a catalogue item in USD explicitly', async () => {
  render(<LaundryTab />); await waitFor(() => expect(get).toHaveBeenCalledWith('/laundry/items'));
  fireEvent.mouseDown(screen.getByRole('tab', { name: /Ayarlar/ }), { button: 0, ctrlKey: false });
  fireEvent.click(screen.getByRole('tab', { name: /Ayarlar/ }));
  fireEvent.change(await screen.findByPlaceholderText('Kod (orn: shirt)'), { target: { value: 'shirt-usd' } });
  fireEvent.change(screen.getByPlaceholderText('Ad (örn. Gömlek)'), { target: { value: 'Gömlek USD' } });
  fireEvent.change(screen.getByLabelText('Yeni ürün para birimi'), { target: { value: 'USD' } });
  fireEvent.change(screen.getByPlaceholderText('Fiyat (USD)'), { target: { value: '5' } });
  post.mockResolvedValue({ data: {} });
  fireEvent.click(screen.getByRole('button', { name: 'ekle', exact: true }));
  await waitFor(() => expect(post).toHaveBeenCalledWith('/laundry/items', { code: 'shirt-usd', name: 'Gömlek USD', price: 5, currency: 'USD' }));
});

it('allows an explicit USD target for a TRY service when the booking is USD and several folios exist', async () => {
  await open();
  get.mockImplementation(url => Promise.resolve({ data: url.startsWith('/bookings/active-by-room/') ? {
    found: true, guest_name: 'Emre', booking_id: 'b104', booking_currency: 'USD', folio_selection_required: true,
  } : [{ folio_id: 'usd', folio_number: 'F-USD', status: 'open', currency: 'USD' },
    { folio_id: 'try', folio_number: 'F-TRY', status: 'open', currency: 'TRY' }] }));
  await lookup('104');
  const target = await screen.findByLabelText('Ücretin işleneceği folyo');
  expect(screen.queryByRole('option', { name: /F-TRY/ })).not.toBeInTheDocument();
  fireEvent.change(target, { target: { value: 'usd' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  expect(submit()).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Folyo dönüşüm kuru'), { target: { value: '0.025' } });
  expect(submit()).toBeEnabled();
});

it('does not overwrite a new room with a late multi-folio read and shows cancellation truthfully', async () => {
  const pending = deferred();
  get.mockImplementation(url => Promise.resolve({ data: url === '/laundry/items' ? { items: [] } : { orders: [{ id: 'cancelled', room_number: '105', guest_name: 'Elif', status: 'cancelled', total: 30, currency: 'TRY' }] } }));
  await open();
  expect(screen.getByText('İptal Edildi', { exact: true })).toBeInTheDocument();
  get.mockImplementation(url => url.startsWith('/folio-windows/') ? pending.promise : Promise.resolve({ data: { found: true, guest_name: 'Elif', booking_id: 'b105', folio_selection_required: true } }));
  await lookup('105');
  fireEvent.change(room(), { target: { value: '102' } });
  await act(async () => pending.resolve({ data: [{ folio_id: 'old', status: 'open', currency: 'TRY' }] }));
  expect(guest()).toHaveValue('');
  expect(screen.queryByRole('combobox', { name: 'Ücretin işleneceği folyo' })).not.toBeInTheDocument();
  expect(submit()).toBeDisabled();
});
afterEach(() => { cleanup(); if (originalScrollIntoView) Element.prototype.scrollIntoView = originalScrollIntoView; else delete Element.prototype.scrollIntoView; });
const open = async () => {
  render(<LaundryTab />);
  await waitFor(() => expect(get).toHaveBeenCalledWith('/laundry/items'));
  // A request starting does not mean its response or Radix selection rendered.
  // Await the actual catalogue promise, including deliberately delayed fixtures.
  const requestIndex = get.mock.calls.findIndex(([url]) => url === '/laundry/items');
  const catalogue = (await get.mock.results[requestIndex].value).data.items;
  await screen.findByText(`Ürün Fiyat Listesi (${catalogue.length})`);
  fireEvent.click(screen.getByRole('button', { name: 'yeni_siparis', exact: true }));
  const dialog = screen.getByRole('dialog');
  const firstProduct = catalogue.find(item => item.active !== false && (item.currency || 'TRY') === 'TRY');
  if (firstProduct) await waitFor(() => expect(within(dialog).getAllByRole('combobox').at(-1)).toHaveTextContent(firstProduct.name));
  return dialog;
};
const room = () => screen.getByPlaceholderText('101');
const guest = () => within(screen.getByRole('dialog')).getAllByRole('textbox')[1];
const submit = () => screen.getByRole('button', { name: /siparis_olustur/ });
const lookup = async value => { fireEvent.change(room(), { target: { value } }); fireEvent.blur(room()); await act(async () => {}); };

it('waits for the catalogue response and rendered product selection before using the order fixture', async () => {
  const catalogue = deferred();
  const original = get.getMockImplementation();
  get.mockImplementation(url => url === '/laundry/items' ? catalogue.promise : original(url));
  const opening = open();
  await waitFor(() => expect(get).toHaveBeenCalledWith('/laundry/items'));
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  await act(async () => catalogue.resolve({ data: { items: [{ id: 'shirt', code: 'shirt', name: 'Gömlek', price: 30 }] } }));
  const dialog = await opening;
  expect(within(dialog).getAllByRole('combobox').at(-1)).toHaveTextContent('Gömlek (30)');
  fireEvent.change(screen.getByLabelText('Ürün miktarı'), { target: { value: '2' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ürün ekle', exact: true }));
  expect(submit()).toHaveTextContent('60');
});

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

it('keeps the last known orders with an explicit warning when a refresh fails', async () => {
  get.mockImplementation(url => Promise.resolve({ data: url === '/laundry/items' ? { items: [] } : { orders: [
    { id: 'retained', room_number: '105', guest_name: 'Bilinen Misafir', status: 'ready', total: 30, currency: 'TRY' }
  ] } }));
  render(<LaundryTab />);
  await screen.findByText('Bilinen Misafir');
  get.mockRejectedValueOnce(new Error('read unavailable'));
  fireEvent.click(screen.getByRole('button', { name: 'yenile', exact: true }));
  await waitFor(() => expect(toast.error).toHaveBeenCalled());
  expect(screen.getByText('Bilinen Misafir')).toBeInTheDocument();
  expect(screen.getByRole('alert')).toHaveTextContent('güncelliği doğrulanamadı');
  expect(screen.getByRole('button', { name: 'Teslim Et', exact: true })).toBeDisabled();
});

it('ignores a stale refresh response after a newer list has arrived', async () => {
  render(<LaundryTab />);
  await act(async () => {});
  const older = deferred(); const newer = deferred();
  get.mockReturnValueOnce(older.promise).mockReturnValueOnce(newer.promise);
  fireEvent.click(screen.getByRole('button', { name: 'yenile', exact: true }));
  fireEvent.click(screen.getByRole('button', { name: 'yenile', exact: true }));
  const orders = name => ({ data: { orders: [{ id: name, room_number: '105', guest_name: name, status: 'ready', total: 30 }] } });
  await act(async () => newer.resolve(orders('Güncel Misafir')));
  await act(async () => older.resolve(orders('Eski Yanıt')));
  expect(screen.getByText('Güncel Misafir')).toBeInTheDocument();
  expect(screen.queryByText('Eski Yanıt')).not.toBeInTheDocument();
});

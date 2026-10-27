import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { api, toast } = vi.hoisted(() => ({
  api: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
  toast: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
}));
vi.mock('axios', () => ({ default: api }));
vi.mock('sonner', () => ({ toast }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', formatCurrency: (amount, code) => `${amount} ${code}` }));
vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn().mockResolvedValue(true) }));

import MinibarPage, { minibarCapabilities } from '../MinibarPage';

const staff = { id: 'manager', tenant_id: 'demo', role: 'admin' };
const item = { id: 'water', name: 'Maden Suyu', price: 60, currency: 'TRY', tax_rate: .2, category: 'drink', active: true };
const product = { id: 'central-water', name: 'Maden Suyu 200 ml', quantity: 50, unit: 'adet', inventory_source: 'accounting' };
const rooms = [{ id: 'r1', room_number: '101', room_type: 'Standard' }, { id: 'r2', room_number: '102' }];

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  api.get.mockImplementation(url => Promise.resolve({ data:
    url === '/minibar/items' ? { items: [item] }
      : url === '/pms/rooms' ? rooms
        : url === '/minibar/inventory-products' ? { items: [product] }
          : url === '/minibar/consumptions' ? { consumptions: [] } : { late_charges: [] },
  }));
  api.post.mockResolvedValue({ data: { posted_to_folio: true, stock_complete: true, stock: [{ status: 'depleted' }] } });
  api.put.mockResolvedValue({ data: {} });
});

async function fillConsumption() {
  await screen.findByRole('button', { name: 'Maden Suyu miktarını artır' });
  fireEvent.change(screen.getByTestId('minibar-room-select'), { target: { value: 'r1' } });
  fireEvent.click(screen.getByRole('button', { name: 'Maden Suyu miktarını artır' }));
}

describe('Minibar inventory and recovery', () => {
  it('does not send a charge if the exact request cannot be retained before sending', async () => {
    render(<MinibarPage user={staff} />);
    await fillConsumption();
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => { throw new Error('storage unavailable'); });
    try {
      fireEvent.click(screen.getByTestId('minibar-submit'));
      expect(await screen.findByText(/Tüketim isteği güvenle saklanamadı/)).toHaveAttribute('role', 'alert');
      expect(api.post).not.toHaveBeenCalled();
      expect(screen.getByTestId('minibar-submit')).toBeDisabled();
    } finally { storage.mockRestore(); }
  });

  it('replays an uncertain request after a full page remount without creating a new key', async () => {
    api.post.mockRejectedValueOnce(new Error('lost response'));
    const view = render(<MinibarPage user={staff} />);
    await fillConsumption();
    fireEvent.click(screen.getByTestId('minibar-submit'));
    await screen.findByText(/Son tüketim isteğinin sonucu doğrulanamadı/);
    const original = structuredClone(api.post.mock.calls[0][1]);
    view.unmount();
    render(<MinibarPage user={staff} />);
    await screen.findByRole('button', { name: 'Maden Suyu miktarını artır' });
    expect(screen.getByTestId('minibar-room-select')).toBeDisabled();
    fireEvent.click(screen.getByTestId('minibar-submit'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[1][1]).toEqual(original);
    await waitFor(() => expect(sessionStorage.getItem('syroce:minibar:pending:demo:manager')).toBeNull());
  });

  it('does not restore a pending request into another property', async () => {
    sessionStorage.setItem('syroce:minibar:pending:demo:manager', JSON.stringify({ room_id: 'r1', lines: [{ item_id: 'water', quantity: 1 }], idempotency_key: 'old' }));
    const view = render(<MinibarPage user={staff} />);
    expect(screen.getByText(/Son tüketim isteğinin sonucu doğrulanamadı/)).toBeInTheDocument();
    view.rerender(<MinibarPage user={{ ...staff, tenant_id: 'other-hotel' }} />);
    await screen.findByRole('button', { name: 'Maden Suyu miktarını artır' });
    expect(screen.queryByText(/Son tüketim isteğinin sonucu doğrulanamadı/)).not.toBeInTheDocument();
    expect(screen.getByTestId('minibar-room-select')).toHaveValue('');
    expect(api.post).not.toHaveBeenCalled();
  });

  it('blocks a new write if pending evidence is malformed', async () => {
    sessionStorage.setItem('syroce:minibar:pending:demo:manager', '{broken');
    render(<MinibarPage user={staff} />);
    expect(screen.getByText(/Önceki minibar isteği güvenle okunamadı/)).toHaveAttribute('role', 'alert');
    await fillConsumption();
    expect(screen.getByTestId('minibar-submit')).toBeDisabled();
    expect(api.post).not.toHaveBeenCalled();
  });

  it('selects a tenant central warehouse product by name, not a raw ID', async () => {
    const user = userEvent.setup();
    render(<MinibarPage user={staff} />);
    await user.click(await screen.findByTestId('tab-catalog'));
    await user.click(screen.getByRole('button', { name: 'Maden Suyu ürününü düzenle' }));
    fireEvent.change(screen.getByLabelText('Merkezî stok ürünü'), { target: { value: 'accounting:central-water' } });
    await user.click(screen.getByRole('button', { name: 'Kaydet' }));
    await waitFor(() => expect(api.put).toHaveBeenCalledWith('/minibar/items/water', expect.objectContaining({
      inventory_product_id: 'central-water', inventory_source: 'accounting', currency: 'TRY', tax_rate: .2,
    })));
    expect(screen.queryByText(/Envanter Ürün ID/)).not.toBeInTheDocument();
  });

  it('preserves the exact original request on an uncertain response and prevents cart/room changes', async () => {
    api.post.mockRejectedValueOnce(new Error('response lost'));
    render(<MinibarPage user={staff} />);
    await fillConsumption();
    fireEvent.click(screen.getByTestId('minibar-submit'));
    expect(await screen.findByText(/Son tüketim isteğinin sonucu doğrulanamadı/)).toBeInTheDocument();
    expect(screen.getByTestId('minibar-room-select')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Maden Suyu miktarını artır' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Temizle' })).toBeDisabled();
    const original = structuredClone(api.post.mock.calls[0][1]);
    fireEvent.click(screen.getByTestId('minibar-submit'));
    await waitFor(() => expect(api.post).toHaveBeenCalledTimes(2));
    expect(api.post.mock.calls[1][1]).toEqual(original);
    expect(original.idempotency_key).toBeTruthy();
    await waitFor(() => expect(screen.queryByText(/Son tüketim isteğinin sonucu doğrulanamadı/)).not.toBeInTheDocument());
  });

  it('does not hide a pending stock operation behind a successful folio result', async () => {
    api.post.mockResolvedValueOnce({ data: { posted_to_folio: true, stock_complete: false, stock: [{ status: 'insufficient_stock' }] } });
    render(<MinibarPage user={staff} />);
    await fillConsumption();
    fireEvent.click(screen.getByTestId('minibar-submit'));
    await waitFor(() => expect(toast.warning).toHaveBeenCalledWith(expect.stringContaining('stok hareketleri tamamlanamadı')));
  });

  it('maps an old untracked line with a reason and never reposts consumption', async () => {
    const user = userEvent.setup();
    const oldGet = api.get.getMockImplementation();
    api.get.mockImplementation((url, ...args) => url === '/minibar/consumptions'
      ? Promise.resolve({ data: { consumptions: [{ id: 'old-source', room_number: '101', total: 60, currency: 'TRY', status: 'posted',
        lines: [{ item_name: 'Maden Suyu', quantity: 1 }], stock_complete: false,
        stock: [{ line_no: 0, item_name: 'Maden Suyu', quantity: 1, status: 'legacy_untracked' }] }] } }) : oldGet(url, ...args));
    render(<MinibarPage user={staff} />);
    expect(await screen.findByText(/Eski kayıt — stok mutabakatı gerekli/)).toBeInTheDocument();
    await user.click(screen.getByRole('button', { name: 'Stok işlemini tamamla' }));
    fireEvent.change(screen.getByLabelText(/Maden Suyu × 1/), { target: { value: 'accounting:central-water' } });
    fireEvent.change(screen.getByLabelText('İşlem gerekçesi'), { target: { value: 'Sunum kaydının stok mutabakatı' } });
    await user.click(screen.getByRole('button', { name: 'Stok işlemini tamamla' }));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith('/minibar/consumptions/old-source/reconcile-stock', {
      reason: 'Sunum kaydının stok mutabakatı', bindings: [{ line_no: 0, inventory_product_id: 'central-water', inventory_source: 'accounting' }],
    }));
    expect(api.post.mock.calls.some(([url]) => url === '/minibar/consume')).toBe(false);
  });

  it('keeps a pending recovery visible if the retry API is unavailable', async () => {
    const user = userEvent.setup();
    const oldGet = api.get.getMockImplementation();
    api.get.mockImplementation((url, ...args) => url === '/minibar/consumptions'
      ? Promise.resolve({ data: { consumptions: [{ id: 'pending', room_number: '101', total: 60, currency: 'TRY', status: 'posted',
        stock_complete: false, stock: [{ line_no: 0, item_name: 'Maden Suyu', quantity: 1, status: 'insufficient_stock' }] }] } }) : oldGet(url, ...args));
    api.post.mockRejectedValueOnce(new Error('stock retry offline'));
    render(<MinibarPage user={staff} />);
    await user.click(await screen.findByRole('button', { name: 'Stok işlemini tamamla' }));
    fireEvent.change(screen.getByLabelText('İşlem gerekçesi'), { target: { value: 'Stok girişi yapıldı' } });
    await user.click(screen.getByRole('button', { name: 'Stok işlemini tamamla' }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(expect.stringContaining('Stok işlemi doğrulanamadı')));
    expect(screen.getByRole('dialog')).toBeInTheDocument();
    expect(screen.getByText(/Stok yetersiz/)).toBeInTheDocument();
  });

  it.each([
    ['/minibar/items', /Minibar kataloğu doğrulanamadı/],
    ['/minibar/consumptions', /Tüketim ve stok durumu doğrulanamadı/],
    ['/minibar/late-charges', /Geç ücret kayıtları yüklenemedi/],
    ['/minibar/inventory-products', /Merkezî stok ürünleri yüklenemedi/],
  ])('does not silently turn a failed %s read into an empty healthy list', async (path, message) => {
    const oldGet = api.get.getMockImplementation();
    api.get.mockImplementation((url, ...args) => url === path ? Promise.reject(new Error('offline')) : oldGet(url, ...args));
    render(<MinibarPage user={staff} />);
    expect(await screen.findByText(message)).toHaveAttribute('role', 'alert');
  });

  it('does not let a late previous-room response replace the selected room history', async () => {
    let resolvePrevious;
    const oldGet = api.get.getMockImplementation();
    api.get.mockImplementation((url, options) => {
      if (url === '/minibar/consumptions' && options?.params?.room_id === 'r1') return new Promise(resolve => { resolvePrevious = resolve; });
      if (url === '/minibar/consumptions' && options?.params?.room_id === 'r2') return Promise.resolve({ data: { consumptions: [{ id: 'new', room_number: '102', total: 120, currency: 'TRY', status: 'posted' }] } });
      return oldGet(url, options);
    });
    render(<MinibarPage user={staff} />);
    await screen.findByRole('option', { name: /Oda 101/ });
    fireEvent.change(screen.getByTestId('minibar-room-select'), { target: { value: 'r1' } });
    fireEvent.change(screen.getByTestId('minibar-room-select'), { target: { value: 'r2' } });
    expect(await screen.findByText('Oda 102 · 120 TRY')).toBeInTheDocument();
    await act(async () => resolvePrevious({ data: { consumptions: [{ id: 'old', room_number: '101', total: 60, currency: 'TRY', status: 'posted' }] } }));
    expect(screen.queryByText('Oda 101 · 60 TRY')).not.toBeInTheDocument();
    expect(screen.getByText('Oda 102 · 120 TRY')).toBeInTheDocument();
  });
});

describe('Minibar permission surface matches backend roles', () => {
  it.each(['super_admin', 'admin', 'supervisor', 'front_desk', 'housekeeping', 'staff', 'finance', 'procurement', 'sales', 'guest', 'agency_admin', 'agency_agent', 'call_center_agent'])(
    'has explicit capabilities for %s', role => {
      const capabilities = minibarCapabilities({ role });
      expect(capabilities.canManageCatalog).toBe(['super_admin', 'admin', 'supervisor'].includes(role));
      expect(capabilities.canConsume).toBe(['super_admin', 'admin', 'supervisor', 'front_desk', 'housekeeping', 'staff'].includes(role));
    },
  );

  it('preserves the explicit platform-superadmin flag', () => {
    expect(minibarCapabilities({ role: 'front_desk', is_super_admin: true })).toEqual({ canManageCatalog: true, canConsume: true });
  });

  it('does not offer consumption or warehouse controls to a finance-only user', async () => {
    render(<MinibarPage user={{ ...staff, role: 'finance' }} />);
    expect(await screen.findByRole('button', { name: 'Maden Suyu miktarını artır' })).toBeDisabled();
    expect(screen.queryByTestId('tab-catalog')).not.toBeInTheDocument();
    expect(api.get.mock.calls.some(([url]) => url === '/minibar/inventory-products')).toBe(false);
  });
});

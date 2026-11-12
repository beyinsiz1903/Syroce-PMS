import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { confirmDialog } from '@/lib/dialogs';

const axiosGet = vi.fn();
const axiosPost = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    post: (...args) => axiosPost(...args),
  },
}));

vi.mock('@/lib/dialogs', () => ({ confirmDialog: vi.fn().mockResolvedValue(true), alertDialog: vi.fn() }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import POSWaiterTerminal, { normalizeWaiterMenuItems, posErrorMessage } from '@/pages/POSWaiterTerminal';

describe('POS waiter menu regressions', () => {
  beforeEach(() => {
    localStorage.clear();
    axiosGet.mockReset();
    axiosPost.mockReset();
    confirmDialog.mockClear();
    confirmDialog.mockResolvedValue(true);
  });

  it('keeps unavailable products visible while excluding inactive products', () => {
    const items = normalizeWaiterMenuItems([
      { id: 'sold-out', name: 'QA Burger', price: '120', available: false, status: 'active' },
      { id: 'inactive', name: 'Eski ürün', price: 10, available: true, status: 'inactive' },
    ]);

    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({
      id: 'sold-out',
      item_name: 'QA Burger',
      unit_price: 120,
      available: false,
    });
  });

  it('shows the backend message from normalized service errors', () => {
    expect(posErrorMessage({
      response: { data: { detail: { status: 'error', message: 'Hedef masa dolu' } } },
    }, 'İşlem tamamlanamadı')).toBe('Hedef masa dolu');
  });

  it('opens a persisted check and keeps it available after sending to kitchen', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/v2/session') return Promise.resolve({ data: { tenant_id: 't1', actor_id: 'u1' } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', name: 'Restoran', currency: 'TRY' }] } });
      if (url === '/pos/table-layout/outlet-1') return Promise.resolve({ data: { tables: [{ id: 'table-1', table_number: '1', seats: 4, status: 'available' }] } });
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [{ id: 'burger', name: 'Burger', price: 100, tax_rate: 0.18, category: 'food', available: true }] } });
      if (url === '/pos/v2/orders/order-1') return Promise.resolve({ data: { order: {
        id: 'order-1', order_number: 'ORD-1', status: 'pending', payment_status: 'unpaid',
        grand_total: 118, order_items: [{ item_id: 'burger', item_name: 'Burger', quantity: 1, unit_price: 100, total: 100 }],
      } } });
      throw new Error(`Unexpected GET ${url}`);
    });
    axiosPost.mockResolvedValue({ data: { order_id: 'order-1' } });

    render(<POSWaiterTerminal />);
    fireEvent.click(await screen.findByTestId('outlet-outlet-1'));
    fireEvent.click(await screen.findByTestId('table-1'));
    await screen.findByTestId('menu-item-burger');
    fireEvent.change(screen.getByRole('textbox', { name: /Menüde ürün ara|Search menu items/ }), { target: { value: 'not found' } });
    expect(screen.queryByTestId('menu-item-burger')).not.toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', { name: /Menüde ürün ara|Search menu items/ }), { target: { value: 'burger' } });
    fireEvent.keyDown(screen.getByTestId('menu-item-burger'), { key: 'Enter' });
    fireEvent.click(screen.getByTestId('send-kitchen'));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/pos/v2/orders', expect.objectContaining({
      outlet_id: 'outlet-1',
      table_number: '1',
      items: [expect.objectContaining({ item_id: 'burger', quantity: 1 })],
    })));
    expect(await screen.findByTestId('active-order-summary')).toHaveTextContent('ORD-1');
    expect(screen.getByTestId('pay-cash')).toBeEnabled();
  });

  it('recovers the order id when a retried create request returns the idempotent envelope', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/v2/session') return Promise.resolve({ data: { tenant_id: 't1', actor_id: 'u1' } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', name: 'Restoran' }] } });
      if (url === '/pos/table-layout/outlet-1') return Promise.resolve({ data: { tables: [{ id: 'table-1', table_number: '1', seats: 4, status: 'available' }] } });
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [{ id: 'burger', name: 'Burger', price: 100, tax_rate: .1, available: true }] } });
      if (url === '/pos/v2/orders/order-replayed') return Promise.resolve({ data: { order: { id: 'order-replayed', order_number: 'ORD-REPLAY', status: 'pending', payment_status: 'unpaid', grand_total: 110, order_items: [] } } });
      throw new Error(`Unexpected GET ${url}`);
    });
    axiosPost.mockResolvedValue({ data: { idempotent: true, order: { id: 'order-replayed' } } });

    render(<POSWaiterTerminal />);
    fireEvent.click(await screen.findByTestId('outlet-outlet-1'));
    fireEvent.click(await screen.findByTestId('table-1'));
    fireEvent.click(await screen.findByTestId('menu-item-burger'));
    fireEvent.click(screen.getByTestId('send-kitchen'));

    expect(await screen.findByTestId('active-order-summary')).toHaveTextContent('ORD-REPLAY');
  });

  it('closes an open check with a cent-exact mixed payment', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/v2/session') return Promise.resolve({ data: { tenant_id: 't1', actor_id: 'u1' } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', name: 'Restoran', currency: 'TRY' }] } });
      if (url === '/pos/table-layout/outlet-1') return Promise.resolve({ data: { tables: [{ id: 'table-1', table_number: '1', seats: 4, status: 'occupied', current_order_id: 'order-1' }] } });
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [] } });
      if (url === '/pos/v2/orders/order-1') return Promise.resolve({ data: { order: {
        id: 'order-1', order_number: 'ORD-1', status: 'pending', payment_status: 'unpaid',
        grand_total: 118.01, order_items: [
          { line_id: 'line-1', item_id: 'burger', item_name: 'Burger', quantity: 1, unit_price: 100, total: 100, tax_rate: .1801 },
          { line_id: 'line-2', item_id: 'water', item_name: 'Su', quantity: 1, unit_price: 18.01, total: 18.01, tax_rate: 0 },
        ],
      } } });
      throw new Error(`Unexpected GET ${url}`);
    });
    axiosPost.mockImplementation(url => Promise.resolve(url === '/pos/v2/checkout/quote'
      ? { data: { quote_id: 'quote1', payable: 118.01, amount_foreign: 118.01, currency_code: 'TRY', base_currency: 'TRY', rate_used: 1 } }
      : { status: 200, data: { amount_paid: 118.01, payment_method: 'mixed' } }));

    render(<POSWaiterTerminal />);
    fireEvent.click(await screen.findByTestId('outlet-outlet-1'));
    fireEvent.click(await screen.findByTestId('table-1'));
    fireEvent.click(await screen.findByTestId('toggle-split-payment'));
    fireEvent.click(screen.getByTestId('submit-split-payment'));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/pos/v2/orders/close', expect.objectContaining({
      order_id: 'order-1', payment_method: 'mixed',
      payments: [{ method: 'cash', amount: 59 }, { method: 'card', amount: 59.01 }],
    })));
  });

  it('keeps the destination table identity after transferring an open check', async () => {
    let tableLoads = 0;
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/v2/session') return Promise.resolve({ data: { tenant_id: 't1', actor_id: 'u1' } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', name: 'Restoran', currency: 'TRY' }] } });
      if (url === '/pos/table-layout/outlet-1') {
        tableLoads += 1;
        return Promise.resolve({ data: { tables: tableLoads === 1 ? [
          { id: 'table-1', table_number: '1', seats: 4, status: 'occupied', current_order_id: 'order-1' },
          { id: 'table-2', table_number: '2', seats: 4, status: 'available' },
        ] : [
          { id: 'table-1', table_number: '1', seats: 4, status: 'available' },
          { id: 'table-2', table_number: '2', seats: 4, status: 'occupied', current_order_id: 'order-1' },
        ] } });
      }
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [] } });
      if (url === '/pos/v2/orders/order-1') return Promise.resolve({ data: { order: {
        id: 'order-1', order_number: 'ORD-1', status: 'pending', payment_status: 'unpaid',
        table_number: '1', grand_total: 100, order_items: [],
      } } });
      throw new Error(`Unexpected GET ${url}`);
    });
    axiosPost.mockResolvedValue({ data: { order_id: 'order-1', to_table: '2' } });

    render(<POSWaiterTerminal />);
    fireEvent.click(await screen.findByTestId('outlet-outlet-1'));
    fireEvent.click(await screen.findByTestId('table-1'));
    fireEvent.change(await screen.findByLabelText('Hedef masa'), { target: { value: '2' } });
    fireEvent.click(screen.getByTestId('transfer-table'));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith(
      '/pos/v2/orders/order-1/transfer-table',
      { to_table_number: '2' },
    ));
    expect(await screen.findByRole('option', { name: 'Masa 1' })).toBeInTheDocument();
    expect(screen.queryByRole('option', { name: 'Masa 2' })).not.toBeInTheDocument();
  });

  it.each([true, false])('confirms table merge and keeps the target check identity (confirm=%s)', async (approved) => {
    let merged = false;
    confirmDialog.mockResolvedValue(approved);
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/v2/session') return Promise.resolve({ data: { tenant_id: 't1', actor_id: 'u1' } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', name: 'Restoran', currency: 'TRY' }] } });
      if (url === '/pos/table-layout/outlet-1') return Promise.resolve({ data: { tables: [
        { id: 'table-1', table_number: '1', status: merged ? 'available' : 'occupied', current_order_id: merged ? null : 'order-1' },
        { id: 'table-2', table_number: '2', status: 'occupied', current_order_id: 'order-2' },
        { id: 'legacy-table', table_number: '3', status: 'occupied', current_transaction_id: 'legacy-sale' },
      ] } });
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [] } });
      if (url.startsWith('/pos/v2/orders/')) {
        const target = url.endsWith('/order-2');
        return Promise.resolve({ data: { order: { id: target ? 'order-2' : 'order-1', order_number: target ? 'ORD-TARGET' : 'ORD-SOURCE',
          status: 'pending', payment_status: 'unpaid', table_number: target ? '2' : '1', grand_total: target ? 330 : 110,
          order_items: [{ line_id: 'line1', item_name: 'Çay', quantity: 1, total: 100 }],
        } } });
      }
      throw new Error(`Unexpected GET ${url}`);
    });
    axiosPost.mockImplementation(() => { merged = true; return Promise.resolve({ data: { target_order_id: 'order-2' } }); });
    render(<POSWaiterTerminal />);
    fireEvent.click(await screen.findByTestId('outlet-outlet-1'));
    fireEvent.click(await screen.findByTestId('table-1'));
    fireEvent.change(await screen.findByLabelText('Hedef masa'), { target: { value: '2' } });
    expect(screen.getByTestId('transfer-table')).toHaveTextContent('Birleştir');
    expect(screen.queryByRole('option', { name: /Masa 3/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId('transfer-table'));
    await waitFor(() => expect(confirmDialog).toHaveBeenCalledWith(expect.objectContaining({ message: expect.stringContaining('Tahsilat yapılmaz') })));
    if (approved) {
      await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/pos/v2/orders/order-1/merge-table', { target_order_id: 'order-2' }));
      await waitFor(() => expect(screen.getByTestId('active-order-summary')).toHaveTextContent('ORD-TARGET'));
      expect(screen.getByRole('option', { name: 'Masa 1' })).toBeInTheDocument();
      expect(screen.queryByRole('option', { name: /Masa 2/ })).not.toBeInTheDocument();
    } else {
      expect(axiosPost).not.toHaveBeenCalled();
      expect(screen.getByTestId('active-order-summary')).toHaveTextContent('ORD-SOURCE');
    }
  });

  it('requires new cart lines to be sent before transferring or merging an existing check', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/v2/session') return Promise.resolve({ data: { tenant_id: 't1', actor_id: 'u1' } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', name: 'Restoran' }] } });
      if (url === '/pos/table-layout/outlet-1') return Promise.resolve({ data: { tables: [
        { id: 'table-1', table_number: '1', status: 'occupied', current_order_id: 'order-1' },
        { id: 'table-2', table_number: '2', status: 'occupied', current_order_id: 'order-2' },
      ] } });
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [{ id: 'tea', name: 'Çay', price: 100, available: true }] } });
      if (url === '/pos/v2/orders/order-1') return Promise.resolve({ data: { order: {
        id: 'order-1', order_number: 'ORD-1', status: 'pending', payment_status: 'unpaid', grand_total: 100, order_items: [],
      } } });
      throw new Error(`Unexpected GET ${url}`);
    });
    render(<POSWaiterTerminal />);
    fireEvent.click(await screen.findByTestId('outlet-outlet-1'));
    fireEvent.click(await screen.findByTestId('table-1'));
    fireEvent.change(await screen.findByLabelText('Hedef masa'), { target: { value: '2' } });
    fireEvent.click(await screen.findByTestId('menu-item-tea'));
    expect(screen.getByTestId('transfer-table')).toBeDisabled();
    expect(axiosPost).not.toHaveBeenCalled();
  });
});

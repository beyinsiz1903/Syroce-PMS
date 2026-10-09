import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();
const axiosPost = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    post: (...args) => axiosPost(...args),
  },
}));

vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

import POSWaiterTerminal, { normalizeWaiterMenuItems, posErrorMessage } from '@/pages/POSWaiterTerminal';

describe('POS waiter menu regressions', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPost.mockReset();
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
    fireEvent.click(await screen.findByTestId('menu-item-burger'));
    fireEvent.click(screen.getByTestId('send-kitchen'));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/pos/v2/orders', expect.objectContaining({
      outlet_id: 'outlet-1',
      table_number: '1',
      items: [expect.objectContaining({ item_id: 'burger', price: 100, tax_rate: 0.18 })],
    })));
    expect(await screen.findByTestId('active-order-summary')).toHaveTextContent('ORD-1');
    expect(screen.getByTestId('pay-cash')).toBeEnabled();
  });

  it('recovers the order id when a retried create request returns the idempotent envelope', async () => {
    axiosGet.mockImplementation((url) => {
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
    axiosPost.mockResolvedValue({ status: 200, data: { amount_paid: 118.01, payment_method: 'mixed' } });

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
});

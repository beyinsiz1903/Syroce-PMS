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

import POSWaiterTerminal, { normalizeWaiterMenuItems } from '@/pages/POSWaiterTerminal';

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
});

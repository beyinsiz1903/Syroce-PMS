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

  it('partitions selected units into another free table without checkout or new kitchen submission', async () => {
    let split = false;
    axiosGet.mockImplementation(url => {
      if (url === '/pos/v2/session') return Promise.resolve({ data: { tenant_id: 't1', actor_id: 'u1' } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'o1', name: 'Restoran', currency: 'TRY' }] } });
      if (url === '/pos/table-layout/o1') return Promise.resolve({ data: { tables: [
        { id: 't1', table_number: '1', status: 'occupied', current_order_id: 'order1' },
        { id: 't2', table_number: '2', status: split ? 'occupied' : 'available', current_order_id: split ? 'order2' : null },
        { id: 't3', table_number: '3', status: 'occupied', current_order_id: 'other' },
      ] } });
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [] } });
      if (url === '/pos/v2/orders/order1') return Promise.resolve({ data: { order: {
        id: 'order1', order_number: 'ORD-1', status: 'pending', payment_status: 'unpaid', grand_total: split ? 44 : 88,
        order_items: [{ line_id: 'line1', item_name: 'Su', quantity: split ? 1 : 2, unit_price: 40, total: split ? 40 : 80 }],
      } } });
      throw new Error(`Unexpected GET ${url}`);
    });
    axiosPost.mockImplementation(url => {
      if (url === '/pos/v2/orders/order1/split-items') { split = true; return Promise.resolve({ data: { target_order_id: 'order2', to_table: '2' } }); }
      throw new Error(`Unexpected POST ${url}`);
    });
    render(<POSWaiterTerminal />);
    fireEvent.click(await screen.findByTestId('outlet-o1'));
    fireEvent.click(await screen.findByTestId('table-1'));
    fireEvent.click(await screen.findByTestId('toggle-item-split'));
    expect(screen.getByTestId('submit-item-split')).toBeDisabled();
    const target = screen.getByRole('combobox', { name: 'Yeni adisyon masası' });
    expect(target).not.toHaveTextContent('Masa 3');
    fireEvent.change(screen.getByRole('spinbutton', { name: 'Su bölünecek adet' }), { target: { value: '1' } });
    fireEvent.change(target, { target: { value: '2' } });
    fireEvent.click(screen.getByTestId('submit-item-split'));
    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/pos/v2/orders/order1/split-items', {
      to_table_number: '2', quantities: { line1: 1 }, request_id: expect.any(String),
    }));
    await waitFor(() => expect(screen.queryByTestId('item-split-panel')).not.toBeInTheDocument());
    expect(axiosPost).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId('active-order-summary')).toHaveTextContent('1 × Su');
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

  it('quotes the selected full-comp room and confirms a zero-debt transfer', async () => {
    const context = { beginPath: vi.fn(), moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn() };
    const getContext = vi.spyOn(window.HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context);
    const toDataURL = vi.spyOn(window.HTMLCanvasElement.prototype, 'toDataURL').mockReturnValue('data:image/png;base64,synthetic');
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/v2/session') return Promise.resolve({ data: { tenant_id: 't1', actor_id: 'u1' } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', name: 'Restoran', currency: 'TRY' }] } });
      if (url === '/pos/table-layout/outlet-1') return Promise.resolve({ data: { tables: [{ id: 'table-1', table_number: '1', status: 'occupied', current_order_id: 'order-1' }] } });
      if (url === '/pos/menu-items') return Promise.resolve({ data: { menu_items: [] } });
      if (url === '/frontdesk/inhouse') return Promise.resolve({ data: [{ id: 'booking-1', guest_name: 'Sentetik Misafir', room_number: '104' }] });
      if (url === '/pos/v2/orders/order-1') return Promise.resolve({ data: { order: {
        id: 'order-1', order_number: 'ORD-1', status: 'pending', payment_status: 'unpaid', grand_total: 132,
        order_items: [{ item_id: 'soup', item_name: 'Çorba', quantity: 1, total: 120, tax_rate: .1 }],
      } } });
      throw new Error(`Unexpected GET ${url}`);
    });
    axiosPost.mockImplementation(url => Promise.resolve(url === '/pos/v2/checkout/quote'
      ? { data: { quote_id: 'comp-quote', payable: 0, base_currency: 'TRY', is_complimentary: true, complimentary_discount: 132 } }
      : { status: 200, data: { amount_paid: 0, payment_method: 'room_charge' } }));
    try {
      render(<POSWaiterTerminal />);
      fireEvent.click(await screen.findByTestId('outlet-outlet-1'));
      fireEvent.click(await screen.findByTestId('table-1'));
      fireEvent.focus(await screen.findByTestId('room-guest-search'));
      fireEvent.click(await screen.findByTestId('inhouse-booking-1'));
      const canvas = screen.getByTestId('signature-pad');
      canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 320, height: 120 });
      fireEvent.mouseDown(canvas, { clientX: 10, clientY: 10 });
      fireEvent.mouseMove(canvas, { clientX: 30, clientY: 30 });
      fireEvent.mouseUp(canvas);
      fireEvent.click(screen.getByTestId('pay-room'));
      await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/pos/v2/orders/close', expect.objectContaining({
        booking_id: 'booking-1', post_to_folio: true, payment_method: 'room_charge',
        checkout_options: expect.objectContaining({ quote_id: 'comp-quote' }),
      })));
      expect(axiosPost).toHaveBeenCalledWith('/pos/v2/checkout/quote', expect.objectContaining({
        order_id: 'order-1', booking_id: 'booking-1', post_to_folio: true,
      }));
      expect(confirmDialog).toHaveBeenCalledWith({ message: expect.stringContaining('Tam ikram kapsamında:') });
      expect(confirmDialog.mock.calls[0][0].message).toContain('Misafire borç yazılmayacak.');
      expect(confirmDialog.mock.calls[0][0].message).not.toContain('Tahsilat:');
    } finally {
      getContext.mockRestore();
      toDataURL.mockRestore();
    }
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

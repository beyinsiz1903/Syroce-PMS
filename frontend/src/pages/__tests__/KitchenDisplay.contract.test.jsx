import { act, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

const apiGet = vi.hoisted(() => vi.fn());
const subscribe = vi.hoisted(() => vi.fn());
vi.mock('axios', () => ({ default: { get: apiGet } }));
vi.mock('@/lib/websocket', () => ({
  useWebSocket: () => ({ isConnected: true }),
  websocket: { on: subscribe },
}));

import KitchenDisplay, { normalizeKitchenOrders } from '@/pages/KitchenDisplay';

describe('KitchenDisplay order contract', () => {
  it('normalizes v2 single-line kitchen tickets into visible items', () => {
    expect(normalizeKitchenOrders([{
      id: 'ticket-1',
      item_name: 'Izgara',
      quantity: 2,
      special_instructions: 'Az pişmiş',
      station: 'hot_kitchen',
    }])[0].items).toEqual([{
      id: 'ticket-1',
      name: 'Izgara',
      quantity: 2,
      notes: 'Az pişmiş',
      station: 'hot_kitchen',
    }]);
  });

  it('preserves grouped tickets while normalizing item labels', () => {
    expect(normalizeKitchenOrders([{ id: 'ticket-2', items: [{ item_name: 'Çorba', quantity: 1 }] }])[0].items[0].name).toBe('Çorba');
  });

  it('reads the authorized queue again on a tenant change signal and shows the room number', async () => {
    let notify;
    subscribe.mockImplementation((event, callback) => {
      if (event === 'kitchen_orders_changed') notify = callback;
      return () => {};
    });
    apiGet.mockResolvedValueOnce({ data: { orders: [] } })
      .mockResolvedValueOnce({ data: { orders: [{
        id: 'ticket-1', room_number: '131', status: 'pending',
        items: [{ name: 'Misafir öğle menüsü', quantity: 1 }],
      }] } });
    render(<MemoryRouter><KitchenDisplay /></MemoryRouter>);
    expect(await screen.findByRole('heading', { name: 'Mutfak Ekranı' })).toBeVisible();
    expect(notify).toBeTypeOf('function');

    act(() => notify());
    expect(await screen.findByText('Oda 131')).toBeVisible();
    expect(apiGet).toHaveBeenNthCalledWith(2, '/fnb/kitchen-display');
  });
});

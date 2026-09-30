import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();
const axiosPut = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    put: (...args) => axiosPut(...args),
  },
}));

vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/components/PropertySwitcher', () => ({ default: () => null }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_key, fallback) => fallback || 'Tümü' }) }));

import MobileOrderTracking from '@/pages/MobileOrderTracking';

const order = {
  id: 'order-1',
  order_number: '1001',
  status: 'pending',
  outlet_name: 'Ana Restoran',
  table_number: '12',
  guest_name: 'Masa Misafiri',
  items_count: 1,
  total_amount: 250,
  currency: 'TRY',
  time_elapsed_minutes: 4,
};

describe('MobileOrderTracking regressions', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPut.mockReset();
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/mobile/active-orders') return Promise.resolve({ data: { orders: [order] } });
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [{ id: 'outlet-1', outlet_name: 'Ana Restoran', status: 'active' }] } });
      throw new Error(`Unexpected GET ${url}`);
    });
  });

  it('prevents duplicate status requests while the first update is in flight', async () => {
    let resolveUpdate;
    axiosPut.mockImplementation(() => new Promise((resolve) => { resolveUpdate = resolve; }));

    render(<MobileOrderTracking user={{ role: 'fnb_manager' }} />);

    const action = await screen.findByRole('button', { name: 'Hazırlanıyor' });
    fireEvent.click(action);
    fireEvent.click(action);

    expect(axiosPut).toHaveBeenCalledTimes(1);
    expect(axiosPut).toHaveBeenCalledWith('/pos/mobile/order/order-1/status', expect.objectContaining({ status: 'preparing' }));

    resolveUpdate({ data: { new_status: 'preparing' } });
    await waitFor(() => expect(screen.getByRole('button', { name: 'Hazırlanıyor' })).toBeEnabled());
  });

  it('offers outlet filtering and sends the selected outlet to the API', async () => {
    render(<MobileOrderTracking user={{ role: 'fnb_manager' }} />);
    await screen.findByText('#1001');

    fireEvent.click(screen.getByRole('button', { name: 'Filtrele' }));
    fireEvent.change(screen.getByLabelText('Satış noktası'), { target: { value: 'outlet-1' } });

    await waitFor(() => expect(axiosGet).toHaveBeenCalledWith(
      '/pos/mobile/active-orders',
      { params: { outlet_id: 'outlet-1' } },
    ));
  });

  it('keeps a visible retry action when the active-order request fails', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/mobile/active-orders') return Promise.reject(new Error('offline'));
      if (url === '/pos/outlets') return Promise.resolve({ data: { outlets: [] } });
      throw new Error(`Unexpected GET ${url}`);
    });

    render(<MobileOrderTracking user={{ role: 'fnb_manager' }} />);

    expect(await screen.findByRole('alert')).toHaveTextContent('Sipariş listesine ulaşılamadı');
    expect(screen.getByRole('button', { name: /Yeniden dene/ })).toBeEnabled();
  });
});

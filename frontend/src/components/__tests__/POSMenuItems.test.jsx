import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();
const axiosPut = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    put: (...args) => axiosPut(...args),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import POSMenuItems from '@/components/POSMenuItems';

describe('POSMenuItems', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPut.mockReset();
    axiosGet.mockResolvedValue({
      data: {
        menu_items: [{
          id: 'burger-1',
          outlet_id: 'outlet-1',
          name: 'QA Burger',
          category: 'food',
          price: 120,
          cost: 45,
          tax_rate: 0.1,
          available: true,
        }],
      },
    });
    axiosPut.mockResolvedValue({ data: { message: 'updated' } });
  });

  it('retains the item outlet when editing from the aggregate view', async () => {
    render(<POSMenuItems outletId={null} />);

    fireEvent.click(await screen.findByTestId('button-edit-menu-burger-1'));
    fireEvent.click(screen.getByRole('switch', { name: 'Satışta' }));
    fireEvent.click(screen.getByTestId('button-save-menu-item'));

    await waitFor(() => expect(axiosPut).toHaveBeenCalledTimes(1));
    expect(axiosPut).toHaveBeenCalledWith(
      '/pos/menu-item/burger-1',
      expect.objectContaining({ outlet_id: 'outlet-1', available: false }),
    );
  });
});

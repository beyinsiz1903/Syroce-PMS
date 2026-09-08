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

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

import POSTableManagement from '@/components/POSTableManagement';

describe('POSTableManagement', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPut.mockReset();
    axiosGet.mockResolvedValue({
      data: {
        available: 1,
        occupied: 0,
        reserved: 0,
        tables: [{ id: 'table-1', table_number: '1', seats: 4, status: 'available' }],
      },
    });
    axiosPut.mockResolvedValue({ data: { success: true } });
  });

  it('uses the persisted table-layout API and can change table status', async () => {
    render(<POSTableManagement outletId="outlet-1" />);

    expect(await screen.findByText('4 seats')).toBeInTheDocument();
    expect(axiosGet).toHaveBeenCalledWith('/pos/table-layout/outlet-1');

    fireEvent.click(screen.getByRole('button', { name: /Occupy/i }));
    await waitFor(() => expect(axiosPut).toHaveBeenCalledWith('/pos/tables/table-1/status?new_status=occupied'));
  });
});

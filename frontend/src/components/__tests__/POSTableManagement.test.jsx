import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const axiosGet = vi.fn();
const axiosPut = vi.fn();
const axiosPost = vi.fn();

vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    put: (...args) => axiosPut(...args),
    post: (...args) => axiosPost(...args),
  },
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/lib/dialogs', () => ({
  confirmDialog: vi.fn().mockResolvedValue(true),
}));

import POSTableManagement from '@/components/POSTableManagement';

describe('POSTableManagement', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPut.mockReset();
    axiosPost.mockReset();
    axiosGet.mockResolvedValue({
      data: {
        available: 1,
        occupied: 0,
        reserved: 0,
        tables: [{ id: 'table-1', table_number: '1', seats: 4, status: 'available' }],
      },
    });
    axiosPut.mockResolvedValue({ data: { success: true } });
    axiosPost.mockResolvedValue({ data: { success: true } });
  });

  it('uses the persisted table-layout API and can change table status', async () => {
    render(<POSTableManagement outletId="outlet-1" />);

    expect(await screen.findByText('4 kişilik')).toBeInTheDocument();
    expect(axiosGet).toHaveBeenCalledWith('/pos/table-layout/outlet-1');

    fireEvent.click(screen.getByRole('button', { name: /Dolu Yap/i }));
    await waitFor(() => expect(axiosPut).toHaveBeenCalledWith(
      '/pos/tables/table-1/status',
      null,
      { params: { new_status: 'occupied' } },
    ));
  });

  it('shows the live check and transfers it to an available table', async () => {
    axiosGet.mockResolvedValue({
      data: {
        available: 1,
        occupied: 1,
        reserved: 0,
        tables: [
          { id: 'table-1', table_number: '1', seats: 4, status: 'occupied', current_transaction_id: 'check-1', current_bill: 250, guest_count: 2, duration_minutes: 18 },
          { id: 'table-2', table_number: '2', seats: 4, status: 'available' },
        ],
      },
    });

    render(<POSTableManagement outletId="outlet-1" />);

    expect(await screen.findByText('Açık adisyon')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Masa 1 hedef masa'), { target: { value: '2' } });
    fireEvent.click(screen.getByRole('button', { name: /Adisyonu Aktar/i }));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith(
      '/pos/transfer-table',
      null,
      { params: { from_table: '1', to_table: '2', outlet_id: 'outlet-1', transfer_all: true } },
    ));
  });

  it('creates a table reservation and advances a confirmed reservation to seated', async () => {
    axiosGet.mockImplementation((url) => {
      if (url === '/pos/reservations') {
        return Promise.resolve({ data: [{ id: 'res-1', table_id: 'table-1', guest_name: 'Ayşe Yılmaz', pax: 3, res_date: '2026-10-02', res_time: '19:30', status: 'confirmed' }] });
      }
      return Promise.resolve({
        data: {
          available: 1,
          occupied: 0,
          reserved: 0,
          tables: [{ id: 'table-1', table_number: '1', seats: 4, status: 'available' }],
        },
      });
    });

    render(<POSTableManagement outletId="outlet-1" />);

    expect(await screen.findByText(/Ayşe Yılmaz/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Masaya Al' }));
    await waitFor(() => expect(axiosPut).toHaveBeenCalledWith(
      '/pos/reservations/res-1/status',
      null,
      { params: { status: 'seated' } },
    ));

    fireEvent.click(screen.getByRole('button', { name: 'Rezervasyon Ekle' }));
    fireEvent.change(screen.getByLabelText('Misafir adı'), { target: { value: 'Mehmet Demir' } });
    fireEvent.change(screen.getByLabelText('Rezervasyon masası'), { target: { value: 'table-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith('/pos/reservations', expect.objectContaining({
      outlet_id: 'outlet-1',
      table_id: 'table-1',
      guest_name: 'Mehmet Demir',
      pax: 2,
    })));
  });
});

import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import InventoryTransferHistory from '../InventoryTransferHistory';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));

const record = {
  transfer_id: 't', created_at: '2026-10-07', line_count: 2, quantity: 5, balanced: false,
  total_value: null, total_value_by_currency: { EUR: 20, TRY: 30 },
  lines: [{ source_item_id: 'a', destination_item_id: 'b', quantity: 2, out_quantity: 2, in_quantity: 0, balanced: false }],
};
const show = () => render(<MemoryRouter><InventoryTransferHistory /></MemoryRouter>);

describe('Inventory transfer reporting', () => {
  beforeEach(() => { axios.get.mockReset(); axios.get.mockResolvedValue({ data: { transfers: [record], count: 1, total_count: 2 } }); });
  afterEach(() => { cleanup(); vi.clearAllMocks(); });

  it('shows document lines, mismatched legs, native values and the report limit', async () => {
    show();
    expect(await screen.findByText('2 kalem · ayrıntılar')).toBeInTheDocument();
    expect(screen.getByText('Giriş/çıkış eşleşmiyor')).toBeInTheDocument();
    expect(screen.getByText(/20,00/)).toHaveTextContent('EUR');
    expect(screen.getByText(/20,00/)).toHaveTextContent('TRY');
    expect(screen.queryByText('₺50,00')).not.toBeInTheDocument();
    expect(screen.getByTestId('transfer-count')).toHaveTextContent('1 / 2');
  });

  it('sends the selected calendar dates without browser timezone conversion', async () => {
    show();
    await screen.findByTestId('transfer-row-t');
    fireEvent.change(screen.getByTestId('filter-start-date'), { target: { value: '2026-10-01' } });
    fireEvent.change(screen.getByTestId('filter-end-date'), { target: { value: '2026-10-07' } });
    await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith('/accounting/inventory/transfers', { params: { limit: 200, start_date: '2026-10-01', end_date: '2026-10-07' } }));
  });

  it('does not call a legacy unit conversion a confirmed mismatch', async () => {
    axios.get.mockResolvedValue({ data: { transfers: [{ ...record, line_count: 1, balanced: null,
      lines: [{ out_quantity: 5, in_quantity: 20, source_unit: 'kg', destination_unit: 'adet' }],
    }], count: 1 } });
    show();
    expect(await screen.findByText('Birim dönüşümü doğrulanamıyor')).toBeInTheDocument();
    expect(screen.queryByText('Giriş/çıkış eşleşmiyor')).not.toBeInTheDocument();
    expect(screen.getByText(/Çıkış: 5 kg/)).toHaveTextContent('Giriş: 20 adet');
  });

  it('does not present an unavailable report as no transactions', async () => {
    axios.get.mockRejectedValue({ response: { data: { detail: 'Rapor servisi kapalı' } } });
    show();
    expect(await screen.findByRole('alert')).toHaveTextContent('Rapor servisi kapalı');
    expect(screen.queryByTestId('no-transfers')).not.toBeInTheDocument();
  });

  it('ignores the response for an older period arriving after the latest response', async () => {
    let finishOld;
    axios.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }));
    show();
    fireEvent.change(screen.getByTestId('filter-start-date'), { target: { value: '2026-10-01' } });
    await screen.findByTestId('transfer-row-t');
    await act(async () => finishOld({ data: { transfers: [{ ...record, transfer_id: 'old' }], count: 1 } }));
    expect(screen.queryByTestId('transfer-row-old')).not.toBeInTheDocument();
    expect(screen.getByTestId('transfer-row-t')).toBeInTheDocument();
  });
});

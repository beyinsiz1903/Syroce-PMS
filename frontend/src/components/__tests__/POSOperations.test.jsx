import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import POSOperations from '@/components/POSOperations';

vi.mock('axios');
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));

describe('POSOperations', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: {
      business_date: '2026-10-09', open_check_count: 1, open_check_total: 220,
      kitchen_open_count: 2, kitchen_overdue_count: 1, payment_methods: { cash: 500 },
      refund_total: 50, net_collected: 450,
      open_orders: [{ id: 'o1', order_number: 'ORD-1', table_number: '4', status: 'preparing', grand_total: 220, created_at: new Date().toISOString() }],
    } });
  });

  it('shows live checks, kitchen SLA and cashier reconciliation', async () => {
    render(<POSOperations outletId="outlet-1" />);
    await waitFor(() => expect(screen.getByText('ORD-1')).toBeInTheDocument());
    expect(screen.getByText('Canlı Operasyon ve Kasa')).toBeInTheDocument();
    expect(screen.getByText('20 dk üzeri')).toBeInTheDocument();
    expect(screen.getByText('Net tahsilat')).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledWith('/pos/v2/operations/summary', { params: { outlet_id: 'outlet-1' } });
  });
});

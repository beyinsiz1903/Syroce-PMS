import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import TransferParkingPage from '@/pages/TransferParkingPage';

const { get, post, deleteRequest, confirmDialog, feature } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  deleteRequest: vi.fn(),
  confirmDialog: vi.fn(),
  feature: vi.fn(() => false),
}));

vi.mock('axios', () => ({
  default: { get, post, delete: deleteRequest },
}));

vi.mock('@/lib/dialogs', () => ({ confirmDialog }));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('@/context/EntitlementContext', () => ({
  useEntitlements: () => ({
    getLimit: () => 10,
    hasFeature: feature,
  }),
}));

afterEach(() => cleanup());

describe('Transfer and parking regressions', () => {
  beforeEach(() => {
    get.mockReset(); post.mockReset(); post.mockResolvedValue({ data: {} });
    deleteRequest.mockReset();
    confirmDialog.mockReset();
    confirmDialog.mockResolvedValue(true);
    deleteRequest.mockResolvedValue({ data: { ok: true } });
    get.mockImplementation((url) => {
      if (url === '/transfer-parking/resources') return Promise.resolve({ data: { resources: [] } });
      if (url === '/transfer-parking/bookings') return Promise.resolve({ data: { bookings: [{
        id: 'transport-1', kind: 'transfer_vehicle', resource_name: 'QA Transfer',
        room_number: '998', guest_name: 'QA', total: 500, currency: 'USD', status: 'reserved',
        folio_charged: false, schedule: { pickup_at: '2026-11-11T00:00:00Z' },
      }] } });
      if (url === '/transfer-parking/late-charges') return Promise.resolve({ data: { late_charges: [] } });
      return Promise.resolve({ data: {} });
    });
  });

  it('refreshes bookings and late charges after cancellation', async () => {
    render(<MemoryRouter><TransferParkingPage /></MemoryRouter>);

    await screen.findByText('QA Transfer');
    expect(screen.getByText(/\$500\.00/)).toBeInTheDocument();
    const row = screen.getByText('QA Transfer').closest('tr');
    fireEvent.click(row.querySelector('button'));

    await waitFor(() => expect(deleteRequest).toHaveBeenCalledWith('/transfer-parking/bookings/transport-1'));
    await waitFor(() => {
      expect(get.mock.calls.filter(([url]) => url === '/transfer-parking/bookings')).toHaveLength(2);
      expect(get.mock.calls.filter(([url]) => url === '/transfer-parking/late-charges')).toHaveLength(2);
    });
  });
});


it('records an external parking payment once without posting to PMS', async () => {
  get.mockImplementation(url => {
    if (url === '/transfer-parking/resources') return Promise.resolve({ data: { resources: [] } });
    if (url === '/transfer-parking/bookings') return Promise.resolve({ data: { bookings: [{
      id: 'external', kind: 'parking_spot', resource_name: 'Dış otopark', customer_type: 'external',
      guest_name: 'Selin Acar', total: 150, currency: 'TRY', status: 'reserved', payment_status: 'unpaid',
      schedule: { start_date: '2026-11-12', num_days: 1 },
    }] } });
    return Promise.resolve({ data: {} });
  });
  post.mockReset();
  let resolve;
  post.mockReturnValue(new Promise(done => { resolve = done; }));
  render(<MemoryRouter><TransferParkingPage /></MemoryRouter>);
  fireEvent.click(await screen.findByRole('button', { name: 'Ödeme kaydet' }));
  expect(screen.getByText(/oda folyosuna yazılmaz/)).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Ödeme / iade açıklaması'), { target: { value: 'Otopark nakit kaydı' } });
  fireEvent.click(screen.getByRole('button', { name: 'Ödemeyi kaydet' }));
  expect(post).toHaveBeenCalledTimes(1);
  expect(post).toHaveBeenCalledWith('/transfer-parking/bookings/external/settlement', {
    request_id: expect.any(String), amount: 150, currency: 'TRY', method: 'cash', reference: 'Otopark nakit kaydı',
  });
  resolve({ data: {} });
  await waitFor(() => expect(screen.queryByRole('button', { name: 'Ödemeyi kaydet' })).not.toBeInTheDocument());
});


it('posts a parking source once and shows its linked journal after refresh', async () => {
  feature.mockReturnValue(true);
  let posted = false;
  get.mockImplementation(url => Promise.resolve({ data: url === '/transfer-parking/analytics' ? {
    external_payment_entries: [{ id: 'parking:t:receipt:1', kind: 'receipt', reference: 'Receipt 001', amount: 150,
      currency: 'TRY', gl: posted ? { status: 'posted', entry_no: 'YEV-148' } : { status: 'pending' } }],
  } : {} }));
  let finish;
  post.mockReset().mockImplementation(() => new Promise(resolve => { finish = () => { posted = true; resolve({ data: {} }); }; }));
  render(<MemoryRouter><TransferParkingPage /></MemoryRouter>);
  fireEvent.mouseDown(screen.getByRole('tab', { name: 'Analiz' }), { button: 0, ctrlKey: false });
  const submit = await screen.findByRole('button', { name: 'Muhasebeye aktar' });
  fireEvent.click(submit); fireEvent.click(submit);
  expect(post).toHaveBeenCalledTimes(1);
  expect(post).toHaveBeenCalledWith('/transfer-parking/external-payments/parking%3At%3Areceipt%3A1/post-to-gl');
  finish();
  expect(await screen.findByText('YEV-148')).toBeInTheDocument();
  expect(screen.queryByRole('button', { name: 'Muhasebeye aktar' })).not.toBeInTheDocument();
  feature.mockReturnValue(false);
});

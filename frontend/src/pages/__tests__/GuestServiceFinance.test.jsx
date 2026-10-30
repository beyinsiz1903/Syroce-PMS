import React from 'react';
import { fireEvent, render, screen, waitFor, cleanup } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import UpsellTab from '@/components/pms/UpsellTab';
import RoomQrCodes from '@/pages/admin/RoomQrCodes';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));
vi.mock('@/lib/currency', () => ({ cachedTenantCurrency: () => 'TRY', currencySymbol: () => '₺', formatCurrency: (value, code) => `${code} ${value}` }));

afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe('source-owned guest service finance UI', () => {
  it('shows offer and posted currencies separately instead of relabeling everything TRY', async () => {
    axios.get.mockImplementation(url => Promise.resolve({ data: url.includes('revenue-insights') ? {
      kpis: { adr_by_currency: { USD: 100, TRY: 3000 }, revpar_by_currency: { USD: 50, TRY: 1500 } },
      upsell_summary: { revenue_by_currency: { USD: 20, TRY: 400 }, accepted: 3, total: 4, unreconciled_accepted: 1 },
    } : { offers: [
      { id: 'o', type: 'early_checkin', status: 'pending', price: 10, currency: 'USD' },
      { id: 'legacy', type: 'late_checkout', status: 'pending', price: 900 },
    ] } }));
    render(<UpsellTab />);
    expect(await screen.findByText('USD 10')).toBeInTheDocument();
    expect(screen.getByText('Para birimi doğrulanmamış')).toBeInTheDocument();
    expect(screen.getByText('USD 20 · TRY 400')).toBeInTheDocument();
    expect(screen.getByText(/eski kabulün folyo kaynağı doğrulanmadı/)).toBeInTheDocument();
  });

  it('preserves declared, explicit zero and unknown VAT when saving a loaded QR menu', async () => {
    axios.get.mockImplementation(url => Promise.resolve({ data: url.includes('bulk') ? { items: [] } : {
      items: [0.2, 0, null].map((rate, index) => ({ service_code: `fnb.qa_${index}`, labels: { tr: `QA ${index}` },
        unit_price_minor: 12000, currency: 'TRY', tax_rate: rate, enabled: true })),
    } }));
    axios.put.mockResolvedValue({ data: {} });
    render(<RoomQrCodes tenant={{ property_id: 'p' }} />);
    fireEvent.click(screen.getByRole('button', { name: 'Oda Servisi Menüsü' }));
    await screen.findByDisplayValue('20');
    expect(screen.getAllByLabelText('KDV oranı (bilinmiyorsa boş)').map(input => input.value)).toEqual(['20', '0', '']);
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));
    await waitFor(() => expect(axios.put).toHaveBeenCalledTimes(1));
    expect(axios.put.mock.calls[0][1].items.map(item => item.tax_rate)).toEqual([0.2, 0, null]);
    expect(axios.put.mock.calls[0][1].items.map(item => item.unit_price_minor)).toEqual([12000, 12000, 12000]);
  });

  it('uses the server-resolved legacy scope when tenant has no property_id', async () => {
    axios.get.mockImplementation(url => Promise.resolve({ data: url.includes('bulk') ? { items: [], property_id: 'legacy-tenant' } : { items: [] } }));
    render(<RoomQrCodes tenant={{ id: 'legacy-tenant' }} />);
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/rooms/qr-codes/bulk'));
    fireEvent.click(screen.getByRole('button', { name: 'Oda Servisi Menüsü' }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/room-qr/room-service-menu', { params: { property_id: 'legacy-tenant' } }));
  });

  it('does not pick an arbitrary other room property from a mixed-scope list', async () => {
    axios.get.mockResolvedValue({ data: { items: [{ room_id: 'r', room_number: '101', property_id: 'other-property' }], property_id: null } });
    render(<RoomQrCodes tenant={{ id: 't' }} />);
    await screen.findAllByText(/101/);
    fireEvent.click(screen.getByRole('button', { name: 'Oda Servisi Menüsü' }));
    expect(axios.get.mock.calls.some(([url]) => url === '/room-qr/room-service-menu')).toBe(false);
  });
});

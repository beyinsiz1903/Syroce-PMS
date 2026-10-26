import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import GuestQRMenu from '../GuestQRMenu';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useParams: () => ({ tenantId: 'hotel', outletId: 'bar' }) }));
vi.mock('react-hot-toast', () => ({ toast: { success: vi.fn(), error: vi.fn() }, Toaster: () => null }));

describe('signed guest QR ordering', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState({}, '', '/?table=one&token=signed-table');
    axios.get.mockResolvedValue({ data: { currency: 'EUR', categories: [{ name: 'İçecek', items: [
      { id: 'tea', item_name: 'Çay', unit_price: 100, tax_rate: .1, currency: 'EUR' },
    ] }] } });
    axios.post.mockResolvedValue({ data: { success: true, order_id: 'order' } });
  });

  it('uses the API-relative anonymous route and confirms the tax-inclusive total', async () => {
    render(<GuestQRMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'Çay ekle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Siparişi Ver' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/public/fnb/hotel/bar/order', expect.objectContaining({
      table_id: 'one', table_token: 'signed-table', expected_total: 110,
      items: [{ item_id: 'tea', quantity: 1 }], idempotency_key: expect.any(String),
    })));
    expect(axios.get).toHaveBeenCalledWith('/public/fnb/hotel/bar/menu');
    await waitFor(() => expect(sessionStorage.length).toBe(0));
  });

  it('shows Turkish labels instead of internal category keys', async () => {
    axios.get.mockResolvedValue({ data: { currency: 'TRY', categories: [
      { name: 'beverage', items: [] }, { name: 'appetizer', items: [] },
      { name: 'food', items: [] }, { name: 'dessert', items: [] },
    ] } });
    render(<GuestQRMenu />);
    expect(await screen.findByRole('heading', { name: 'İçecekler' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Başlangıçlar' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Ana yemekler' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Tatlılar' })).toBeInTheDocument();
  });

  it('keeps the same immutable request after a network error AND page reload', async () => {
    axios.post.mockRejectedValueOnce(new Error('timeout'));
    const view = render(<GuestQRMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'Çay ekle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Siparişi Ver' }));
    await screen.findByRole('button', { name: 'Aynı siparişi tekrar dene' });
    const sent = axios.post.mock.calls[0][1];
    expect(screen.getByRole('button', { name: 'Çay ekle' })).toBeDisabled();
    view.unmount();
    render(<GuestQRMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'Aynı siparişi tekrar dene' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    expect(axios.post.mock.calls[1][1]).toEqual(sent);
    await waitFor(() => expect(sessionStorage.length).toBe(0));
  });

  it('does not submit a copied old unsigned table code', async () => {
    window.history.replaceState({}, '', '/?table=one');
    render(<GuestQRMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'Çay ekle' }));
    expect(screen.getByRole('button', { name: 'Siparişi Ver' })).toBeDisabled();
    expect(screen.getByRole('alert')).toHaveTextContent('eski QR');
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('refreshes prices and clears an explicitly rejected quote', async () => {
    axios.post.mockRejectedValueOnce({ response: { status: 409, data: { detail: 'Menü fiyatı değişti' } } });
    render(<GuestQRMenu />);
    fireEvent.click(await screen.findByRole('button', { name: 'Çay ekle' }));
    fireEvent.click(screen.getByRole('button', { name: 'Siparişi Ver' }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledTimes(2));
    await screen.findByRole('button', { name: 'Çay ekle' });
    expect(screen.queryByRole('button', { name: 'Siparişi Ver' })).not.toBeInTheDocument();
    expect(sessionStorage.length).toBe(0);
  });
});

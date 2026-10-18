import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import AdminModuleSalesRequests from '../AdminModuleSalesRequests';

vi.mock('axios', () => ({ default: { get: vi.fn(), patch: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
const row = { id: '883f5403-request', product_name: 'Restoran POS', tenant_name: 'Kartepe', user_email: 'hotel@example.test',
  quantity: 2, status: 'new', delivery: { email: 'failed' }, created_at: '2026-10-18T10:00:00Z' };
const response = (requests = [row]) => ({ data: { requests, total: requests.length, summary: { open: 3, new: 2, quote_sent: 1, total: 4 }, has_more: false } });
const mount = (url = '/admin/module-requests') => render(<MemoryRouter initialEntries={[url]}><AdminModuleSalesRequests /></MemoryRouter>);

describe('Platform module sales queue', () => {
  beforeEach(() => { vi.resetAllMocks(); axios.get.mockResolvedValue(response()); axios.patch.mockResolvedValue({ data: { ok: true } }); });

  it('loads directly, without depending on price, refund, setup or tenant services', async () => {
    mount();
    expect(await screen.findByText('Restoran POS')).toBeInTheDocument();
    expect(axios.get).toHaveBeenCalledWith('/module-store/admin/quote-requests', { params: { status_filter: 'open', search: '', limit: 50, offset: 0 } });
    expect(axios.get.mock.calls.every(([url]) => url === '/module-store/admin/quote-requests')).toBe(true);
    expect(screen.getByText(/Satış e-postası: Gönderilemedi/)).toBeInTheDocument();
    expect(screen.getByText(/Talep edilen adet: 2/)).toBeInTheDocument();
  });

  it('opens the exact request from notification links and supports literal prefix search', async () => {
    mount('/admin/module-requests?request=883f5403');
    await screen.findByText('Restoran POS');
    expect(axios.get).toHaveBeenLastCalledWith('/module-store/admin/quote-requests', { params: { status_filter: 'all', search: '883f5403', limit: 50, offset: 0 } });
    fireEvent.change(screen.getByLabelText('Talep no, tesis, ürün veya e-posta'), { target: { value: '[otel]' } });
    fireEvent.click(screen.getByRole('button', { name: 'Ara' }));
    await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith('/module-store/admin/quote-requests', { params: { status_filter: 'all', search: '[otel]', limit: 50, offset: 0 } }));
  });

  it('keeps a failed read distinct from an empty queue and retries independently', async () => {
    axios.get.mockRejectedValueOnce(new Error('offline'));
    mount();
    expect(await screen.findByRole('alert')).toHaveTextContent('Liste boş kabul edilmedi');
    expect(screen.queryByText('Bu filtrede teklif talebi bulunamadı.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Yeniden dene' }));
    expect(await screen.findByText('Restoran POS')).toBeInTheDocument();
  });

  it('saves stage, assignee and follow-up in UTC, and preserves drafts if the save fails', async () => {
    mount(); await screen.findByText('Restoran POS');
    fireEvent.change(screen.getByLabelText(`Aşama ${row.id}`), { target: { value: 'in_progress' } });
    fireEvent.change(screen.getByLabelText(`Sorumlu ${row.id}`), { target: { value: 'Sales owner' } });
    fireEvent.change(screen.getByLabelText(`Takip tarihi ${row.id}`), { target: { value: '2026-10-19T10:30' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith(`/module-store/admin/quote-requests/${row.id}`, {
      status: 'in_progress', assignee: 'Sales owner', follow_up_at: new Date('2026-10-19T10:30').toISOString(), internal_note: null,
    }));
    await waitFor(() => expect(screen.getByRole('button', { name: 'Kaydet' })).toBeEnabled());
    axios.patch.mockRejectedValueOnce(new Error('offline'));
    fireEvent.change(screen.getByLabelText(`Yönetici notu ${row.id}`), { target: { value: 'Notumu koru' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('değişiklikleriniz korunuyor');
    expect(screen.getByLabelText(`Yönetici notu ${row.id}`)).toHaveValue('Notumu koru');
  });

  it('ignores a late result for a previous filter', async () => {
    let finishOld;
    axios.get.mockImplementationOnce(() => new Promise(resolve => { finishOld = resolve; }));
    mount();
    fireEvent.change(screen.getByLabelText('Aşama filtresi'), { target: { value: 'won' } });
    expect(await screen.findByText('Restoran POS')).toBeInTheDocument();
    await act(async () => finishOld(response([{ ...row, id: 'old', product_name: 'Eski filtre' }])));
    expect(screen.queryByText('Eski filtre')).not.toBeInTheDocument();
  });

  it('shows explicit pagination and resets it when the stage changes', async () => {
    axios.get.mockResolvedValue({ data: { ...response().data, total: 105, has_more: true } });
    mount(); await screen.findByText('Restoran POS');
    fireEvent.click(screen.getByRole('button', { name: 'Sonraki sayfa' }));
    await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith('/module-store/admin/quote-requests', { params: { status_filter: 'open', search: '', limit: 50, offset: 50 } }));
    fireEvent.change(screen.getByLabelText('Aşama filtresi'), { target: { value: 'new' } });
    await waitFor(() => expect(axios.get).toHaveBeenLastCalledWith('/module-store/admin/quote-requests', { params: { status_filter: 'new', search: '', limit: 50, offset: 0 } }));
  });
});

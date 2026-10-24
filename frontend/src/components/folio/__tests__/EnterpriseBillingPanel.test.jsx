import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import axios from 'axios';
import EnterpriseBillingPanel from '../EnterpriseBillingPanel';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
const props = { bookingId: 'booking', currency: 'TRY', folios: [{ id: 'guest', folio_number: 'F-1', status: 'open' }],
  charges: [{ id: 'room', folio_id: 'guest', description: 'Oda ücreti', charge_category: 'room', total: 1000 }] };
let requests;
beforeEach(() => {
  requests = [];
  vi.clearAllMocks();
  axios.get.mockImplementation(async url => ({ data: url.endsWith('catalog')
    ? { provider: null, provider_readiness: 'not_configured', non_collection_operations: ['concession'] }
    : url.endsWith('policy') ? { actor_id: 'requester', can_apply: true, concession_mode: 'direct', reason_required: true } : { items: requests } }));
  axios.post.mockImplementation(async (_url, body) => ({ data: { ...body, id: body.request_id, status: 'applied' } }));
});
afterEach(cleanup);

async function fill() {
  await screen.findByText(/Ödeme sağlayıcısı:/);
  fireEvent.change(screen.getByLabelText('İkram hedef folyo'), { target: { value: 'guest' } });
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('İkram gerekçesi'), { target: { value: 'Yönetim ikramı' } });
}

describe('Enterprise billing', () => {
  it('applies directly with explanation, refreshes the folio and removes approval settings', async () => {
    const onChanged = vi.fn();
    render(<EnterpriseBillingPanel {...props} onChanged={onChanged} />);
    await fill();
    expect(screen.getByText(/Entegre kart tahsilatı hazır değil/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'İkramı / indirimi uygula' }));
    await screen.findByText(/açıklama ve işlemi yapan kişi loga kaydedildi/);
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post.mock.calls[0][0]).toBe('/enterprise-billing/concessions');
    expect(axios.post.mock.calls[0][1]).toMatchObject({ folio_id: 'guest', charge_ids: ['room'], mode: 'full', reason: 'Yönetim ikramı' });
    expect(screen.queryByRole('button', { name: 'Onayla ve uygula' })).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Tesis ikram onay limiti')).not.toBeInTheDocument();
    await waitFor(() => expect(onChanged).toHaveBeenCalledTimes(1));
  });

  it('uses the same immutable request after an uncertain network result', async () => {
    axios.post.mockRejectedValueOnce(new Error('network timeout'));
    const onLockChange = vi.fn();
    render(<EnterpriseBillingPanel {...props} onLockChange={onLockChange} />);
    await fill();
    fireEvent.click(screen.getByRole('button', { name: 'İkramı / indirimi uygula' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Aynı talebin sonucunu doğrula' }));
    await screen.findByText(/açıklama ve işlemi yapan kişi loga kaydedildi/);
    expect(axios.post).toHaveBeenCalledTimes(2);
    expect(axios.post.mock.calls[0][1]).toEqual(axios.post.mock.calls[1][1]);
    expect(onLockChange).toHaveBeenCalledWith(true);
  });

  it('supports percentage and decimal comma without calling a cash collection endpoint', async () => {
    render(<EnterpriseBillingPanel {...props} />);
    await fill();
    fireEvent.change(screen.getByLabelText('İkram kapsamı'), { target: { value: 'percentage' } });
    fireEvent.change(screen.getByLabelText('İkram değeri'), { target: { value: '33,33' } });
    fireEvent.click(screen.getByRole('button', { name: 'İkramı / indirimi uygula' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post.mock.calls[0][1]).toMatchObject({ mode: 'percentage', percentage: 33.33 });
    expect(axios.post.mock.calls[0][0]).not.toContain('record-payment');
  });

  it('does not expose mutation controls in read-only mode', async () => {
    render(<EnterpriseBillingPanel {...props} readOnly />);
    await screen.findByText(/Ödeme sağlayıcısı:/);
    expect(screen.queryByRole('button', { name: 'İkramı / indirimi uygula' })).not.toBeInTheDocument();
  });

  it('bases a new percentage on remaining service value even after a folio move', async () => {
    requests = [{ id: 'prior', folio_id: 'previous-window', charge_ids: ['room'], allocated_charge_minor: { room: 40000 },
      status: 'applied', amount_minor: 40000, requested_by: 'other', reason: 'Önceki ikram', currency: 'TRY' }];
    render(<EnterpriseBillingPanel {...props} />);
    await fill();
    fireEvent.change(screen.getByLabelText('İkram kapsamı'), { target: { value: 'percentage' } });
    fireEvent.change(screen.getByLabelText('İkram değeri'), { target: { value: '50' } });
    expect(screen.getByText(/Uygulanacak tutar:/).textContent).toContain('300');
    expect(screen.getByRole('checkbox').closest('label').textContent).toContain('600');
  });

  it('lets the creator apply a legacy pending record with a required explanation', async () => {
    requests = [{ id: 'request', status: 'requested', amount_minor: 10000, requested_by: 'manager', reason: 'Örnek', currency: 'TRY' }];
    axios.get.mockImplementation(async url => ({ data: url.endsWith('catalog') ? { non_collection_operations: [] }
      : url.endsWith('policy') ? { actor_id: 'manager', can_apply: true } : { items: requests } }));
    axios.post.mockImplementation(async (_url, body) => ({ data: { id: 'request', status: 'applied', reason: body.reason } }));
    render(<EnterpriseBillingPanel {...props} />);
    await screen.findByText('Eski bekleyen işlem', { exact: false });
    fireEvent.change(screen.getByLabelText('Bekleyen işlem açıklaması request'), { target: { value: ' ' } });
    expect(screen.getByRole('button', { name: 'Uygula' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Bekleyen işlem açıklaması request'), { target: { value: 'Yönetim oda ikramı' } });
    fireEvent.click(screen.getByRole('button', { name: 'Uygula' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/enterprise-billing/concessions/request/apply', { reason: 'Yönetim oda ikramı' }));
  });

  it('does not expose concessions without existing financial override permission', async () => {
    axios.get.mockImplementation(async url => ({ data: url.endsWith('catalog') ? { non_collection_operations: [] }
      : url.endsWith('policy') ? { can_apply: false } : { items: [] } }));
    render(<EnterpriseBillingPanel {...props} />);
    await screen.findByText(/fiyat değiştirme yetkileri gerekir/);
    expect(screen.queryByRole('button', { name: 'İkramı / indirimi uygula' })).not.toBeInTheDocument();
  });

  it('requires a non-whitespace explanation before direct application', async () => {
    render(<EnterpriseBillingPanel {...props} />);
    await fill();
    fireEvent.change(screen.getByLabelText('İkram gerekçesi'), { target: { value: '  ' } });
    expect(screen.getByRole('button', { name: 'İkramı / indirimi uygula' })).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('shows the operator and explanation on an applied concession', async () => {
    requests = [{ id: 'applied', status: 'applied', amount_minor: 10000, currency: 'TRY',
      decided_by: 'manager', performed_by_name: 'Ayşe Yılmaz', business_date: '2026-10-24', reason: 'Yönetim oda ikramı' }];
    render(<EnterpriseBillingPanel {...props} />);
    await screen.findByText('Açıklama: Yönetim oda ikramı');
    expect(screen.getByText(/İşlemi yapan: Ayşe Yılmaz/)).toBeInTheDocument();
  });

  it('locks an uncertain legacy application and retries with the identical explanation', async () => {
    requests = [{ id: 'pending', status: 'requested', amount_minor: 10000, requested_by: 'requester', reason: 'Yönetim ikramı', currency: 'TRY' }];
    axios.post.mockRejectedValueOnce(new Error('timeout'));
    axios.post.mockImplementation(async () => ({ data: { id: 'pending', status: 'applied' } }));
    const onLockChange = vi.fn();
    render(<EnterpriseBillingPanel {...props} onLockChange={onLockChange} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Uygula' }));
    const retry = await screen.findByRole('button', { name: 'Bekleyen işlemin sonucunu doğrula' });
    expect(screen.getByLabelText('Bekleyen işlem açıklaması pending')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'İkramı / indirimi uygula' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'İptal et' })).toBeDisabled();
    fireEvent.click(retry);
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(2));
    expect(axios.post.mock.calls[0]).toEqual(axios.post.mock.calls[1]);
    expect(onLockChange).toHaveBeenCalledWith(true);
  });
});

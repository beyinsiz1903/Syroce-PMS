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
    : url.endsWith('policy') ? { actor_id: 'requester', can_approve: false, approval_limits_minor: {} } : { items: requests } }));
  axios.post.mockImplementation(async (_url, body) => ({ data: { ...body, id: body.request_id, status: 'requested' } }));
});
afterEach(cleanup);

async function fill() {
  await screen.findByText(/Ödeme sağlayıcısı:/);
  fireEvent.change(screen.getByLabelText('İkram hedef folyo'), { target: { value: 'guest' } });
  fireEvent.click(screen.getByRole('checkbox'));
  fireEvent.change(screen.getByLabelText('İkram gerekçesi'), { target: { value: 'Yönetim ikramı' } });
}

describe('Enterprise billing', () => {
  it('separates provider readiness and requires a second actor for concessions', async () => {
    render(<EnterpriseBillingPanel {...props} />);
    await fill();
    expect(screen.getByText(/Entegre kart tahsilatı hazır değil/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Onaya gönder' }));
    await screen.findByText(/Talep kaydedildi/);
    expect(axios.post).toHaveBeenCalledTimes(1);
    expect(axios.post.mock.calls[0][0]).toBe('/enterprise-billing/concessions');
    expect(axios.post.mock.calls[0][1]).toMatchObject({ folio_id: 'guest', charge_ids: ['room'], mode: 'full', reason: 'Yönetim ikramı' });
    expect(screen.queryByRole('button', { name: 'Onayla ve uygula' })).not.toBeInTheDocument();
  });

  it('uses the same immutable request after an uncertain network result', async () => {
    axios.post.mockRejectedValueOnce(new Error('network timeout'));
    const onLockChange = vi.fn();
    render(<EnterpriseBillingPanel {...props} onLockChange={onLockChange} />);
    await fill();
    fireEvent.click(screen.getByRole('button', { name: 'Onaya gönder' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Aynı talebin sonucunu doğrula' }));
    await screen.findByText(/Talep kaydedildi/);
    expect(axios.post).toHaveBeenCalledTimes(2);
    expect(axios.post.mock.calls[0][1]).toEqual(axios.post.mock.calls[1][1]);
    expect(onLockChange).toHaveBeenCalledWith(true);
  });

  it('supports percentage and decimal comma without recording a payment', async () => {
    render(<EnterpriseBillingPanel {...props} />);
    await fill();
    fireEvent.change(screen.getByLabelText('İkram kapsamı'), { target: { value: 'percentage' } });
    fireEvent.change(screen.getByLabelText('İkram değeri'), { target: { value: '33,33' } });
    fireEvent.click(screen.getByRole('button', { name: 'Onaya gönder' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));
    expect(axios.post.mock.calls[0][1]).toMatchObject({ mode: 'percentage', percentage: 33.33 });
    expect(axios.post.mock.calls[0][0]).not.toContain('record-payment');
  });

  it('does not expose mutation controls in read-only mode', async () => {
    render(<EnterpriseBillingPanel {...props} readOnly />);
    await screen.findByText(/Ödeme sağlayıcısı:/);
    expect(screen.queryByRole('button', { name: 'Onaya gönder' })).not.toBeInTheDocument();
  });

  it('bases a new percentage on remaining service value even after a folio move', async () => {
    requests = [{ id: 'prior', folio_id: 'previous-window', charge_ids: ['room'], allocated_charge_minor: { room: 40000 },
      status: 'applied', amount_minor: 40000, requested_by: 'other', reason: 'Önceki ikram', currency: 'TRY' }];
    render(<EnterpriseBillingPanel {...props} />);
    await fill();
    fireEvent.change(screen.getByLabelText('İkram kapsamı'), { target: { value: 'percentage' } });
    fireEvent.change(screen.getByLabelText('İkram değeri'), { target: { value: '50' } });
    expect(screen.getByText(/Talep:/).textContent).toContain('300');
    expect(screen.getByRole('checkbox').closest('label').textContent).toContain('600');
  });

  it('does not let a manager approve their own request', async () => {
    requests = [{ id: 'request', status: 'requested', amount_minor: 10000, requested_by: 'manager', reason: 'Örnek', currency: 'TRY' }];
    axios.get.mockImplementation(async url => ({ data: url.endsWith('catalog') ? { non_collection_operations: [] }
      : url.endsWith('policy') ? { actor_id: 'manager', can_approve: true, approval_limits_minor: {} } : { items: requests } }));
    render(<EnterpriseBillingPanel {...props} />);
    await screen.findByText('Onay bekliyor', { exact: false });
    expect(screen.queryByRole('button', { name: 'Onayla ve uygula' })).not.toBeInTheDocument();
  });
});

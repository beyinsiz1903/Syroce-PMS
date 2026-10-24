import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import FolioAllocationPanel from '../FolioAllocationPanel';

const { post } = vi.hoisted(() => ({ post: vi.fn() }));
vi.mock('axios', () => ({ default: { post } }));
const props = () => ({ bookingId: 'booking', currency: 'TRY', onClose: vi.fn(), onChanged: vi.fn(),
  folios: [ { id: 'guest', folio_number: 'F-1', folio_type: 'guest', status: 'open', balance: 10000, currency: 'TRY' },
    { id: 'company', folio_number: 'F-2', folio_type: 'company', cari_account_name: 'Örnek Şirket', status: 'open', balance: 0, currency: 'TRY' },
    { id: 'closed', folio_number: 'F-closed', status: 'closed' },
    { id: 'euro', folio_number: 'F-euro', status: 'open', currency: 'EUR' } ],
  charges: [{ id: 'room', folio_id: 'guest', description: 'Oda Ücreti', total: 6000 },
    { id: 'extra', folio_id: 'guest', description: 'Minibar', total: 4000 },
    { id: 'void', folio_id: 'guest', description: 'İptal masraf', total: 100, voided: true },
    { id: 'billed', folio_id: 'guest', description: 'Faturalı masraf', total: 100, invoice_id: 'invoice' },
    { id: 'adjust', folio_id: 'guest', description: 'Aktarım satırı', total: 100, charge_category: 'split_adjustment' },
    { id: 'orphan', description: 'İşlenmemiş ekstra', total: 100 }],
});
const choose = () => {
  fireEvent.change(screen.getByLabelText('Paylaştırma kaynak folyo'), { target: { value: 'guest' } });
  fireEvent.change(screen.getByLabelText('Paylaştırma hedef folyo'), { target: { value: 'company' } });
  fireEvent.change(screen.getByLabelText('Paylaştırma açıklaması'), { target: { value: 'Konaklama şirket hesabına' } });
};
beforeEach(() => {
  post.mockReset().mockImplementation(async (_url, body) => ({ data: { success: true, allocation_id: body.request_id,
    source_folio_id: body.source_folio_id, target_folio_id: body.target_folio_id, transferred_amount: 6000, source_balance: 4000, target_balance: 6000 } }));
});

describe('existing folio allocation', () => {
  it('moves the selected posted charge into the existing company window without creating payment/new folio', async () => {
    const data = props(); render(<FolioAllocationPanel {...data} />); choose();
    expect(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' })).toBeDisabled();
    expect(screen.getByLabelText('Paylaştırma hedef folyo')).not.toHaveTextContent('F-closed');
    expect(screen.getByLabelText('Paylaştırma hedef folyo')).not.toHaveTextContent('F-euro');
    for (const label of ['İptal masraf', 'Faturalı masraf', 'Aktarım satırı', 'İşlenmemiş ekstra']) expect(screen.queryByText(label)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('checkbox', { name: /Oda Ücreti/ }));
    expect(screen.getByTestId('allocation-preview')).toHaveTextContent('6.000');
    expect(screen.getByTestId('allocation-preview')).toHaveTextContent('4.000');
    fireEvent.click(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' }));
    await screen.findByText(/Paylaştırma kaydedildi:/);
    expect(post).toHaveBeenCalledExactlyOnceWith('/folio-windows/allocate', {
      request_id: expect.any(String), booking_id: 'booking', source_folio_id: 'guest', target_folio_id: 'company',
      mode: 'items', charge_ids: ['room'], expected_amount: 6000, reason: 'Konaklama şirket hesabına',
    });
    expect(data.onChanged).toHaveBeenCalledExactlyOnceWith('company');
    expect(screen.queryByRole('button', { name: 'Paylaştırmayı Onayla' })).not.toBeInTheDocument();
  });

  it('accepts decimal comma and full debt but blocks an amount above debt', async () => {
    render(<FolioAllocationPanel {...props()} />); choose();
    fireEvent.change(screen.getByLabelText('Paylaştırma yöntemi'), { target: { value: 'amount' } });
    fireEvent.change(screen.getByLabelText('Paylaştırma tutarı'), { target: { value: '10000,01' } });
    expect(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' })).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Paylaştırma tutarı'), { target: { value: '10000,00' } });
    expect(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' })).toBeEnabled();
    fireEvent.change(screen.getByLabelText('Paylaştırma tutarı'), { target: { value: '6000,01' } });
    fireEvent.click(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/folio-windows/allocate', expect.objectContaining({ mode: 'amount', amount: 6000.01 })));
    expect(post.mock.calls[0][1]).not.toHaveProperty('charge_ids');
  });

  it('locks uncertain requests and retries the same request id without double-submit', async () => {
    let fail;
    post.mockImplementationOnce(() => new Promise((_resolve, reject) => { fail = reject; }));
    render(<FolioAllocationPanel {...props()} />); choose();
    fireEvent.click(screen.getByRole('checkbox', { name: /Oda Ücreti/ }));
    const button = screen.getByRole('button', { name: 'Paylaştırmayı Onayla' });
    fireEvent.click(button); fireEvent.click(button);
    expect(post).toHaveBeenCalledTimes(1);
    fail(new Error('connection lost after commit'));
    await screen.findByRole('alert');
    expect(screen.getByLabelText('Paylaştırma hedef folyo')).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Kapat' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Aynı İşlemi Doğrula / Tekrar Dene' }));
    await screen.findByText(/Paylaştırma kaydedildi:/);
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[1][1]).toEqual(post.mock.calls[0][1]);
  });

  it('does not offer a second mutation if refresh fails after a successful allocation', async () => {
    const data = props(); data.onChanged.mockRejectedValue(new Error('refresh failed'));
    render(<FolioAllocationPanel {...data} />); choose();
    fireEvent.click(screen.getByRole('checkbox', { name: /Oda Ücreti/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Paylaştırma kaydedildi');
    expect(screen.queryByRole('button', { name: 'Paylaştırmayı Onayla' })).not.toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('invalidates selections if a refresh closes or removes the selected target', () => {
    const data = props(); const page = render(<FolioAllocationPanel {...data} />); choose();
    fireEvent.click(screen.getByRole('checkbox', { name: /Oda Ücreti/ }));
    expect(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' })).toBeEnabled();
    page.rerender(<FolioAllocationPanel {...data} folios={data.folios.map(folio => folio.id === 'company' ? { ...folio, status: 'closed' } : folio)} />);
    expect(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' })).toBeDisabled();
    expect(post).not.toHaveBeenCalled();
  });

  it('does not accept a response for another allocation as success', async () => {
    post.mockResolvedValueOnce({ data: { success: true, allocation_id: 'wrong-request', transferred_amount: 6000 } });
    render(<FolioAllocationPanel {...props()} />); choose();
    fireEvent.click(screen.getByRole('checkbox', { name: /Oda Ücreti/ }));
    fireEvent.click(screen.getByRole('button', { name: 'Paylaştırmayı Onayla' }));
    await screen.findByRole('alert');
    expect(screen.queryByText(/Paylaştırma kaydedildi:/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Aynı İşlemi Doğrula / Tekrar Dene' })).toBeEnabled();
  });
});

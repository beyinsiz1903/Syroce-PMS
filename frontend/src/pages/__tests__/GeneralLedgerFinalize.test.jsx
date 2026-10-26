import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import GeneralLedgerModule from '@/pages/GeneralLedgerModule';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('voucher finalization', () => {
  it('shows the source explanation instead of generic GL reversal for linked records', async () => {
    axios.get.mockImplementation(async url => ({ data: url === '/gl/voucher-policy'
      ? { policy: { mode: 'authorized_self', version: 0 }, can_manage: false, can_finalize: true }
      : url === '/gl/journal' ? { entries: [
        { id: 'linked', source: 'billing_settlement', memo: 'Misafir cüzdanı' },
        { id: 'funding', source: 'manual_voucher', memo: 'Fonlama kaydı' },
        { id: 'ordinary', source: 'manual_voucher', memo: 'Sıradan mahsup' },
      ], reversal_controls: { funding: { can_reverse: false, reason: 'Fonlama kaynağı haklara bağlı' } } } : {} }));
    render(<MemoryRouter initialEntries={['/?tab=journals']}><GeneralLedgerModule /></MemoryRouter>);
    expect(await screen.findByText('Fonlama kaynağı haklara bağlı')).toBeInTheDocument();
    expect(screen.getByText(/Rezervasyondaki özgün kaynaklı mahsup/)).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: 'Ters Kayıt Oluştur' })).toHaveLength(1);
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('collects a reason and uses the single server finalization path', async () => {
    axios.get.mockImplementation(async url => ({ data: url === '/gl/voucher-policy'
      ? { policy: { mode: 'authorized_self', version: 0 }, can_manage: false, can_finalize: true }
      : url === '/gl/vouchers' ? { vouchers: [{ id: 'voucher-1', voucher_no: 'MF-1', status: 'submitted', memo: 'Sunum bütçesi' }] } : {} }));
    axios.post.mockResolvedValue({ data: {} });
    render(<MemoryRouter initialEntries={['/?tab=journals']}><GeneralLedgerModule /></MemoryRouter>);
    fireEvent.click(await screen.findByRole('button', { name: 'Gerekçeyle Kesinleştir' }));
    const dialog = within(screen.getByTestId('gl-voucher-action-dialog'));
    expect(dialog.getByRole('button', { name: 'Onayla' })).toBeDisabled();
    fireEvent.change(dialog.getByLabelText('Gerekçe'), { target: { value: 'Kaynak belge ve tutarlar kontrol edildi' } });
    fireEvent.click(dialog.getByRole('button', { name: 'Onayla' }));
    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/gl/vouchers/voucher-1/finalize', { reason: 'Kaynak belge ve tutarlar kontrol edildi' }));
    expect(axios.post).toHaveBeenCalledTimes(1);
  });
});

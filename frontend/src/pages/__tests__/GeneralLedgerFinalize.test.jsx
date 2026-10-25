import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import axios from 'axios';
import GeneralLedgerModule from '@/pages/GeneralLedgerModule';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn(), put: vi.fn() } }));
afterEach(() => { cleanup(); vi.clearAllMocks(); });

describe('voucher finalization', () => {
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

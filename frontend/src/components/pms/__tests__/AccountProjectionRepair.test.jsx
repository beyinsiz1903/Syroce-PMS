import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import AccountProjectionRepair from '../AccountProjectionRepair';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
const issues = [{ account_id: 'cari_accounts:a', reason: 'account_projection_differs_from_sources' }];
const preview = { source: 'cari_accounts', account_id: 'a', currency: 'TRY', cached_balances: { balance: 4501, current_balance: 4501 },
  source_balance: 4503, source_transaction_count: 11, repairable: true, needs_repair: true, source_fingerprint: 'a'.repeat(64) };
const user = { id: 'admin', role: 'admin' };

async function open() {
  fireEvent.click(screen.getByRole('button', { name: 'Cari kaynak farklarını incele' }));
  fireEvent.change(screen.getByRole('combobox', { name: 'Düzeltilecek cari hesap' }), { target: { value: 'cari_accounts:a' } });
  await screen.findByText(/Kaynak hareketi: 11/);
}
function confirm() {
  fireEvent.change(screen.getByRole('textbox', { name: 'Düzeltme gerekçesi' }), { target: { value: 'Tarihsel kaynak dökümü incelendi' } });
  fireEvent.change(screen.getByRole('textbox', { name: 'Kaynak inceleme referansı' }), { target: { value: 'Cari ekstre Ağustos ve Eylül 2026' } });
  fireEvent.click(screen.getByRole('checkbox'));
}

describe('Account projection repair', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: preview });
    axios.post.mockResolvedValue({ data: { success: true, new_balance: 4503 } });
  });

  it('is hidden for non-admins and never posts automatically', async () => {
    const view = render(<AccountProjectionRepair issues={issues} user={{ role: 'front_desk' }} />);
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
    view.rerender(<AccountProjectionRepair issues={issues} user={user} />);
    await open();
    expect(screen.getByRole('button', { name: 'Kaynağa göre bakiyeyi yeniden kur' })).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('requires reason/reference/source confirmation and sends no arbitrary balance', async () => {
    const refreshed = vi.fn();
    render(<AccountProjectionRepair issues={issues} user={user} onRepaired={refreshed} />);
    await open(); confirm();
    fireEvent.click(screen.getByRole('button', { name: 'Kaynağa göre bakiyeyi yeniden kur' }));
    await screen.findByText(/Bakiye .*olarak yeniden kuruldu/);
    expect(refreshed).toHaveBeenCalledTimes(1);
    expect(axios.post).toHaveBeenCalledWith('/pms/account-projections/cari_accounts/a/repair', {
      request_id: expect.any(String), source_fingerprint: preview.source_fingerprint,
      reason: 'Tarihsel kaynak dökümü incelendi', source_review_reference: 'Cari ekstre Ağustos ve Eylül 2026', confirm_sources_authoritative: true,
    });
  });

  it('keeps the exact request identity and payload after an uncertain response', async () => {
    axios.post.mockRejectedValueOnce(new Error('response lost'));
    render(<AccountProjectionRepair issues={issues} user={user} />);
    await open(); confirm();
    fireEvent.click(screen.getByRole('button', { name: 'Kaynağa göre bakiyeyi yeniden kur' }));
    await screen.findByRole('alert');
    expect(screen.getByRole('textbox', { name: 'Düzeltme gerekçesi' })).toBeDisabled();
    fireEvent.click(screen.getByRole('button', { name: 'Aynı isteği tekrar kontrol et' }));
    await screen.findByText(/Bakiye .*olarak yeniden kuruldu/);
    expect(axios.post.mock.calls[0]).toEqual(axios.post.mock.calls[1]);
  });

  it('refuses incomplete source history rather than offering a write-off', async () => {
    axios.get.mockResolvedValue({ data: { ...preview, repairable: false, source_balance: null, blocked_reasons: ['source_history_missing'] } });
    render(<AccountProjectionRepair issues={issues} user={user} />);
    await open();
    expect(screen.getByRole('alert')).toHaveTextContent('source_history_missing');
    expect(screen.queryByRole('checkbox')).not.toBeInTheDocument();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('re-reads a changed source instead of silently repairing the new balance', async () => {
    axios.post.mockRejectedValueOnce({ response: { data: { detail: 'Cari kaynaklar değişti; önizlemeyi tekrar kontrol edin' } } });
    render(<AccountProjectionRepair issues={issues} user={user} />);
    await open(); confirm();
    fireEvent.click(screen.getByRole('button', { name: 'Kaynağa göre bakiyeyi yeniden kur' }));
    await screen.findByText('Cari kaynaklar değişti; önizlemeyi tekrar kontrol edin');
    axios.get.mockResolvedValueOnce({ data: { ...preview, source_fingerprint: 'b'.repeat(64), source_balance: 4504 } });
    fireEvent.click(screen.getByRole('button', { name: 'Güncel önizlemeyi tekrar oku' }));
    await waitFor(() => expect(screen.getByRole('textbox', { name: 'Düzeltme gerekçesi' })).toHaveValue(''));
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(axios.post).toHaveBeenCalledTimes(1);
  });
});

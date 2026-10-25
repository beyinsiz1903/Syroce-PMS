import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import { VoucherPolicyControls, VOUCHER_POLICY_ENDPOINT } from '@/pages/accounting/VoucherPolicyControls';

vi.mock('axios', () => ({ default: { get: vi.fn(), put: vi.fn() } }));
afterEach(cleanup);
beforeEach(() => vi.clearAllMocks());

describe('property voucher approval policy', () => {
  it('requires an admin reason and optimistic version before changing this property', async () => {
    const onChange = vi.fn();
    axios.get.mockResolvedValue({ data: { policy: { mode: 'authorized_self', version: 3 }, can_manage: true, can_finalize: true } });
    axios.put.mockResolvedValue({ data: { policy: { mode: 'dual_control', version: 4 }, can_manage: true, can_finalize: true } });
    render(<VoucherPolicyControls onChange={onChange} />);
    fireEvent.change(await screen.findByLabelText('Onay yöntemi'), { target: { value: 'dual_control' } });
    const save = screen.getByRole('button', { name: 'Politikayı Kaydet' });
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Politika değişikliği gerekçesi'), { target: { value: ' İşletme çift kontrol tercihi ' } });
    fireEvent.click(save);
    await waitFor(() => expect(axios.put).toHaveBeenCalledWith(VOUCHER_POLICY_ENDPOINT, { mode: 'dual_control', version: 3, reason: 'İşletme çift kontrol tercihi' }));
    expect(await screen.findByText(/İkinci kişi onayı: hazırlayan/)).toBeInTheDocument();
    expect(onChange).toHaveBeenLastCalledWith(expect.objectContaining({ policy: { mode: 'dual_control', version: 4 } }));
  });

  it('does not give finance users access to policy changes', async () => {
    axios.get.mockResolvedValue({ data: { policy: { mode: 'authorized_self', version: 0 }, can_manage: false, can_finalize: true } });
    render(<VoucherPolicyControls onChange={vi.fn()} />);
    expect(await screen.findByText(/Yetkili kullanıcı kendi fişini/)).toBeInTheDocument();
    expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
  });

  it('does not assume permissive settings when the policy cannot be loaded', async () => {
    const onChange = vi.fn();
    axios.get.mockRejectedValue(new Error('network'));
    render(<VoucherPolicyControls onChange={onChange} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('yüklenemedi');
    expect(onChange).toHaveBeenCalledWith(null);
    expect(onChange).toHaveBeenCalledTimes(1);
  });
});

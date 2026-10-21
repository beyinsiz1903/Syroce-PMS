import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { get, put, post, success, error } = vi.hoisted(() => ({
  get: vi.fn(), put: vi.fn(), post: vi.fn(), success: vi.fn(), error: vi.fn(),
}));
vi.mock('axios', () => ({ default: { get, put, post } }));
vi.mock('sonner', () => ({ toast: { success, error } }));

import KBSCloudSettings from '../KBSCloudSettings';

const base = { configured: false, managed: false, can_manage: true, enabled: false, verified: false, egress_ip: '8.8.8.8' };
const showSettings = async () => fireEvent.click(await screen.findByRole('button', { name: 'Bağlantı ayarları' }));

describe('KBS cloud settings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    get.mockResolvedValue({ data: base });
    put.mockResolvedValue({ data: {} });
    post.mockResolvedValue({ data: {} });
  });

  it('requires verified connection and explicit consent before live enablement', async () => {
    get.mockResolvedValue({ data: { ...base, configured: true, verified: true } });
    render(<KBSCloudSettings tenantId="a" onStatusChange={vi.fn()} />);
    await showSettings();
    const enable = screen.getByRole('button', { name: 'Canlı sunucu gönderimini etkinleştir' });
    expect(enable).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(enable).toBeEnabled();
    fireEvent.click(enable);
    await waitFor(() => expect(put).toHaveBeenCalledWith('/kbs/cloud/settings', { enabled: true, live_confirmed: true }));
  });

  it('saving secrets never enables live sending and clears fields afterward', async () => {
    render(<KBSCloudSettings tenantId="a" onStatusChange={vi.fn()} />);
    await showSettings();
    fireEvent.change(screen.getByLabelText('Yetkili kullanıcı T.C.'), { target: { value: '12345678901' } });
    fireEvent.change(screen.getByLabelText('Tesis kodu'), { target: { value: '123' } });
    fireEvent.change(screen.getByLabelText('Web servis şifresi'), { target: { value: 'synthetic' } });
    fireEvent.click(screen.getByRole('button', { name: 'Bilgileri güvenle kaydet' }));
    await waitFor(() => expect(put).toHaveBeenCalledWith('/kbs/cloud/settings', { user_tc: '12345678901', facility_code: '123', password: 'synthetic', enabled: false }));
    await waitFor(() => expect(screen.getByLabelText('Web servis şifresi')).toHaveValue(''));
    expect(screen.getByLabelText('Yetkili kullanıcı T.C.')).toHaveValue('');
    expect(localStorage.getItem('kbs-cloud-password')).toBeNull();
  });

  it('verification calls only the read-only connection test', async () => {
    get.mockResolvedValue({ data: { ...base, configured: true } });
    render(<KBSCloudSettings tenantId="a" onStatusChange={vi.fn()} />);
    await showSettings();
    fireEvent.click(screen.getByRole('button', { name: /Bağlantıyı doğrula/ }));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/kbs/cloud/verify'));
    expect(put).not.toHaveBeenCalled();
    expect(success).toHaveBeenCalledWith(expect.stringContaining('Misafir bildirimi gönderilmedi'));
  });

  it('does not expose configuration controls to reception users', async () => {
    get.mockResolvedValue({ data: { ...base, can_manage: false } });
    render(<KBSCloudSettings tenantId="a" onStatusChange={vi.fn()} />);
    await screen.findByText(/Sunucu bağlantısı henüz kurulmadı/);
    expect(screen.queryByRole('button', { name: 'Bağlantı ayarları' })).not.toBeInTheDocument();
  });

  it('an unavailable status is not shown as a successful connection', async () => {
    get.mockRejectedValue(new Error('offline'));
    const onStatus = vi.fn();
    render(<KBSCloudSettings tenantId="a" onStatusChange={onStatus} />);
    await screen.findByText(/Sunucu bağlantı durumu okunamadı/);
    expect(onStatus).toHaveBeenCalledWith(null);
    expect(screen.queryByText(/Sunucu gönderimi etkin\./)).not.toBeInTheDocument();
  });
});

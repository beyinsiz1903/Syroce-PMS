import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import axios from 'axios';
import UserAccessDialog from '../UserAccessDialog';

vi.mock('axios', () => ({ default: { get: vi.fn(), patch: vi.fn() } }));
const target = { id: 'staff-1', role: 'staff', name: 'Resepsiyon', access_revision: 2 };
const data = {
  modules: { reports: 'Raporlar' },
  pages: [{ key: 'reports', module: 'reports', label: 'Operasyon raporları', permissions: ['view_reports'] }],
  permissions: ['view_reports'], roles: [{ role: 'staff', modules: [], permissions: [] }],
  guest_data_visibility: {
    modes: [
      { value: 'full', label: 'Tam göster' },
      { value: 'masked', label: 'Maskeli göster' },
      { value: 'hidden', label: 'Tamamen gizle' },
    ],
    fields: [{ key: 'identity', label: 'Kimlik ve pasaport numarası', description: 'TCKN ve pasaport', default: 'hidden' }],
    default_policy: { identity: 'hidden' },
  },
};
describe('UserAccessDialog', () => {
  beforeEach(() => { vi.clearAllMocks(); axios.get.mockResolvedValue({ data }); axios.patch.mockResolvedValue({ data: { success: true } }); });
  it('saves explicit scopes, pages and grants with the loaded revision', async () => {
    const onSaved = vi.fn(), onClose = vi.fn();
    render(<UserAccessDialog target={target} onSaved={onSaved} onClose={onClose} />);
    fireEvent.click(await screen.findByLabelText('Raporlar'));
    fireEvent.click(screen.getByLabelText('Operasyon raporlarını görüntüle'));
    fireEvent.click(screen.getByRole('button', { name: 'Yetkileri Kaydet' }));
    await waitFor(() => expect(onSaved).toHaveBeenCalledOnce());
    expect(axios.patch).toHaveBeenCalledWith('/admin/users/staff-1/access', {
      module_scopes: ['reports'], page_access: {}, granted_permissions: ['view_reports'], guest_data_visibility: { identity: 'hidden' }, revision: 2, reset_to_role: false,
    });
    expect(onClose).toHaveBeenCalledOnce();
  });
  it('saves a user-specific guest data setting independently from the role', async () => {
    render(<UserAccessDialog target={target} onSaved={vi.fn()} onClose={vi.fn()} />);
    fireEvent.change(await screen.findByLabelText('Kimlik ve pasaport numarası görünürlüğü'), { target: { value: 'masked' } });
    fireEvent.click(screen.getByRole('button', { name: 'Yetkileri Kaydet' }));
    await waitFor(() => expect(axios.patch).toHaveBeenCalled());
    expect(axios.patch.mock.calls[0][1].guest_data_visibility).toEqual({ identity: 'masked' });
  });
  it('keeps the dialog open and shows stale-edit conflicts without claiming success', async () => {
    axios.patch.mockRejectedValue({ response: { data: { detail: 'Yetkiler değişti. Yenileyin.' } } });
    const onClose = vi.fn();
    render(<UserAccessDialog target={target} onSaved={vi.fn()} onClose={onClose} />);
    fireEvent.click(await screen.findByRole('button', { name: 'Yetkileri Kaydet' }));
    expect(await screen.findByRole('alert')).toHaveTextContent('Yetkiler değişti');
    expect(onClose).not.toHaveBeenCalled();
  });
  it('does not allow saving before the catalog loads', async () => {
    axios.get.mockRejectedValue(new Error('offline'));
    render(<UserAccessDialog target={target} onSaved={vi.fn()} onClose={vi.fn()} />);
    await screen.findByRole('alert');
    expect(screen.queryByRole('button', { name: 'Yetkileri Kaydet' })).not.toBeInTheDocument();
  });
});

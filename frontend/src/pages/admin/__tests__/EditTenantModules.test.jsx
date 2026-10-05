import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import EditTenantModal from '../EditTenantModal';

vi.mock('axios', () => ({ default: { patch: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

async function openModules(modules = {}) {
  render(<EditTenantModal open tenant={{ id: 'qa-hotel', modules }} onOpenChange={vi.fn()} />);
  const tab = screen.getByRole('tab', { name: /moduller/ });
  fireEvent.mouseDown(tab, { button: 0, ctrlKey: false });
  fireEvent.click(tab);
  await screen.findByRole('checkbox', { name: /İnsan Kaynakları/ });
}

describe('hotel module editing', () => {
  beforeEach(() => { vi.clearAllMocks(); axios.patch.mockResolvedValue({ data: {} }); });

  it('saves HR explicitly without dropping unknown existing settings', async () => {
    await openModules({ pms: true, custom_existing_flag: true });
    const hr = screen.getByRole('checkbox', { name: /İnsan Kaynakları/ });
    expect(hr).not.toBeChecked();
    fireEvent.click(hr);
    fireEvent.click(screen.getByTestId('edit-tenant-modules-submit'));
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith('/admin/tenants/qa-hotel/modules', expect.objectContaining({
      modules: expect.objectContaining({ hr: true, pms: true, custom_existing_flag: true }),
    })));
  });

  it('supports group enable-all and explicit HR disable', async () => {
    await openModules();
    const group = screen.getByText('İK & Ek Operasyon Modülleri').closest('.border');
    fireEvent.click(within(group).getByRole('button', { name: 'Hepsi' }));
    for (const label of [/İnsan Kaynakları/, /Gelişmiş POS/, /^Otopark/]) {
      expect(screen.getByRole('checkbox', { name: label })).toBeChecked();
    }
    fireEvent.click(screen.getByRole('checkbox', { name: /İnsan Kaynakları/ }));
    fireEvent.click(screen.getByTestId('edit-tenant-modules-submit'));
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith('/admin/tenants/qa-hotel/modules', expect.objectContaining({
      modules: expect.objectContaining({ hr: false, pos_fnb: true, parking: true }),
    })));
  });
});

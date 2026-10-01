import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import AdminModuleControlCenter from '../AdminModuleControlCenter';

vi.mock('axios', () => ({ default: { get: vi.fn(), patch: vi.fn(), post: vi.fn(), defaults: { headers: { common: {} } } } }));
vi.mock('sonner', () => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));

describe('AdminModuleControlCenter', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockResolvedValue({ data: { tenants: [{ id: 'hotel-1', property_name: 'Denizli Oteli', subscription_tier: 'mini', modules: { pms: true, hr: false } }] } });
    axios.patch.mockResolvedValue({ data: { modules: { pms: true, hr: true } } });
  });

  it('keeps changes in draft until publish is clicked', async () => {
    render(<AdminModuleControlCenter />);
    await screen.findByText('Denizli Oteli');
    const toggle = screen.getByRole('switch', { name: /İnsan Kaynakları.*aç/ });
    fireEvent.click(toggle);
    expect(axios.patch).not.toHaveBeenCalled();
    fireEvent.click(screen.getByTestId('publish-module-changes'));
    await waitFor(() => expect(axios.patch).toHaveBeenCalledWith('/admin/tenants/hotel-1/modules', expect.objectContaining({
      modules: expect.objectContaining({ pms: true, hr: true }),
    })));
  });
});

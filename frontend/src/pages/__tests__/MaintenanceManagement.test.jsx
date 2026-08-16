import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { axiosGet, axiosPost, toast } = vi.hoisted(() => ({
  axiosGet: vi.fn(),
  axiosPost: vi.fn(),
  toast: { error: vi.fn(), success: vi.fn() },
}));

vi.mock('axios', () => ({
  default: { get: axiosGet, post: axiosPost },
}));

vi.mock('sonner', () => ({ toast }));

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}));

vi.mock('@/components/ui/select', () => ({
  Select: ({ value, onValueChange, children }) => (
    <select aria-label="test-select" value={value} onChange={(event) => onValueChange(event.target.value)}>
      {children}
    </select>
  ),
  SelectContent: ({ children }) => <>{children}</>,
  SelectItem: ({ value, children }) => <option value={value}>{children}</option>,
  SelectTrigger: ({ children }) => <>{children}</>,
  SelectValue: ({ placeholder }) => <option value="">{placeholder}</option>,
}));

import MaintenanceAssets from '@/pages/MaintenanceAssets';
import MaintenancePlans from '@/pages/MaintenancePlans';

const assets = [
  { id: 'asset-1', name: 'Test HVAC', asset_type: 'hvac', room_number: '101' },
  { id: 'asset-2', name: 'Test Plumbing', asset_type: 'plumbing', room_number: '102' },
];

describe('maintenance asset and plan controls', () => {
  beforeEach(() => {
    axiosGet.mockReset();
    axiosPost.mockReset();
    toast.error.mockReset();
    toast.success.mockReset();
  });

  afterEach(() => cleanup());

  it('reloads assets when the type filter changes', async () => {
    axiosGet
      .mockResolvedValueOnce({ data: { items: assets } })
      .mockResolvedValueOnce({ data: { items: [assets[1]] } });

    render(<MaintenanceAssets />);
    expect(await screen.findByText('Test HVAC')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('test-select'), { target: { value: 'plumbing' } });

    await waitFor(() => expect(axiosGet).toHaveBeenLastCalledWith(
      '/maintenance/assets',
      { params: { asset_type: 'plumbing' } },
    ));
    expect(await screen.findByText('Test Plumbing')).toBeInTheDocument();
    expect(screen.queryByText('Test HVAC')).not.toBeInTheDocument();
  });

  it('creates a plan with a real selected asset id', async () => {
    axiosGet.mockImplementation((url) => Promise.resolve({
      data: { items: url === '/maintenance/assets' ? assets : [] },
    }));
    axiosPost.mockResolvedValue({ data: {} });

    render(<MaintenancePlans />);
    fireEvent.click(await screen.findByRole('button', { name: 'Yeni Plan' }));

    fireEvent.change(screen.getAllByLabelText('test-select')[0], { target: { value: 'asset-1' } });
    fireEvent.change(document.querySelector('input[type="date"]'), { target: { value: '2026-08-20' } });
    fireEvent.click(screen.getByRole('button', { name: 'Kaydet' }));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledWith(
      '/maintenance/plans',
      expect.objectContaining({
        asset_id: 'asset-1',
        next_due_date: new Date('2026-08-20').toISOString(),
      }),
    ));
    expect(toast.success).toHaveBeenCalledWith('Bakım planı oluşturuldu');
  });

  it('reports scheduler output instead of failing silently', async () => {
    axiosGet.mockResolvedValue({ data: { items: [] } });
    axiosPost.mockResolvedValue({ data: { created_count: 2, skipped_count: 1 } });

    render(<MaintenancePlans />);
    fireEvent.click(await screen.findByRole('button', { name: 'Run Scheduler' }));

    await waitFor(() => expect(toast.success).toHaveBeenCalledWith(
      '2 iş emri oluşturuldu, 1 geçersiz plan atlandı',
    ));
  });
});

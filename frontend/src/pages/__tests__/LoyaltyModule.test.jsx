import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';

import LoyaltyModule from '../LoyaltyModule';

vi.mock('axios', () => ({ default: { get: vi.fn(), post: vi.fn() } }));
vi.mock('sonner', () => ({ toast: { error: vi.fn(), success: vi.fn() } }));

const guests = (start, count) => Array.from({ length: count }, (_, index) => ({
  id: `guest-${start + index}`,
  name: `Misafir ${start + index}`,
  email: `misafir${start + index}@example.com`,
  phone: `555${start + index}`,
  total_stays: index % 3,
}));

describe('LoyaltyModule', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    axios.get.mockImplementation((url, config = {}) => {
      if (url === '/loyalty/programs') return Promise.resolve({ data: [] });
      if (url === '/pms/guests') {
        const offset = config.params?.offset || 0;
        return Promise.resolve({ data: guests(offset, 48), headers: { 'x-total-count': '120' } });
      }
      return Promise.resolve({ data: [] });
    });
    axios.post.mockResolvedValue({ data: {} });
  });

  it('50 kayıt sınırına takılmadan toplamı ve daha fazla yükleme işlemini gösterir', async () => {
    render(<LoyaltyModule />);

    expect(await screen.findByText('48 / 120 aktif misafir kaydını yükledi.', { exact: false })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Daha fazla misafir yükle' }));

    await waitFor(() => expect(screen.getByText('96 / 120 kayıt yüklendi')).toBeInTheDocument());
    expect(axios.get).toHaveBeenCalledWith('/pms/guests', { params: { limit: 48, offset: 48 } });
  });

  it('üyelik kaydını seçilen misafir kimliğiyle oluşturur', async () => {
    render(<LoyaltyModule />);
    const buttons = await screen.findAllByRole('button', { name: 'Kaydet' });
    fireEvent.click(buttons[0]);

    await waitFor(() => expect(axios.post).toHaveBeenCalledWith('/loyalty/programs', {
      guest_id: 'guest-0', tier: 'bronze', points: 0, lifetime_points: 0,
    }));
  });
});

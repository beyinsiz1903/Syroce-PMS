import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const { get, post, toastError, toastSuccess } = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  toastError: vi.fn(),
  toastSuccess: vi.fn(),
}));

vi.mock('axios', () => ({ default: { get, post } }));
vi.mock('sonner', () => ({ toast: { error: toastError, success: toastSuccess } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (_key, fallback) => fallback || _key }) }));

import AIRMSDashboard from '@/components/AIRMSDashboard';

describe('AIRMSDashboard fiyat önerisi', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    get.mockResolvedValue({ data: { data_available: false, message: 'Piyasa verisi yok' } });
    post.mockResolvedValue({
      data: {
        success: true,
        dry_run: true,
        published_rates: [{ date: '2026-10-03', forecasted_occupancy: 81, recommended_rate: 3500, published: false }],
      },
    });
  });

  afterEach(() => cleanup());

  it('uses dry-run for pricing suggestions and labels the result as a preview', async () => {
    render(<AIRMSDashboard />);
    fireEvent.click(screen.getByRole('button', { name: 'Yapay zekâ fiyat önerilerini göster' }));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/rms/ai-pricing/auto-publish-rates',
      null,
      expect.objectContaining({ params: expect.objectContaining({ dry_run: true }) }),
    ));
    expect(await screen.findByText('Fiyat önerisi önizlemesi')).toBeInTheDocument();
    expect(screen.getByText('Bu sonuç yalnızca öneridir; hiçbir fiyat kaydedilmedi veya kanallara gönderilmedi.')).toBeInTheDocument();
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('Hiçbir fiyat yayınlanmadı'));
  });
});

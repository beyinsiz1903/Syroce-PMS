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

import EnhancedReservationCalendar from '@/components/EnhancedReservationCalendar';

describe('EnhancedReservationCalendar AI pricing preview', () => {
  beforeEach(() => {
    get.mockReset();
    post.mockReset();
    toastError.mockReset();
    toastSuccess.mockReset();
    get.mockResolvedValue({ data: { rooms: [] } });
    post.mockResolvedValue({
      data: {
        success: true,
        dry_run: true,
        published_rates: [{
          date: '2026-10-03',
          forecasted_occupancy: 72.5,
          recommended_rate: 3250,
          published: false,
        }],
      },
    });
  });

  afterEach(() => cleanup());

  it('requests a dry-run preview and explicitly communicates that no rate is published', async () => {
    render(<EnhancedReservationCalendar />);

    fireEvent.click(screen.getByRole('button', { name: 'Yapay zekâ fiyat önerilerini göster' }));

    await waitFor(() => expect(post).toHaveBeenCalledWith(
      '/rms/ai-pricing/auto-publish-rates',
      null,
      expect.objectContaining({
        params: expect.objectContaining({ dry_run: true, strategy: 'revenue_optimization' }),
      }),
    ));
    expect(await screen.findByText('Fiyat önerisi önizlemesi')).toBeInTheDocument();
    expect(screen.getByText('Bu sonuç yalnızca öneridir; hiçbir fiyat kaydedilmedi veya kanallara gönderilmedi.')).toBeInTheDocument();
    expect(toastSuccess).toHaveBeenCalledWith(expect.stringContaining('Hiçbir fiyat yayınlanmadı'));
  });
});

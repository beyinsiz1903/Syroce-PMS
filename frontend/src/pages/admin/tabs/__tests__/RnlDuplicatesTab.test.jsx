import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup, waitFor } from '@testing-library/react';
import axios from 'axios';
import RnlDuplicatesTab from '@/pages/admin/tabs/RnlDuplicatesTab';

const stableT = (key, opts) => {
  if (opts && typeof opts === 'object' && 'count' in opts) {
    return `${key}:${opts.count}`;
  }
  return key;
};
const stableI18n = { t: stableT };
vi.mock('react-i18next', () => ({
  useTranslation: () => stableI18n,
}));

vi.mock('sonner', () => ({
  toast: {
    error: vi.fn(),
    success: vi.fn(),
    info: vi.fn(),
    warning: vi.fn(),
  },
}));

vi.mock('axios', () => ({
  default: {
    get: vi.fn(),
    post: vi.fn(),
  },
}));

const renderTab = async (plan) => {
  axios.get.mockResolvedValueOnce({ data: plan });
  render(<RnlDuplicatesTab />);
  await waitFor(() =>
    expect(screen.getByTestId('rnl-duplicates-tab')).toBeInTheDocument()
  );
};

beforeEach(() => {
  axios.get.mockReset();
  axios.post.mockReset();
});

afterEach(() => cleanup());

describe('RnlDuplicatesTab — destructive guardrails', () => {
  it('auto_resolvable=0 ise "Güvenli Çöz" butonu disabled', async () => {
    await renderTab({
      total: 3,
      auto_resolvable: 0,
      manual_required: 3,
      groups: [],
    });

    const btn = screen.getByTestId('rnl-resolve-safe');
    expect(btn).toBeDisabled();
    expect(axios.post).not.toHaveBeenCalled();
  });

  it('auto_resolvable>0 + confirm onayı → POST gövdesi/sorgu doğru', async () => {
    await renderTab({
      total: 2,
      auto_resolvable: 2,
      manual_required: 0,
      groups: [
        {
          tenant_id: 't1',
          room_id: 'r1',
          night_date: '2026-05-20',
          count: 2,
          recommendation: 'auto_safe',
          reason: 'duplicate active',
          keep_booking_id: 'b-keep',
          retire_booking_ids: ['b-retire'],
          owners: [
            { kind: 'active', booking_id: 'b-keep', status: 'checked_in' },
            { kind: 'block', booking_id: 'b-retire', status: 'cancelled' },
          ],
        },
      ],
    });

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(true);

    axios.post.mockResolvedValueOnce({
      data: {
        resolved_count: 2,
        skipped_count: 0,
        scanned: 2,
        skipped: [],
        index_rebuild: { ran: true },
      },
    });
    // fetchPlan refresh after resolve
    axios.get.mockResolvedValueOnce({
      data: { total: 0, auto_resolvable: 0, manual_required: 0, groups: [] },
    });

    const btn = screen.getByTestId('rnl-resolve-safe');
    expect(btn).not.toBeDisabled();
    fireEvent.click(btn);

    await waitFor(() => expect(axios.post).toHaveBeenCalledTimes(1));

    expect(confirmSpy).toHaveBeenCalledTimes(1);
    const [url, body, cfg] = axios.post.mock.calls[0];
    expect(url).toBe('/api/admin/db/room-night-lock-duplicates/resolve');
    expect(body).toEqual({ confirm: true, limit: 200 });
    expect(cfg).toEqual({ params: { dry_run: false, rebuild_index: true } });

    confirmSpy.mockRestore();
  });

  it('confirm iptal edilirse POST atılmaz', async () => {
    await renderTab({
      total: 1,
      auto_resolvable: 1,
      manual_required: 0,
      groups: [
        {
          tenant_id: 't1',
          room_id: 'r1',
          night_date: '2026-05-20',
          count: 2,
          recommendation: 'auto_safe',
          reason: 'dup',
          keep_booking_id: 'b1',
          retire_booking_ids: ['b2'],
          owners: [
            { kind: 'active', booking_id: 'b1' },
            { kind: 'block', booking_id: 'b2' },
          ],
        },
      ],
    });

    const confirmSpy = vi.spyOn(window, 'confirm').mockReturnValue(false);
    fireEvent.click(screen.getByTestId('rnl-resolve-safe'));

    await waitFor(() => expect(confirmSpy).toHaveBeenCalled());
    expect(axios.post).not.toHaveBeenCalled();

    confirmSpy.mockRestore();
  });

  it('manual_required grubu keeper/retire rozetlerini doğru çizer', async () => {
    await renderTab({
      total: 1,
      auto_resolvable: 0,
      manual_required: 1,
      groups: [
        {
          tenant_id: 't9',
          room_id: 'r9',
          night_date: '2026-05-21',
          count: 3,
          recommendation: 'manual_required',
          reason: 'multiple active bookings',
          keep_booking_id: 'book-keeper',
          retire_booking_ids: ['book-retire-1', 'book-retire-2'],
          owners: [
            { kind: 'active', booking_id: 'book-keeper', status: 'checked_in' },
            { kind: 'active', booking_id: 'book-retire-1', status: 'confirmed' },
            { kind: 'active', booking_id: 'book-retire-2', status: 'confirmed' },
          ],
        },
      ],
    });

    const group = screen.getByTestId('rnl-group-t9-r9-2026-05-21');
    expect(group).toBeInTheDocument();

    // keeper rozeti tam olarak 1 kez
    const keepers = screen.getAllByText('rnlDuplicates.keeper');
    expect(keepers).toHaveLength(1);

    // retire rozeti tam olarak 2 kez (her retire booking_id için)
    const retires = screen.getAllByText('rnlDuplicates.retire');
    expect(retires).toHaveLength(2);

    // booking_id'ler render ediliyor
    expect(group.textContent).toContain('book-keeper');
    expect(group.textContent).toContain('book-retire-1');
    expect(group.textContent).toContain('book-retire-2');

    // manual_required olduğu için alttaki uyarı kartı da görünmeli
    expect(screen.getByText(/rnlDuplicates.manualWarning/)).toBeInTheDocument();
  });
});

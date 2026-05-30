// Test koruması (#149 overbooking suggestions panel): EnhancedFrontDesk'in
// /ai/solve-overbooking POST yanıtını API'nin döndürdüğü öncelik sırasında
// render ettiğini doğrular — priority score, rationale, loyalty-tier badge ve
// önerilen taşıma metni. Ayrıca "çakışma yok" (empty) ve hata (error) durumları
// da panelin none mesajına düştüğünü doğrular. axios mock'lanır.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, waitFor, within } from '@testing-library/react';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      if (opts && typeof opts === 'object') {
        // tier label: defaultValue tek seçenek olarak verilir
        if ('defaultValue' in opts && Object.keys(opts).length === 1) {
          return opts.defaultValue;
        }
        const parts = Object.entries(opts)
          .filter(([k]) => k !== 'defaultValue')
          .map(([k, v]) => `${k}=${v}`);
        return parts.length ? `${key} ${parts.join(' ')}` : key;
      }
      return key;
    },
  }),
}));

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn(), warning: vi.fn() },
}));

const axiosGet = vi.fn();
const axiosPost = vi.fn();
vi.mock('axios', () => ({
  default: {
    get: (...args) => axiosGet(...args),
    post: (...args) => axiosPost(...args),
  },
}));

import EnhancedFrontDesk from '@/components/EnhancedFrontDesk';

// API öncelik skoruna göre azalan sıralı döndürür; bu fixture o sırayı yansıtır.
const solutions = [
  {
    booking_id: 'bk-1',
    guest_name: 'Ada Lovelace',
    loyalty_tier: 'vip',
    current_room: '101',
    recommended_room: '301',
    priority_score: 95,
    priority_rationale: 'VIP guest with long stay and high lifetime value',
  },
  {
    booking_id: 'bk-2',
    guest_name: 'Grace Hopper',
    loyalty_tier: 'gold',
    current_room: '102',
    recommended_room: '205',
    priority_score: 70,
    priority_rationale: 'Gold member arriving tonight',
  },
  {
    booking_id: 'bk-3',
    guest_name: 'Alan Turing',
    loyalty_tier: 'standard',
    current_room: '103',
    recommended_room: '110',
    priority_score: 40,
    priority_rationale: 'Standard guest, flexible dates',
  },
];

function setupAxios({ overbooking } = {}) {
  axiosGet.mockResolvedValue({ data: { bookings: [] } });
  if (overbooking instanceof Error) {
    axiosPost.mockImplementation((url) =>
      url.includes('/ai/solve-overbooking')
        ? Promise.reject(overbooking)
        : Promise.resolve({ data: {} })
    );
  } else {
    axiosPost.mockImplementation((url) =>
      url.includes('/ai/solve-overbooking')
        ? Promise.resolve({ data: { solutions: overbooking } })
        : Promise.resolve({ data: {} })
    );
  }
}

beforeEach(() => {
  axiosGet.mockReset();
  axiosPost.mockReset();
});
afterEach(() => cleanup());

describe('EnhancedFrontDesk — overbooking suggestions panel', () => {
  it('solutions render with score, rationale, tier badge and move text', async () => {
    setupAxios({ overbooking: solutions });
    render(<EnhancedFrontDesk />);

    const rows = await screen.findAllByTestId('overbooking-solution');
    expect(rows).toHaveLength(3);

    // POST doğru endpoint'e tarih query'si ile gitti
    await waitFor(() => {
      expect(axiosPost).toHaveBeenCalledWith(
        expect.stringContaining('/ai/solve-overbooking?date=')
      );
    });

    // İlk satırın tüm alanları render oldu
    const first = within(rows[0]);
    expect(first.getByText('Ada Lovelace')).toBeInTheDocument();
    expect(first.getByTestId('overbooking-priority-score')).toHaveTextContent('95');
    expect(first.getByTestId('overbooking-priority-rationale')).toHaveTextContent(
      'VIP guest with long stay and high lifetime value'
    );
    expect(first.getByTestId('overbooking-loyalty-tier')).toHaveTextContent('vip');
    // move: from=101 → to=301
    expect(rows[0]).toHaveTextContent('from=101');
    expect(rows[0]).toHaveTextContent('to=301');
  });

  it('preserves the API-provided priority order in the DOM', async () => {
    setupAxios({ overbooking: solutions });
    render(<EnhancedFrontDesk />);

    const rows = await screen.findAllByTestId('overbooking-solution');
    const names = rows.map((r) => within(r).getByRole('heading').textContent);
    expect(names).toEqual(['Ada Lovelace', 'Grace Hopper', 'Alan Turing']);

    const scores = screen
      .getAllByTestId('overbooking-priority-score')
      .map((el) => parseInt(el.textContent.replace(/\D/g, ''), 10));
    expect(scores).toEqual([95, 70, 40]);
  });

  it('renders the loyalty-tier badge for each tier in order', async () => {
    setupAxios({ overbooking: solutions });
    render(<EnhancedFrontDesk />);

    await screen.findAllByTestId('overbooking-solution');
    const tiers = screen
      .getAllByTestId('overbooking-loyalty-tier')
      .map((el) => el.textContent);
    expect(tiers).toEqual(['vip', 'gold', 'standard']);
  });

  it('shows the empty state when there are no conflicts', async () => {
    setupAxios({ overbooking: [] });
    render(<EnhancedFrontDesk />);

    expect(await screen.findByTestId('overbooking-suggestions')).toBeInTheDocument();
    expect(screen.queryByTestId('overbooking-solution')).toBeNull();
    expect(
      screen.getByText('frontDeskEnhanced.overbooking.none')
    ).toBeInTheDocument();
  });

  it('falls back to the empty state when the API call errors', async () => {
    setupAxios({ overbooking: new Error('500 boom') });
    render(<EnhancedFrontDesk />);

    expect(await screen.findByTestId('overbooking-suggestions')).toBeInTheDocument();
    expect(screen.queryByTestId('overbooking-solution')).toBeNull();
    expect(
      screen.getByText('frontDeskEnhanced.overbooking.none')
    ).toBeInTheDocument();
  });
});

import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import MobileGM from '../MobileGM';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

function mockApi({ tasksFail = false, ar = {} } = {}) {
  axios.get.mockImplementation((url) => {
    if (url.startsWith('/reports/daily-flash')) return Promise.resolve({ data: { date: '2026-09-15', occupancy: { occupancy_rate: 75, occupied_rooms: 3, total_rooms: 4 },
      revenue: { total_revenue: 0, total_revenue_by_currency: { EUR: 25.75, TRY: 1000.49 }, adr_by_currency: { EUR: 12.25 }, rev_par_by_currency: { EUR: 6.25 } } } });
    if (url.startsWith('/reports/finance-snapshot')) return Promise.resolve({ data: { pending_ar: { total: null, by_currency: { EUR: { total: 42.50 } }, ...ar },
      todays_collections: { amount: 321.45, currency: 'TRY', payment_count: 1 }, mtd_collections: { amount: 1000.55, currency: 'TRY', collection_rate_percentage: 50 } } });
    if (url === '/pms/staff-tasks?limit=5') return tasksFail ? Promise.reject(new Error('forbidden')) : Promise.resolve({ data: { tasks: [{ id: '1', title: 'Oda kontrolü' }] } });
    return Promise.resolve({ data: {} });
  });
}

describe('MobileGM report response mapping', () => {
  beforeEach(() => vi.clearAllMocks());

  it('shows actual occupancy, AR, collections, currencies and normalized tasks', async () => {
    mockApi();
    render(<MobileGM user={{}} tenant={{ id: 't', property_name: 'Test Hotel' }} />);
    expect(await screen.findByText('75.0%')).toBeInTheDocument();
    expect(screen.getByText(/42,50/)).toBeInTheDocument();
    expect(screen.getByText(/321,45/)).toBeInTheDocument();
    expect(screen.getByText(/1\.000,55/)).toBeInTheDocument();
    expect(screen.getByText(/25,75/)).toBeInTheDocument();
    expect(screen.getByText('Oda kontrolü')).toBeInTheDocument();
    expect(screen.getByText(/15 Eylül 2026/)).toBeInTheDocument();
  });

  it('does not erase financial reports when an unrelated staff request is denied', async () => {
    mockApi({ tasksFail: true });
    render(<MobileGM user={{}} tenant={{ id: 't', property_name: 'Test Hotel' }} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Personel görevleri');
    expect(screen.getByText(/321,45/)).toBeInTheDocument();
    expect(screen.getByText('75.0%')).toBeInTheDocument();
  });

  it('forces a fresh financial read when the user presses refresh', async () => {
    mockApi();
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    await screen.findByText('75.0%');
    fireEvent.click(screen.getByRole('button', { name: 'Yenile' }));
    await waitFor(() => expect(axios.get).toHaveBeenCalledWith('/reports/finance-snapshot?nocache=1'));
    expect(axios.get).toHaveBeenCalledWith('/reports/daily-flash?nocache=1');
  });

  it('does not display a partial balance as the complete receivable total', async () => {
    mockApi({ ar: { complete: false, failed_folio_ids: ['bad'] } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    expect(await screen.findByText('Veri eksik')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('toplam eksik');
    expect(screen.queryByText(/42,50/)).not.toBeInTheDocument();
  });

  it('shows native debt alongside a mixed-ledger reconciliation warning', async () => {
    mockApi({ ar: { complete: true, mixed_ledger_folio_ids: ['mixed'] } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    expect(await screen.findByText(/42,50/)).toBeInTheDocument();
    expect(screen.getByText(/1 folyoda farklı döviz bakiyeleri/)).toHaveTextContent('mahsup edilmedi');
  });

  it('does not certify unmatched account projections as a successful total', async () => {
    mockApi({ ar: { complete: false, failed_account_ids: ['cari_accounts:legacy'] } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    expect(await screen.findByText('Veri eksik')).toBeInTheDocument();
    expect(screen.getByRole('alert')).toHaveTextContent('folyo/cari bakiyeleri doğrulanamadı');
    expect(screen.queryByText(/42,50/)).not.toBeInTheDocument();
  });

  it('keeps unallocated account payments visible as unknown-age debt', async () => {
    mockApi({ ar: { complete: true, unaged_balance_by_currency: { EUR: 12.50 } } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    expect(await screen.findByText(/Vadesi belirsiz alacak/)).toHaveTextContent('12,50');
    expect(screen.getByText(/Tarih veya ödeme dağılımı doğrulanmalı/)).toBeInTheDocument();
  });
});

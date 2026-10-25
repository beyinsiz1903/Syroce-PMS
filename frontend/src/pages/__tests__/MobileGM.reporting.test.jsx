import { fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import axios from 'axios';
import MobileGM from '../MobileGM';

vi.mock('axios', () => ({ default: { get: vi.fn() } }));
vi.mock('react-router-dom', () => ({ useNavigate: () => vi.fn() }));
vi.mock('sonner', () => ({ toast: { error: vi.fn() } }));
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: key => key }) }));

function mockApi({ tasksFail = false, ar = {}, flash = {}, rooms = {} } = {}) {
  axios.get.mockImplementation((url) => {
    if (url.startsWith('/reports/daily-flash')) return Promise.resolve({ data: { date: '2026-09-15', occupancy: { occupancy_rate: 75, occupied_rooms: 3, total_rooms: 4 },
      revenue: { total_revenue: 0, total_revenue_by_currency: { EUR: 25.75, TRY: 1000.49 }, adr_by_currency: { EUR: 12.25 }, rev_par_by_currency: { EUR: 6.25 } }, ...flash } });
    if (url === '/housekeeping/room-status') return Promise.resolve({ data: rooms });
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

  it('counts occupied rooms from the canonical occupancy field, not a nonexistent movement field', async () => {
    mockApi({ flash: { occupancy: { occupied_rooms: 10, total_rooms: 31, occupancy_rate: 32.26 }, movements: { arrivals: 3, departures: 4, stayovers: 7 } } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    await screen.findByText('32.3%');
    expect(screen.getByText('Konaklayan oda').parentElement).toHaveTextContent('10');
    expect(screen.getByText(/kişi sayısı değildir/)).toBeInTheDocument();
  });

  it.each([0, undefined])('distinguishes zero occupied rooms from unavailable occupancy (%s)', async count => {
    mockApi({ flash: { occupancy: count === undefined ? undefined : { occupied_rooms: count, total_rooms: 31, occupancy_rate: 0 }, movements: { arrivals: 0, departures: 0 } } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    const label = await screen.findByText('Konaklayan oda');
    expect(label.parentElement).toHaveTextContent(count === undefined ? '—' : '0');
  });

  it('does not present unposted room metrics as a realized zero ADR or RevPAR', async () => {
    mockApi({ flash: { revenue: { posting_pending: true, adr: 0, rev_par: 0, adr_by_currency: {}, rev_par_by_currency: {},
      operational_adr_by_currency: { TRY: 2030, EUR: 35.6 }, operational_revpar_by_currency: { TRY: 654.84, EUR: 11.48 } } } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    expect(await screen.findByText('ADR: İşlenmeyi bekliyor')).toBeInTheDocument();
    expect(screen.getByText(/Tahakkuk ADR:/)).toHaveTextContent('2.030,00');
    expect(screen.getByText(/Tahakkuk RevPAR:/)).toHaveTextContent('654,84');
    expect(screen.getByRole('status')).toHaveTextContent('kesinleşmiş gelir değildir');
    fireEvent.click(screen.getByRole('button', { name: 'Tam Dashboard' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getAllByText('İşlenmeyi bekliyor')).toHaveLength(2);
    expect(within(dialog).getByText(/oda ücretleri henüz tam işlenmedi/)).toBeInTheDocument();
  });

  it('uses the same nested response contract in both detail dialogs', async () => {
    mockApi({ flash: { movements: { arrivals: 3, departures: 4, stayovers: 1 } } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    await screen.findByText('75.0%');
    fireEvent.click(screen.getByRole('button', { name: 'Tam Dashboard' }));
    expect(within(screen.getByRole('dialog')).getByText('75.0%')).toBeInTheDocument();
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' });
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', { name: 'nav.reports' }));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('75.0%')).toBeInTheDocument();
    expect(within(dialog).getByText('Geliş (rezervasyon):').parentElement).toHaveTextContent('3');
    expect(within(dialog).getByText('Gidiş (rezervasyon):').parentElement).toHaveTextContent('4');
  });

  it('retains unavailable and unknown room statuses in the physical inventory summary', async () => {
    mockApi({ rooms: { total_rooms: 31, status_counts: { occupied: 10, dirty: 18, available: 1, out_of_order: 1, unknown: 1 } } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    expect(await screen.findByText(/31 aktif fiziksel oda/)).toBeInTheDocument();
    expect(screen.getByText('Hizmet dışı / diğer durumlar: 2')).toBeInTheDocument();
  });

  it('renders actual same-cohort performance and keeps unknown channel share explicit', async () => {
    mockApi({ flash: { performance: { reservation_count: 4, average_stay_nights: 3.75,
      channel_share_pct: { ota: 25, direct: 25, agency: 25, unknown: 25 }, channel_classification_complete: false } } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    await screen.findByText('75.0%');
    fireEvent.click(screen.getByRole('button', { name: 'nav.reports' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText('3,75 gece')).toBeInTheDocument();
    expect(dialog.getByText(/iş gününde geceleyen 4 rezervasyon/)).toBeInTheDocument();
    for (const label of ['Rezervasyon Kaynağı (OTA):', 'Direkt Rezervasyon:', 'Acente / Şirket:', 'Kaynağı Belirsiz:']) {
      expect(dialog.getByText(label).parentElement).toHaveTextContent('25%');
    }
    expect(dialog.getByText(/doğrudan veya OTA sayılmadı/)).toBeInTheDocument();
    expect(dialog.queryByText('Operasyonel')).not.toBeInTheDocument();
    expect(dialog.getAllByText('Durum ölçülmüyor')).toHaveLength(2);
  });

  it.each([undefined, { reservation_count: 0, average_stay_nights: null, channel_share_pct: { ota: null, direct: null } }])(
    'never displays missing performance as zero (%s)', async performance => {
      mockApi({ flash: { performance, avg_stay_duration: 99, ota_percentage: 99, direct_percentage: 99 } });
      render(<MobileGM user={{}} tenant={{ id: 't' }} />);
      await screen.findByText('75.0%');
      fireEvent.click(screen.getByRole('button', { name: 'nav.reports' }));
      const dialog = within(screen.getByRole('dialog'));
      for (const label of ['Ortalama Konaklama Süresi:', 'Rezervasyon Kaynağı (OTA):', 'Direkt Rezervasyon:']) {
        expect(dialog.getByText(label).parentElement).toHaveTextContent('—');
        expect(dialog.getByText(label).parentElement).not.toHaveTextContent('0%');
      }
      expect(dialog.queryByText('99 gece')).not.toBeInTheDocument();
    },
  );

  it('distinguishes a measured zero OTA share from unavailable performance', async () => {
    mockApi({ flash: { performance: { reservation_count: 10, average_stay_nights: 4,
      channel_share_pct: { ota: 0, direct: 100, agency: 0, unknown: 0 }, channel_classification_complete: true } } });
    render(<MobileGM user={{}} tenant={{ id: 't' }} />);
    await screen.findByText('75.0%');
    fireEvent.click(screen.getByRole('button', { name: 'nav.reports' }));
    const dialog = within(screen.getByRole('dialog'));
    expect(dialog.getByText('Rezervasyon Kaynağı (OTA):').parentElement).toHaveTextContent('0%');
    expect(dialog.getByText('Direkt Rezervasyon:').parentElement).toHaveTextContent('100%');
    expect(dialog.getByText('4 gece')).toBeInTheDocument();
  });
});

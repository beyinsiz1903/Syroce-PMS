// Regression koruması (Task #419 — Folyo bölme akışı): FoliosTab'in "Folyo Böl"
// düğmesi + SplitFolioDialog entegrasyonunu uçtan uca doğrular. Reservation detayı
// bir modal (route değil) olduğu için canlı e2e kırılgan ve veri-bağımlı olurdu;
// bu yüzden FoliosTab gerçek SplitFolioDialog ile birlikte render edilip axios
// mock'lanarak gönderilen sözleşme (endpoint + payload) ve veri yenileme doğrulanır.
//
// Kapsanan kabul kriterleri:
//   1) data-testid="btn-folyo-bol" görünür + tıklayınca data-testid="split-folio-panel" açılır.
//   2) Kaleme göre bölme: kalem seçilip sebep girilince /pms-core/folio/split doğru
//      payload ile çağrılır ve onRefresh (veri yenileme) tetiklenir.
//   3) Sebep boşken işlem reddedilir (axios.post çağrılmaz, toast.error gösterilir).
//   4) Birden fazla folyo: kaynak folyo seçimiyle doğru folio_id ve yalnızca o
//      folyoya ait kalemler (folio_id eşleşmesi) iletilir.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, within } from '@testing-library/react';
import { toast } from 'sonner';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, fallback) => fallback || key }),
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

import { FoliosTab } from '@/pages/reservation-detail/FoliosTab';

const booking = { id: 'bk-1', guest_name: 'Ada Lovelace', room_number: '101' };
const summary = { total_amount: 100, total_charges: 100, total_payments: 0, balance: 100 };

function singleFolioProps(overrides = {}) {
  return {
    folios: [{ id: 'f1', folio_number: 'F-001', folio_type: 'guest', status: 'open', balance: 100 }],
    charges: [
      { id: 'c1', folio_id: 'f1', description: 'Oda Ücreti', total: 60, voided: false },
      { id: 'c2', folio_id: 'f1', description: 'Minibar', total: 40, voided: false },
    ],
    payments: [],
    extra_charges: [],
    summary,
    booking,
    onRefresh: vi.fn(),
    onSwitchTab: vi.fn(),
    ...overrides,
  };
}

function multiFolioProps(overrides = {}) {
  return {
    folios: [
      { id: 'f1', folio_number: 'F-001', folio_type: 'guest', status: 'open', balance: 100 },
      { id: 'f2', folio_number: 'F-002', folio_type: 'company', status: 'open', balance: 200 },
    ],
    charges: [
      { id: 'c1', folio_id: 'f1', description: 'Oda Ücreti', total: 60, voided: false },
      { id: 'c2', folio_id: 'f1', description: 'Minibar', total: 40, voided: false },
      { id: 'c3', folio_id: 'f2', description: 'Toplantı Salonu', total: 120, voided: false },
      { id: 'c4', folio_id: 'f2', description: 'İkram', total: 80, voided: false },
    ],
    payments: [],
    extra_charges: [],
    summary,
    booking,
    onRefresh: vi.fn(),
    onSwitchTab: vi.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  axiosGet.mockReset();
  axiosPost.mockReset();
  axiosGet.mockResolvedValue({ data: {} });
  axiosPost.mockResolvedValue({ data: { transferred_charges: 1, transferred_amount: 60 } });
  toast.error.mockReset();
  toast.success.mockReset();
});

afterEach(() => cleanup());

describe('FoliosTab — Folyo Böl akışı (Task #419)', () => {
  it('btn-folyo-bol görünür ve tıklayınca split-folio-panel açılır', () => {
    render(<FoliosTab {...singleFolioProps()} />);

    const btn = screen.getByTestId('btn-folyo-bol');
    expect(btn).toBeInTheDocument();
    expect(screen.queryByTestId('split-folio-panel')).toBeNull();

    fireEvent.click(btn);

    expect(screen.getByTestId('split-folio-panel')).toBeInTheDocument();
    // SplitFolioDialog kaynak folyo numarasını gösterir
    expect(screen.getAllByText(/F-001/).length).toBeGreaterThan(0);
  });

  it('kaleme göre bölme: kalem + sebep ile /pms-core/folio/split doğru payload çağrılır ve onRefresh tetiklenir', async () => {
    const onRefresh = vi.fn();
    render(<FoliosTab {...singleFolioProps({ onRefresh })} />);

    fireEvent.click(screen.getByTestId('btn-folyo-bol'));

    // İki kalemden birini seç (hepsini seçmek backend'de reddedilir → orijinalde en az bir kalem kalmalı)
    const checkboxes = screen.getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2);
    fireEvent.click(checkboxes[0]); // c1

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'Şirket faturası ayrıştırma' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Bölmeyi Onayla/i }));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledTimes(1));
    const [url, payload] = axiosPost.mock.calls[0];
    expect(url).toBe('/pms-core/folio/split');
    expect(payload).toMatchObject({
      source_folio_id: 'f1',
      charge_ids: ['c1'],
      target_folio_type: 'guest',
      reason: 'Şirket faturası ayrıştırma',
    });

    // Başarı sonrası veri yenilenir (onSuccess → onRefresh)
    await waitFor(() => expect(onRefresh).toHaveBeenCalled());
  });

  it('sebep boşken işlem reddedilir: axios.post çağrılmaz, toast.error gösterilir', () => {
    render(<FoliosTab {...singleFolioProps()} />);

    fireEvent.click(screen.getByTestId('btn-folyo-bol'));

    // Kalem seç ama sebebi boş bırak
    fireEvent.click(screen.getAllByRole('checkbox')[0]);
    fireEvent.click(screen.getByRole('button', { name: /Bölmeyi Onayla/i }));

    expect(axiosPost).not.toHaveBeenCalled();
    expect(toast.error).toHaveBeenCalledWith('Bölme sebebini yazın');
  });

  it('birden fazla folyo: kaynak folyo seçimi doğru folio_id ve yalnızca o folyonun kalemlerini iletir', async () => {
    render(<FoliosTab {...multiFolioProps()} />);

    fireEvent.click(screen.getByTestId('btn-folyo-bol'));

    const panel = screen.getByTestId('split-folio-panel');

    // Varsayılan kaynak folyo F-001 (guest) → kalemleri c1/c2
    expect(within(panel).getByText('Oda Ücreti')).toBeInTheDocument();
    expect(within(panel).queryByText('Toplantı Salonu')).toBeNull();

    // Kaynak folyoyu F-002'ye çevir
    fireEvent.change(within(panel).getByRole('combobox'), { target: { value: 'f2' } });

    // Artık yalnızca F-002 kalemleri görünür (folio_id eşleşmesi)
    expect(within(panel).getByText('Toplantı Salonu')).toBeInTheDocument();
    expect(within(panel).getByText('İkram')).toBeInTheDocument();
    expect(within(panel).queryByText('Oda Ücreti')).toBeNull();

    const checkboxes = within(panel).getAllByRole('checkbox');
    expect(checkboxes).toHaveLength(2); // c3, c4
    fireEvent.click(checkboxes[0]); // c3

    fireEvent.change(within(panel).getByRole('textbox'), {
      target: { value: 'Şirket folyosu bölme' },
    });

    fireEvent.click(screen.getByRole('button', { name: /Bölmeyi Onayla/i }));

    await waitFor(() => expect(axiosPost).toHaveBeenCalledTimes(1));
    const [url, payload] = axiosPost.mock.calls[0];
    expect(url).toBe('/pms-core/folio/split');
    expect(payload.source_folio_id).toBe('f2');
    expect(payload.charge_ids).toEqual(['c3']);
  });
});
